"""
Seeds CMCHIS as Entitlement Config E1.

This is the canonical translation of the current WRP hardcoded logic into
the generic entitlement config system. Run once; idempotent on re-run.

Doc slots:
  doc1 → Aadhaar Card     (SLA 15 days, required for unlock)
  doc2 → Income Certificate (SLA 4 days, required for unlock)

Final status:
  not_applied → Applied (ETA 5d) → Active (goal) | Rejected
"""
import frappe


def execute():
    if frappe.db.exists("Entitlement Config", "E1"):
        return  # Already seeded

    doc = frappe.get_doc({
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

        # ── Doc Slot 1: Aadhaar ───────────────────────────────────────────────
        "doc_slots": [
            {
                "slot_number":         1,
                "slot_key":            "doc1",
                "label":               "Aadhaar Card",
                "sla_days":            15,
                "required_for_unlock": 1,
                "statuses": [
                    {"status_value": "missing",            "label": "Missing",                         "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
                    {"status_value": "external_needed",    "label": "External Aadhaar Needed",         "is_terminal": 0, "starts_sla": 0, "color": "orange", "sort_order": 2},
                    {"status_value": "external_applied",   "label": "External Applied (ETA 15d)",      "is_terminal": 0, "starts_sla": 1, "color": "orange", "sort_order": 3},
                    {"status_value": "internal_applied",   "label": "Internal Applied",                "is_terminal": 0, "starts_sla": 1, "color": "blue",   "sort_order": 4},
                    {"status_value": "correction_needed",  "label": "Correction Needed",               "is_terminal": 0, "starts_sla": 0, "color": "red",    "sort_order": 5},
                    {"status_value": "received",           "label": "Aadhaar Received",                "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 6},
                ],
            },
            # ── Doc Slot 2: Income Certificate ────────────────────────────────
            {
                "slot_number":         2,
                "slot_key":            "doc2",
                "label":               "Income Certificate",
                "sla_days":            4,
                "required_for_unlock": 1,
                "statuses": [
                    {"status_value": "not_applied",  "label": "Not Applied",              "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
                    {"status_value": "applied",      "label": "Applied (ETA 4d)",         "is_terminal": 0, "starts_sla": 1, "color": "orange", "sort_order": 2},
                    {"status_value": "received",     "label": "Income Cert Received",     "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 3},
                    {"status_value": "expired",      "label": "Income Cert Expired",      "is_terminal": 1, "starts_sla": 0, "color": "orange", "sort_order": 4},
                ],
            },
        ],

        # ── Final statuses ────────────────────────────────────────────────────
        "final_statuses": [
            {"status_value": "not_applied", "label": "Not Applied",          "is_goal": 0, "is_negative": 0, "requires_unlock": 0, "color": "grey",   "sort_order": 1},
            {"status_value": "applied",     "label": "CMCHIS Applied (ETA 5d)", "is_goal": 0, "is_negative": 0, "requires_unlock": 1, "color": "blue",   "sort_order": 2},
            {"status_value": "active",      "label": "CMCHIS Active",        "is_goal": 1, "is_negative": 0, "requires_unlock": 1, "color": "green",  "sort_order": 3},
            {"status_value": "rejected",    "label": "CMCHIS Rejected",      "is_goal": 0, "is_negative": 1, "requires_unlock": 0, "color": "red",    "sort_order": 4},
        ],
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger().info("Seeded Entitlement Config E1 (CMCHIS)")
