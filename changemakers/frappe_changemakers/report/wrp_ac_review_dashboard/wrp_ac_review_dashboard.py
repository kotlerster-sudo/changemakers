import frappe


def execute(filters=None):
    filters = filters or {}

    columns = [
        {"label": "Household",       "fieldname": "household",        "fieldtype": "Data",    "width": 140},
        {"label": "Respondent",      "fieldname": "respondent",       "fieldtype": "Data",    "width": 140},
        {"label": "Street",          "fieldname": "street",           "fieldtype": "Data",    "width": 160},
        {"label": "AC",              "fieldname": "ac_alloted",       "fieldtype": "Data",    "width": 130},
        {"label": "CO",              "fieldname": "co",               "fieldtype": "Data",    "width": 130},
        {"label": "Visits",          "fieldname": "visit_count",      "fieldtype": "Int",     "width":  60},
        {"label": "Escalated On",    "fieldname": "escalation_date",  "fieldtype": "Date",    "width": 110},
        {"label": "Days Pending",    "fieldname": "days_pending",     "fieldtype": "Int",     "width":  90},
        {"label": "Status",          "fieldname": "status",           "fieldtype": "Data",    "width": 160},
        {"label": "AC Notes",        "fieldname": "ac_notes",         "fieldtype": "Data",    "width": 200},
        {"label": "Intervention Unit","fieldname": "intervention_unit","fieldtype": "Data",   "width": 140},
        {"label": "Organisation",    "fieldname": "implementing_org", "fieldtype": "Data",    "width": 130},
    ]

    conds = []
    vals = {}

    if filters.get("ac"):
        conds.append("ac_alloted = %(ac)s")
        vals["ac"] = filters["ac"]

    if filters.get("status"):
        conds.append("status = %(status)s")
        vals["status"] = filters["status"]
    else:
        # Default: show only pending
        conds.append("status = 'Pending AC Review'")

    if filters.get("street"):
        conds.append("street = %(street)s")
        vals["street"] = filters["street"]

    if filters.get("intervention_unit"):
        conds.append("intervention_unit = %(iu)s")
        vals["iu"] = filters["intervention_unit"]

    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    today = frappe.utils.nowdate()

    rows = frappe.db.sql(f"""
        SELECT
            household,
            respondent,
            street,
            ac_alloted,
            co,
            visit_count,
            escalation_date,
            DATEDIFF(%(today)s, escalation_date) AS days_pending,
            status,
            ac_notes,
            intervention_unit,
            implementing_org
        FROM `tabWRP AC Review`
        {where}
        ORDER BY
            FIELD(status, 'Pending AC Review', 'Blocked – No Resolution', 'Cleared – Will Apply'),
            days_pending DESC
    """, {**vals, "today": today}, as_dict=True)

    return columns, rows
