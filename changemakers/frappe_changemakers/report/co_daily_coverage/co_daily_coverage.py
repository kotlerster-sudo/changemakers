import frappe
from frappe.utils import nowdate


def _user_org_filter():
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if not wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        return "", {}
    org = frappe.db.get_value("Staff details - WRP", {"mail_id": frappe.session.user}, "organisation")
    if not org:
        return None
    return " AND sl.implementing_org = %(user_org)s", {"user_org": org}


# ── HH-level helpers (same rule as pipeline dashboard) ────────────────────────

AADHAAR_RECEIVED = "Aadhaar Received"
INCOME_READY = {"Income Cert Received", "Income Cert Expired"}


def _hh_closer(members):
    for m in members:
        if (m.get("aadhaar_status") or "") == AADHAAR_RECEIVED and \
           (m.get("income_status") or "") in INCOME_READY:
            return True
    return False


def _hh_stage_label(hh_cmchis, max_visits, members):
    c = (hh_cmchis or "").lower()
    if "active" in c:
        return "CMCHIS Active"
    if "rejected" in c:
        return "Rejected"
    if "applied" in c and "not" not in c:
        return "Applied"
    if max_visits == 1:
        return "First Visit"
    if _hh_closer(members):
        return "Docs Ready – Follow-up"
    return "Pending Docs – Follow-up"


def _hh_visit_type(max_visits, members):
    """Classify the household's visit into first / doc / regular."""
    if max_visits == 1:
        return "first"
    if _hh_closer(members):
        return "doc"
    return "regular"


# ── Columns ───────────────────────────────────────────────────────────────────

def execute(filters=None):
    filters = filters or {}
    if not filters.get("date"):
        filters["date"] = nowdate()
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"fieldname": "label",             "label": "CO / Household",    "fieldtype": "Data",    "width": 220},
        {"fieldname": "intervention_unit", "label": "Intervention Unit", "fieldtype": "Data",    "width": 150},
        {"fieldname": "street",            "label": "Street",            "fieldtype": "Data",    "width": 140},
        {"fieldname": "visited",           "label": "Visited",           "fieldtype": "Int",     "width": 80},
        {"fieldname": "target",            "label": "Target",            "fieldtype": "Int",     "width": 70},
        {"fieldname": "coverage_pct",      "label": "Coverage %",        "fieldtype": "Percent", "width": 105},
        {"fieldname": "first_visits",      "label": "First Visits",      "fieldtype": "Int",     "width": 95},
        {"fieldname": "doc_followups",     "label": "Doc Follow-ups",    "fieldtype": "Int",     "width": 115},
        {"fieldname": "regular_followups", "label": "Regular Follow-ups","fieldtype": "Int",     "width": 130},
        {"fieldname": "stage",             "label": "Stage",             "fieldtype": "Data",    "width": 180},
    ]


# ── Data ──────────────────────────────────────────────────────────────────────

def get_data(filters):
    date_filter = filters.get("date") or nowdate()
    cond = ""
    vals = {"date": date_filter}

    if filters.get("street"):
        cond += " AND sl.name = %(street)s"
        vals["street"] = filters["street"]
    if filters.get("intervention_unit"):
        cond += " AND sl.intervention_units = %(intervention_unit)s"
        vals["intervention_unit"] = filters["intervention_unit"]

    org_filter = _user_org_filter()
    if org_filter is None:
        return []
    org_cond, org_vals = org_filter
    cond += org_cond
    vals.update(org_vals)

    # Fetch all individuals whose last_visited_at is today.
    # We then group by household — a household is "visited today" if ANY member was.
    rows = frappe.db.sql(
        """
        SELECT
            ind.name              AS ind_id,
            ind.visit_count,
            ind.aadhaar_status,
            ind.income_status,
            ind.last_visited_at,
            hh.name               AS hh_name,
            hh.cmchis_status      AS hh_cmchis,
            hh.respondent         AS hh_respondent,
            hh.street_name        AS hh_street,
            sl.street_name        AS street_label,
            sl.intervention_units AS iu_name,
            sl.added_by_co        AS co_id,
            iu.name_of_iu         AS iu_label,
            staff.full_name       AS co_name
        FROM `tabIndividual Profile-WRP` ind
        INNER JOIN `tabHousehold Profile-WRP` hh
            ON hh.name = ind.hhid
        LEFT JOIN `tabStreet List  - WRP` sl
            ON sl.name = hh.street_name
        LEFT JOIN `tabIntervention Units-WRP` iu
            ON iu.name = sl.intervention_units
        LEFT JOIN `tabStaff details - WRP` staff
            ON staff.name = sl.added_by_co
        WHERE ind.status = 'Active- ஆக்டிவ்'
          AND DATE(ind.last_visited_at) = %(date)s
          {cond}
        """.format(cond=cond),
        vals,
        as_dict=True,
    )

    if not rows:
        return []

    # ── Step 1: group individuals by household ────────────────────────────────
    hh_map   = {}
    hh_order = []

    for r in rows:
        hh_name = r.get("hh_name") or r.get("ind_id")
        if hh_name not in hh_map:
            hh_map[hh_name] = {
                "hh_name":    hh_name,
                "respondent": r.get("hh_respondent") or "",
                "hh_cmchis":  r.get("hh_cmchis") or "",
                "street":     r.get("street_label") or r.get("hh_street") or "",
                "iu":         r.get("iu_label") or r.get("iu_name") or "",
                "co_id":      r.get("co_id"),
                "co_name":    r.get("co_name") or "",
                "members":    [],
            }
            hh_order.append(hh_name)
        hh_map[hh_name]["members"].append({
            "visit_count":    r.get("visit_count"),
            "aadhaar_status": r.get("aadhaar_status"),
            "income_status":  r.get("income_status"),
        })

    # ── Step 2: classify each household ──────────────────────────────────────
    for hh_name in hh_order:
        hh = hh_map[hh_name]
        members = hh["members"]
        max_visits = max(int(m.get("visit_count") or 0) for m in members)
        hh["max_visits"] = max_visits
        hh["stage"]      = _hh_stage_label(hh["hh_cmchis"], max_visits, members)
        hh["visit_type"] = _hh_visit_type(max_visits, members)

    # ── Step 3: group households by CO ────────────────────────────────────────
    co_groups = {}
    co_order  = []

    for hh_name in hh_order:
        hh   = hh_map[hh_name]
        co_id = hh.get("co_id") or "Unassigned"
        if co_id not in co_groups:
            co_groups[co_id] = {
                "co_name":    hh.get("co_name") or co_id,
                "iu":         hh.get("iu") or "",
                "households": [],
            }
            co_order.append(co_id)
        co_groups[co_id]["households"].append(hh)

    # ── Step 4: build output rows ─────────────────────────────────────────────
    EMPTY = {
        "intervention_unit": "", "street": "", "visited": "",
        "target": "", "coverage_pct": "", "first_visits": "",
        "doc_followups": "", "regular_followups": "", "stage": "",
    }

    data = []
    for co_id in co_order:
        co   = co_groups[co_id]
        hhs  = co["households"]
        total = len(hhs)
        first_v = sum(1 for h in hhs if h["visit_type"] == "first")
        doc_v   = sum(1 for h in hhs if h["visit_type"] == "doc")
        reg_v   = total - first_v - doc_v

        data.append({
            "label":             co["co_name"],
            "intervention_unit": co["iu"],
            "street":            "",
            "visited":           total,
            "target":            30,
            "coverage_pct":      round(total / 30 * 100, 1),
            "first_visits":      first_v,
            "doc_followups":     doc_v,
            "regular_followups": reg_v,
            "stage":             "",
            "indent":            0,
            "bold":              1,
        })

        for hh in hhs:
            row = dict(EMPTY)
            row.update({
                "label":             hh.get("respondent") or hh.get("hh_name"),
                "street":            hh.get("street") or "",
                "visited":           1,
                "first_visits":      1 if hh["visit_type"] == "first" else "",
                "doc_followups":     1 if hh["visit_type"] == "doc" else "",
                "regular_followups": 1 if hh["visit_type"] == "regular" else "",
                "stage":             hh["stage"],
                "indent":            1,
                "bold":              0,
            })
            data.append(row)

    return data
