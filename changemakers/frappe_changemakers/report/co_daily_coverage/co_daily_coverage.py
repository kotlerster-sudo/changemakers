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


def execute(filters=None):
    filters = filters or {}
    if not filters.get("date"):
        filters["date"] = nowdate()
    columns = get_columns()
    data = get_data(filters)
    return columns, data


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


def _stage_label(visit_count, aadhaar_status, income_status, hh_cmchis):
    c = (hh_cmchis or "").lower()
    if "active" in c:
        return "CMCHIS Active"
    if "rejected" in c:
        return "Rejected"
    if "applied" in c and "not" not in c:
        return "Applied"
    if visit_count == 1:
        return "First Visit"
    has_a = "Received" in (aadhaar_status or "")
    has_i = "Received" in (income_status or "")
    if has_a and has_i:
        return "Docs Ready – Follow-up"
    return "Pending Docs – Follow-up"


def _visit_type(visit_count, aadhaar_status, income_status):
    """Classify visit into the three daily-plan bucket types."""
    if (visit_count or 0) == 1:
        return "first"
    if "Received" in (aadhaar_status or "") and "Received" in (income_status or ""):
        return "doc"
    return "regular"


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

    rows = frappe.db.sql(
        """
        SELECT
            ind.name              AS ind_id,
            ind.name_of_the_individual AS ind_name,
            ind.visit_count,
            ind.aadhaar_status,
            ind.income_status,
            ind.last_visited_at,
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
        ORDER BY staff.full_name, sl.street_name, ind.name_of_the_individual
        """.format(cond=cond),
        vals,
        as_dict=True,
    )

    if not rows:
        return []

    # Group by CO
    co_groups = {}
    co_order = []
    for r in rows:
        co_id = r.get("co_id") or "Unassigned"
        if co_id not in co_groups:
            co_groups[co_id] = {
                "co_name": r.get("co_name") or co_id,
                "iu": r.get("iu_label") or r.get("iu_name") or "",
                "households": [],
            }
            co_order.append(co_id)
        co_groups[co_id]["households"].append(r)

    data = []
    for co_id in co_order:
        co = co_groups[co_id]
        hh_list = co["households"]
        visited = len(hh_list)

        first_v = sum(1 for h in hh_list if _visit_type(h.visit_count, h.aadhaar_status, h.income_status) == "first")
        doc_v   = sum(1 for h in hh_list if _visit_type(h.visit_count, h.aadhaar_status, h.income_status) == "doc")
        reg_v   = visited - first_v - doc_v

        # CO summary row
        data.append({
            "label":             co["co_name"],
            "intervention_unit": co["iu"],
            "street":            "",
            "visited":           visited,
            "target":            30,
            "coverage_pct":      round(visited / 30 * 100, 1),
            "first_visits":      first_v,
            "doc_followups":     doc_v,
            "regular_followups": reg_v,
            "stage":             "",
            "indent":            0,
            "bold":              1,
        })

        # Household detail rows
        for h in hh_list:
            vc = int(h.get("visit_count") or 0)
            stage = _stage_label(vc, h.aadhaar_status, h.income_status, h.hh_cmchis)
            vtype = _visit_type(vc, h.aadhaar_status, h.income_status)
            data.append({
                "label":             h.get("ind_name") or h.get("hh_respondent") or h.get("ind_id"),
                "intervention_unit": "",
                "street":            h.get("street_label") or h.get("hh_street") or "",
                "visited":           1,
                "target":            "",
                "coverage_pct":      "",
                "first_visits":      1 if vtype == "first" else "",
                "doc_followups":     1 if vtype == "doc" else "",
                "regular_followups": 1 if vtype == "regular" else "",
                "stage":             stage,
                "indent":            1,
                "bold":              0,
            })

    return data
