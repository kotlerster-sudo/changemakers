import frappe


def execute():
    """Add 'Income Cert Expired' option to income_status field on Individual Profile-WRP."""
    new_option = "Income Cert Expired"

    # Try as a Custom Field first, then as a standard DocField
    cf = frappe.db.get_value(
        "Custom Field",
        {"dt": "Individual Profile-WRP", "fieldname": "income_status"},
        ["name", "options"],
        as_dict=True,
    )
    if cf:
        if new_option not in (cf.options or ""):
            frappe.db.set_value(
                "Custom Field", cf.name, "options",
                (cf.options or "") + "\n" + new_option,
                update_modified=False,
            )
            frappe.db.commit()
        return

    df = frappe.db.get_value(
        "DocField",
        {"parent": "Individual Profile-WRP", "fieldname": "income_status"},
        ["name", "options"],
        as_dict=True,
    )
    if df and new_option not in (df.options or ""):
        frappe.db.set_value(
            "DocField", df.name, "options",
            (df.options or "") + "\n" + new_option,
            update_modified=False,
        )
        frappe.db.commit()
