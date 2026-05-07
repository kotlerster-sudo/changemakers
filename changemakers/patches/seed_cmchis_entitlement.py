"""
Seeds CMCHIS as Entitlement Config E1.
Idempotent: creates config if missing, always ensures Doc Slot Status rows
exist (Frappe does not insert nested child tables automatically).
"""
import frappe

SLOT_STATUSES = {
    "doc1": [
        {"status_value": "missing",           "label": "Missing",                    "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
        {"status_value": "external_needed",   "label": "External Aadhaar Needed",    "is_terminal": 0, "starts_sla": 0, "color": "orange", "sort_order": 2},
        {"status_value": "external_applied",  "label": "External Applied (ETA 15d)", "is_terminal": 0, "starts_sla": 1, "color": "orange", "sort_order": 3},
        {"status_value": "internal_applied",  "label": "Internal Applied",           "is_terminal": 0, "starts_sla": 1, "color": "blue",   "sort_order": 4},
        {"status_value": "correction_needed", "label": "Correction Needed",          "is_terminal": 0, "starts_sla": 0, "color": "red",    "sort_order": 5},
        {"status_value": "received",          "label": "Aadhaar Received",           "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 6},
    ],
    "doc2": [
        {"status_value": "not_applied", "label": "Not Applied",          "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
        {"status_value": "applied",     "label": "Applied (ETA 4d)",     "is_terminal": 0, "starts_sla": 1, "color": "orange", "sort_order": 2},
        {"status_value": "received",    "label": "Income Cert Received", "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 3},
        {"status_value": "expired",     "label": "Income Cert Expired",  "is_terminal": 1, "starts_sla": 0, "color": "orange", "sort_order": 4},
    ],
}


def execute():
    if not frappe.db.exists("DocType", "Entitlement Config"):
        return

    if not frappe.db.exists("Entitlement Config", "E1"):
        frappe.get_doc({
            "doctype":             "Entitlement Config",
            "entitlement_code":    "E1",
            "entitlement_name":    "CMCHIS",
            "enabled":             1,
            "geography":           "Chennai",
            "beneficiary_unit":    "Individual",
            "doc_tracking_level":  "Individual",
            "final_status_at":     "Household",
            "max_doc_slots":       2,
            "final_status_label":  "CMCHIS Status",
            "unlock_rule":         "ALL_REQUIRED_TERMINAL",
            "goal_status_value":   "active",
            "doc_slots": [
                {"slot_number": 1, "slot_key": "doc1", "label": "Aadhaar Card",        "sla_days": 15, "required_for_unlock": 1},
                {"slot_number": 2, "slot_key": "doc2", "label": "Income Certificate",  "sla_days": 4,  "required_for_unlock": 1},
            ],
            "final_statuses": [
                {"status_value": "not_applied", "label": "Not Applied",             "is_goal": 0, "is_negative": 0, "requires_unlock": 0, "color": "grey",  "sort_order": 1},
                {"status_value": "applied",     "label": "CMCHIS Applied (ETA 5d)", "is_goal": 0, "is_negative": 0, "requires_unlock": 1, "color": "blue",  "sort_order": 2},
                {"status_value": "active",      "label": "CMCHIS Active",           "is_goal": 1, "is_negative": 0, "requires_unlock": 1, "color": "green", "sort_order": 3},
                {"status_value": "rejected",    "label": "CMCHIS Rejected",         "is_goal": 0, "is_negative": 1, "requires_unlock": 0, "color": "red",   "sort_order": 4},
            ],
        }).insert(ignore_permissions=True)

    _ensure_slot_statuses("E1", SLOT_STATUSES)
    frappe.db.commit()
    frappe.logger().info("Seeded/verified Entitlement Config E1 (CMCHIS)")


def _ensure_slot_statuses(config_code, slot_statuses_map):
    slots = frappe.get_all(
        "Entitlement Doc Slot",
        filters={"parent": config_code, "parenttype": "Entitlement Config"},
        fields=["name", "slot_key"],
    )
    for slot in slots:
        statuses = slot_statuses_map.get(slot.slot_key, [])
        if not statuses:
            continue
        existing = frappe.db.count("Doc Slot Status", {"parent": slot.name})
        if existing == len(statuses):
            continue
        frappe.db.delete("Doc Slot Status", {"parent": slot.name})
        for s in statuses:
            frappe.get_doc({
                "doctype":     "Doc Slot Status",
                "parent":      slot.name,
                "parenttype":  "Entitlement Doc Slot",
                "parentfield": "statuses",
                **s,
            }).insert(ignore_permissions=True)
