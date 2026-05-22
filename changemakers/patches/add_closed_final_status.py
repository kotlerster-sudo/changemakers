"""
Add a 'closed' final_status row to every Entitlement Config that doesn't
already have one. AC coordinators use this to mark beneficiaries whose
case can't progress (houses locked, members unreachable, documents
unobtainable after multiple attempts by COs and ACs).

Idempotent. Safe to re-run.
"""
import frappe

CLOSED_ROW = {
    "status_value":    "closed",
    "label":           "Closed – Unreachable / No Docs",
    "is_goal":         0,
    "is_negative":     1,
    "requires_unlock": 0,
    "color":           "grey",
    "sort_order":      99,
}


def execute():
    if not frappe.db.exists("DocType", "Entitlement Final Status"):
        return

    configs = frappe.get_all("Entitlement Config", pluck="name")
    for config_name in configs:
        existing = frappe.db.exists(
            "Entitlement Final Status",
            {
                "parent":     config_name,
                "parenttype": "Entitlement Config",
                "status_value": "closed",
            },
        )
        if existing:
            continue

        frappe.get_doc({
            "doctype":     "Entitlement Final Status",
            "parent":      config_name,
            "parenttype":  "Entitlement Config",
            "parentfield": "final_statuses",
            **CLOSED_ROW,
        }).insert(ignore_permissions=True)

    frappe.db.commit()
    frappe.logger().info(
        f"add_closed_final_status: ensured 'closed' option on {len(configs)} entitlement config(s)"
    )
