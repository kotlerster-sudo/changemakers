"""
Adds two new final statuses to E2 (Old Age Pension SSNMSY):
  - other_pension: Ineligible — Receiving Other Pension (negative, no unlock required)
  - already_active: Already Receiving OAP (goal, no unlock required)
Idempotent: skips if status already exists.
"""
import frappe

NEW_STATUSES = [
    {
        "status_value": "other_pension",
        "label":         "Ineligible — Receiving Other Pension",
        "is_goal":       0,
        "is_negative":   1,
        "requires_unlock": 0,
        "color":         "red",
        "sort_order":    5,
    },
    {
        "status_value": "already_active",
        "label":         "Already Receiving OAP",
        "is_goal":       1,
        "is_negative":   0,
        "requires_unlock": 0,
        "color":         "green",
        "sort_order":    6,
    },
]


def execute():
    if not frappe.db.exists("Entitlement Config", "E2"):
        return

    for s in NEW_STATUSES:
        already = frappe.db.exists(
            "Entitlement Final Status",
            {"parent": "E2", "status_value": s["status_value"]},
        )
        if already:
            continue
        frappe.get_doc({
            "doctype":     "Entitlement Final Status",
            "parent":      "E2",
            "parenttype":  "Entitlement Config",
            "parentfield": "final_statuses",
            **s,
        }).insert(ignore_permissions=True)
        frappe.logger().info(f"Added OAP final status: {s['status_value']}")

    frappe.db.commit()
