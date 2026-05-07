"""
Seeds Entitlement Role Config mappings for WRP roles.
Idempotent — skips existing mappings.
"""
import frappe

ROLE_MAPPINGS = [
    {"role": "WRP-PM",  "access_level": "Programme Manager", "geography": "Chennai"},
    {"role": "WRP-MIS", "access_level": "MIS",               "geography": "Chennai"},
    {"role": "WRP-AC",  "access_level": "Area Coordinator",  "geography": "Chennai"},
    {"role": "WRP-HR",  "access_level": "HR",                "geography": "Chennai"},
]


def execute():
    if not frappe.db.exists("DocType", "Entitlement Role Config"):
        return

    for m in ROLE_MAPPINGS:
        if frappe.db.exists("Entitlement Role Config", m["role"]):
            continue
        frappe.get_doc({
            "doctype":      "Entitlement Role Config",
            "role":         m["role"],
            "access_level": m["access_level"],
            "geography":    m["geography"],
        }).insert(ignore_permissions=True)

    frappe.db.commit()
    frappe.logger().info("Seeded Entitlement Role Config for WRP roles")
