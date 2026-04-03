import frappe


def execute():
    """Force WRP Performance workspace to be public, under WRP, module Frappe Changemakers."""
    if not frappe.db.exists("Workspace", "WRP Performance"):
        return

    frappe.db.set_value(
        "Workspace",
        "WRP Performance",
        {
            "parent_page": "WRP",
            "public": 1,
            "is_hidden": 0,
            "for_user": "",
            "module": "Frappe Changemakers",
            "hide_custom": 0,
        },
        update_modified=False,
    )
    frappe.db.commit()
