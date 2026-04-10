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


def _classify_transition(old_b, new_b):
    """Map old→new bucket pair to a transition category."""
    if not old_b or not new_b or old_b == new_b:
        return None
    if new_b == "docs_ready":
        return "docs_completed"
    if new_b == "applied":
        return "cmchis_applied"
    if new_b == "active":
        return "cmchis_active"
    if new_b == "rejected":
        return "rejected"
    if old_b == "missing_both" and new_b == "missing_income":
        return "aadhaar_step"
    if old_b == "missing_both" and new_b == "missing_aadhaar":
        return "income_step"
    return None


TRANS_PRIORITY = {
    "cmchis_active": 6, "cmchis_applied": 5, "docs_completed": 4,
    "aadhaar_step": 3, "income_step": 2, "rejected": 1,
}

TRANS_COLS = ["docs_completed", "aadhaar_step", "income_step",
              "cmchis_applied", "cmchis_active", "rejected"]


# ── Columns ───────────────────────────────────────────────────────────────────

def execute(filters=None):
    filters = filters or {}
    if not filters.get("date"):
        filters["date"] = nowdate()
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"fieldname": "label",             "label": "CO / Household",      "fieldtype": "Data",    "width": 220},
        {"fieldname": "intervention_unit", "label": "Intervention Unit",   "fieldtype": "Data",    "width": 150},
        {"fieldname": "street",            "label": "Street",              "fieldtype": "Data",    "width": 140},
        {"fieldname": "visited",           "label": "Visited HH",          "fieldtype": "Int",     "width": 90},
        {"fieldname": "target",            "label": "Target",              "fieldtype": "Int",     "width": 70},
        {"fieldname": "coverage_pct",      "label": "Coverage %",          "fieldtype": "Percent", "width": 105},
        {"fieldname": "first_visits",      "label": "First Visits",        "fieldtype": "Int",     "width": 95},
        {"fieldname": "doc_followups",     "label": "Doc Follow-ups",      "fieldtype": "Int",     "width": 115},
        {"fieldname": "regular_followups", "label": "Regular Follow-ups",  "fieldtype": "Int",     "width": 130},
        {"fieldname": "docs_completed",    "label": "→ Docs Ready",        "fieldtype": "Int",     "width": 105},
        {"fieldname": "aadhaar_step",      "label": "Aadhaar Done",        "fieldtype": "Int",     "width": 105},
        {"fieldname": "income_step",       "label": "Income Done",         "fieldtype": "Int",     "width": 100},
        {"fieldname": "cmchis_applied",    "label": "→ Applied",           "fieldtype": "Int",     "width": 85},
        {"fieldname": "cmchis_active",     "label": "→ Active",            "fieldtype": "Int",     "width": 80},
        {"fieldname": "rejected",          "label": "→ Rejected",          "fieldtype": "Int",     "width": 90},
        {"fieldname": "stage",             "label": "Stage",               "fieldtype": "Data",    "width": 180},
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

    # ── Visited HH query ──────────────────────────────────────────────────────
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

    # ── Bucket transitions for the day (from WRP Status Log) ─────────────────
    # Build: {hh_name → best_transition_category}
    log_cond = ""
    log_vals = {"date": date_filter}
    if org_vals:
        log_cond += " AND log.implementing_org = %(user_org)s"
        log_vals["user_org"] = org_vals["user_org"]
    if filters.get("intervention_unit"):
        log_cond += " AND log.intervention_unit = %(intervention_unit)s"
        log_vals["intervention_unit"] = filters["intervention_unit"]
    if filters.get("street"):
        log_cond += " AND log.street_name = %(street)s"
        log_vals["street"] = filters["street"]

    log_rows = frappe.db.sql(
        """
        SELECT hh_name, old_bucket, new_bucket
        FROM `tabWRP Status Log` log
        WHERE DATE(log.changed_at) = %(date)s
          AND log.old_bucket IS NOT NULL AND log.old_bucket != ''
          {cond}
        """.format(cond=log_cond),
        log_vals,
        as_dict=True,
    )

    # Keep only the highest-priority transition per HH
    hh_transition = {}
    for lr in log_rows:
        cat = _classify_transition(lr.get("old_bucket"), lr.get("new_bucket"))
        if not cat:
            continue
        hh = lr["hh_name"]
        if hh not in hh_transition or \
                TRANS_PRIORITY.get(cat, 0) > TRANS_PRIORITY.get(hh_transition[hh], 0):
            hh_transition[hh] = cat

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
        hh_name = r.get("hh_name")
        co_groups[co_id]["hhs"].append({
            "hh_name":    hh_name,
            "respondent": r.get("hh_respondent") or hh_name or "",
            "street":     r.get("street_label") or "",
            "stage":      _hh_stage(r.get("hh_cmchis"), r.get("max_visits"), r.get("has_closer")),
            "vtype":      vtype,
            "transition": hh_transition.get(hh_name),
        })

    # ── Build output rows ─────────────────────────────────────────────────────
    EMPTY = {
        "intervention_unit": "", "street": "",
        "target": "", "coverage_pct": "",
        "first_visits": "", "doc_followups": "", "regular_followups": "",
        "docs_completed": "", "aadhaar_step": "", "income_step": "",
        "cmchis_applied": "", "cmchis_active": "", "rejected": "",
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

        trans_counts = {c: sum(1 for h in hhs if h["transition"] == c) for c in TRANS_COLS}

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
            "docs_completed":    trans_counts["docs_completed"] or "",
            "aadhaar_step":      trans_counts["aadhaar_step"]   or "",
            "income_step":       trans_counts["income_step"]    or "",
            "cmchis_applied":    trans_counts["cmchis_applied"] or "",
            "cmchis_active":     trans_counts["cmchis_active"]  or "",
            "rejected":          trans_counts["rejected"]       or "",
            "stage":             "",
            "indent":            0,
            "bold":              1,
        })

        for hh in hhs:
            row = dict(EMPTY)
            t = hh["transition"]
            row.update({
                "label":  hh["respondent"],
                "street": hh["street"],
                "visited": "",
                "first_visits":      1 if hh["vtype"] == "first"   else "",
                "doc_followups":     1 if hh["vtype"] == "doc"     else "",
                "regular_followups": 1 if hh["vtype"] == "regular" else "",
                "docs_completed":    1 if t == "docs_completed" else "",
                "aadhaar_step":      1 if t == "aadhaar_step"   else "",
                "income_step":       1 if t == "income_step"    else "",
                "cmchis_applied":    1 if t == "cmchis_applied" else "",
                "cmchis_active":     1 if t == "cmchis_active"  else "",
                "rejected":          1 if t == "rejected"       else "",
                "stage":  hh["stage"],
                "indent": 1,
                "bold":   0,
            })
            data.append(row)

    return data
