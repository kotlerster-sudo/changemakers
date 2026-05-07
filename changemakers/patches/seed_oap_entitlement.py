"""
Seeds Old Age Pension (SSNMSY) as Entitlement Config E2.
Idempotent: creates config if missing, always ensures Doc Slot Status rows
exist (Frappe does not insert nested child tables automatically).
"""
import frappe

SLOT_STATUSES = {
    "doc1_status": [
        {"status_value": "not_checked", "label": "Not Checked",             "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
        {"status_value": "present",     "label": "Name on Ration Card",     "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 2},
        {"status_value": "absent",      "label": "Name Not on Ration Card", "is_terminal": 1, "starts_sla": 0, "color": "red",    "sort_order": 3},
    ],
    "doc2_status": [
        {"status_value": "not_checked",         "label": "Not Checked",                         "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
        {"status_value": "valid",               "label": "Aadhaar Valid",                       "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 2},
        {"status_value": "internal_correction", "label": "Internal Correction Initiated (~7d)", "is_terminal": 0, "starts_sla": 1, "color": "blue",   "sort_order": 3},
        {"status_value": "external_correction", "label": "Camp / e-Seva Scheduled (~14d)",      "is_terminal": 0, "starts_sla": 1, "color": "purple", "sort_order": 4},
        {"status_value": "corrected",           "label": "Aadhaar Corrected",                   "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 5},
    ],
    "doc3_status": [
        {"status_value": "not_checked",    "label": "Not Checked",                    "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
        {"status_value": "active",         "label": "Active Bank Account",            "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 2},
        {"status_value": "dormant",        "label": "Dormant - Reactivation Pending", "is_terminal": 0, "starts_sla": 1, "color": "orange", "sort_order": 3},
        {"status_value": "pan_pending",    "label": "No Account - PAN Pending",       "is_terminal": 0, "starts_sla": 1, "color": "orange", "sort_order": 4},
        {"status_value": "account_opening","label": "Account Opening in Progress",    "is_terminal": 0, "starts_sla": 1, "color": "blue",   "sort_order": 5},
        {"status_value": "account_opened", "label": "Account Opened and Active",      "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 6},
    ],
}


def execute():
    if not frappe.db.exists("DocType", "Entitlement Config"):
        return

    if not frappe.db.exists("Entitlement Config", "E2"):
        frappe.get_doc({
            "doctype":            "Entitlement Config",
            "entitlement_code":   "E2",
            "entitlement_name":   "Old Age Pension (SSNMSY)",
            "enabled":            1,
            "geography":          "Chennai",
            "beneficiary_unit":   "Individual",
            "doc_tracking_level": "Individual",
            "final_status_at":    "Individual",
            "max_doc_slots":      3,
            "final_status_label": "Pension Status",
            "unlock_rule":        "ALL_REQUIRED_TERMINAL",
            "goal_status_value":  "active",
            "doc_slots": [
                {"slot_number": 1, "slot_key": "doc1_status", "label": "Ration Card",   "sla_days": 0,  "required_for_unlock": 1},
                {"slot_number": 2, "slot_key": "doc2_status", "label": "Aadhaar",       "sla_days": 14, "required_for_unlock": 1},
                {"slot_number": 3, "slot_key": "doc3_status", "label": "Bank Account",  "sla_days": 10, "required_for_unlock": 1},
            ],
            "final_statuses": [
                {"status_value": "not_applied", "label": "Not Applied",              "is_goal": 0, "is_negative": 0, "requires_unlock": 0, "color": "grey",  "sort_order": 1},
                {"status_value": "applied",     "label": "Applied on e-Sevai (30d)", "is_goal": 0, "is_negative": 0, "requires_unlock": 1, "color": "blue",  "sort_order": 2},
                {"status_value": "active",      "label": "Pension Active",           "is_goal": 1, "is_negative": 0, "requires_unlock": 1, "color": "green", "sort_order": 3},
                {"status_value": "rejected",    "label": "Application Rejected",     "is_goal": 0, "is_negative": 1, "requires_unlock": 0, "color": "red",   "sort_order": 4},
            ],
        }).insert(ignore_permissions=True)

    _ensure_slot_statuses("E2", SLOT_STATUSES)
    frappe.db.commit()
    frappe.logger().info("Seeded/verified Entitlement Config E2 (Old Age Pension)")


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
