import frappe


def execute():
    """Ensure WRP Performance workspace is public and nested under WRP."""
    if frappe.db.exists("Workspace", "WRP Performance"):
        frappe.db.set_value(
            "Workspace",
            "WRP Performance",
            {
                "parent_page": "WRP",
                "public": 1,
                "is_hidden": 0,
            },
            update_modified=False,
        )
        frappe.db.commit()
