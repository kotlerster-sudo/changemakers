import frappe


def execute():
    """Clear any DB-saved scripts on our standard reports so they use the module files."""
    for report_name in ("CO CMCHIS Performance", "CMCHIS Delay Analysis"):
        if frappe.db.exists("Report", report_name):
            frappe.db.set_value(
                "Report",
                report_name,
                {"report_script": "", "is_standard": "Yes"},
                update_modified=False,
            )
    frappe.db.commit()
