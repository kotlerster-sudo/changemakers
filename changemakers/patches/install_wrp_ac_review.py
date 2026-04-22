"""
Install WRP AC Review DocType and set report permissions.
Idempotent — safe to run multiple times.
"""
import frappe


def execute():
    # Sync DocType from module JSON
    frappe.reload_doc("frappe_changemakers", "doctype", "wrp_ac_review", force=True)

    # Ensure the Script Report exists with correct roles
    if not frappe.db.exists("Report", "WRP AC Review Dashboard"):
        return

    report = frappe.get_doc("Report", "WRP AC Review Dashboard")
    existing_roles = {r.role for r in report.roles}
    for role in ("WRP-AC", "WRP-PM", "System Manager"):
        if role not in existing_roles:
            report.append("roles", {"role": role})
    report.save(ignore_permissions=True)
    frappe.db.commit()
