"""
Force-writes the updated filter definitions for WRP Saturation Progress
directly into the Report doc's filters_json column.

Changes vs the original:
  - AC filter: Link → Data (free-text LIKE match on sl.ac_alloted)
  - Implementing Org filter preserved as Data
  - Assembly Constituency filter removed
"""
import frappe
import json

REPORT = "WRP Saturation Progress"

FILTERS = [
    {
        "fieldname": "co",
        "fieldtype": "Link",
        "label": "Community Organiser",
        "mandatory": 0,
        "options": "Staff details - WRP",
        "wildcard_filter": 0,
    },
    {
        "fieldname": "ac",
        "fieldtype": "Data",
        "label": "Area Coordinator (name)",
        "mandatory": 0,
        "wildcard_filter": 0,
    },
    {
        "fieldname": "pm",
        "fieldtype": "Link",
        "label": "Programme Manager",
        "mandatory": 0,
        "options": "Staff details - WRP",
        "wildcard_filter": 0,
    },
    {
        "fieldname": "street",
        "fieldtype": "Link",
        "label": "Street",
        "mandatory": 0,
        "options": "Street List  - WRP",
        "wildcard_filter": 0,
    },
    {
        "fieldname": "intervention_unit",
        "fieldtype": "Link",
        "label": "Intervention Unit / Settlement",
        "mandatory": 0,
        "options": "Intervention Units-WRP",
        "wildcard_filter": 0,
    },
    {
        "fieldname": "implementing_org",
        "fieldtype": "Data",
        "label": "Implementing Organisation (partial name)",
        "mandatory": 0,
        "wildcard_filter": 0,
    },
    {
        "fieldname": "from_date",
        "fieldtype": "Date",
        "label": "From Date",
        "mandatory": 0,
        "wildcard_filter": 0,
    },
    {
        "fieldname": "to_date",
        "fieldtype": "Date",
        "label": "To Date",
        "mandatory": 0,
        "wildcard_filter": 0,
    },
]


def execute():
    if not frappe.db.exists("Report", REPORT):
        return

    # 1. Force reload from module JSON first
    try:
        frappe.reload_doc("Frappe Changemakers", "Report", REPORT, force=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "reload_doc WRP Saturation Progress v2")

    # 2. Directly write filters_json — survives any future module sync
    frappe.db.set_value(
        "Report",
        REPORT,
        "filters_json",
        json.dumps(FILTERS),
    )

    # 3. Also delete the child-table filter rows and re-insert (belt + suspenders)
    frappe.db.sql(
        "DELETE FROM `tabReport Filter` WHERE parent = %s", (REPORT,)
    )
    for idx, f in enumerate(FILTERS, start=1):
        frappe.db.sql(
            """
            INSERT INTO `tabReport Filter`
                (name, creation, modified, modified_by, owner,
                 parent, parentfield, parenttype, idx,
                 fieldname, fieldtype, label, mandatory, options, wildcard_filter)
            VALUES
                (%s, NOW(), NOW(), 'Administrator', 'Administrator',
                 %s, 'filters', 'Report', %s,
                 %s, %s, %s, %s, %s, %s)
            """,
            (
                frappe.generate_hash(length=10),
                REPORT,
                idx,
                f["fieldname"],
                f["fieldtype"],
                f["label"],
                f.get("mandatory", 0),
                f.get("options", "") or "",
                f.get("wildcard_filter", 0),
            ),
        )

    frappe.db.commit()
