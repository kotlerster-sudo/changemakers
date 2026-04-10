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


# ── Stage / visit-type helpers ────────────────────────────────────────────────

def _hh_stage(hh_cmchis, max_visits, has_closer):
    c = (hh_cmchis or "").lower()
    if "active" in c:
        return "CMCHIS Active"
    if "rejected" in c:
        return "Rejected"
    if "applied" in c and "not" not in c:
        return "Applied"
    if int(max_visits or 0) == 1:
        return "First Visit"
    if has_closer:
        return "Docs Ready – Follow-up"
    return "Pending Docs – Follow-up"


def _visit_type(max_visits, has_closer):
    if int(max_visits or 0) == 1:
        return "first"
    if has_closer:
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
        {"fieldname": "visited",           "label": "Visited HH",        "fieldtype": "Int",     "width": 90},
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

    # One row per HOUSEHOLD (GROUP BY in SQL — no Python deduplication needed).
    # Subquery finds HHs where any member was visited by the app today
    # (visit_count > 0 excludes last_visited_at set by bulk upload).
    rows = frappe.db.sql(
        """
        SELECT
            hh.name                         AS hh_name,
            hh.cmchis_status                AS hh_cmchis,
            hh.respondent                   AS hh_respondent,
            sl.street_name                  AS street_label,
            sl.intervention_units           AS iu_name,
            sl.added_by_co                  AS co_id,
            iu.name_of_iu                   AS iu_label,
            staff.full_name                 AS co_name,
            MAX(ind.visit_count)            AS max_visits,
            MAX(CASE
                WHEN ind.aadhaar_status = 'Aadhaar Received'
                 AND ind.income_status IN ('Income Cert Received', 'Income Cert Expired')
                THEN 1 ELSE 0 END)          AS has_closer
        FROM `tabHousehold Profile-WRP` hh
        INNER JOIN `tabIndividual Profile-WRP` ind
            ON ind.hhid = hh.name
           AND ind.status = 'Active- ஆக்டிவ்'
        LEFT JOIN `tabStreet List  - WRP` sl  ON sl.name  = hh.street_name
        LEFT JOIN `tabIntervention Units-WRP` iu ON iu.name = sl.intervention_units
        LEFT JOIN `tabStaff details - WRP` staff ON staff.name = sl.added_by_co
        WHERE hh.name IN (
            SELECT DISTINCT hhid
            FROM `tabIndividual Profile-WRP`
            WHERE status      = 'Active- ஆக்டிவ்'
              AND visit_count > 0
              AND DATE(last_visited_at) = %(date)s
              AND hhid IS NOT NULL AND hhid != ''
        )
        {cond}
        GROUP BY
            hh.name, hh.cmchis_status, hh.respondent,
            sl.street_name, sl.intervention_units, sl.added_by_co,
            iu.name_of_iu, staff.full_name
        ORDER BY staff.full_name, sl.street_name
        """.format(cond=cond),
        vals,
        as_dict=True,
    )

    if not rows:
        return []

    # ── Group households by CO ────────────────────────────────────────────────
    co_groups = {}
    co_order  = []

    for r in rows:
        co_id = r.get("co_id") or "Unassigned"
        if co_id not in co_groups:
            co_groups[co_id] = {
                "co_name": r.get("co_name") or co_id,
                "iu":      r.get("iu_label") or r.get("iu_name") or "",
                "hhs":     [],
            }
            co_order.append(co_id)

        vtype = _visit_type(r.get("max_visits"), r.get("has_closer"))
        co_groups[co_id]["hhs"].append({
            "respondent": r.get("hh_respondent") or r.get("hh_name") or "",
            "street":     r.get("street_label") or "",
            "stage":      _hh_stage(r.get("hh_cmchis"), r.get("max_visits"), r.get("has_closer")),
            "vtype":      vtype,
        })

    # ── Build output rows ─────────────────────────────────────────────────────
    EMPTY = {
        "intervention_unit": "", "street": "",
        "target": "", "coverage_pct": "",
        "first_visits": "", "doc_followups": "", "regular_followups": "",
        "stage": "",
    }

    data = []
    for co_id in co_order:
        co    = co_groups[co_id]
        hhs   = co["hhs"]
        total = len(hhs)
        first_v = sum(1 for h in hhs if h["vtype"] == "first")
        doc_v   = sum(1 for h in hhs if h["vtype"] == "doc")
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
                "label":  hh["respondent"],
                "street": hh["street"],
                "visited": "",
                "first_visits":      1 if hh["vtype"] == "first"   else "",
                "doc_followups":     1 if hh["vtype"] == "doc"     else "",
                "regular_followups": 1 if hh["vtype"] == "regular" else "",
                "stage":  hh["stage"],
                "indent": 1,
                "bold":   0,
            })
            data.append(row)

    return data
