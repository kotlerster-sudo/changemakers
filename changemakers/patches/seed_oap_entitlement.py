"""
Seeds Old Age Pension (SSNMSY) as Entitlement Config E2.

Eligibility: age 60+, not receiving other govt pension, Aadhaar valid,
name on ration card, active bank account.

Doc slots:
  doc1 → Ration Card inclusion (gate: blocked if absent)
  doc2 → Aadhaar validity / correction (SLA 14 days)
  doc3 → Bank Account status (SLA 10 days)

Final status (Individual-level — one person per application):
  not_applied → applied (e-Sevai, 30 working days) → active (goal) | rejected
"""
import frappe


def execute():
    if not frappe.db.exists("DocType", "Entitlement Config"):
        return
    if frappe.db.exists("Entitlement Config", "E2"):
        return

    doc = frappe.get_doc({
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

        # ── Doc Slot 1: Ration Card ───────────────────────────────────────────
        "doc_slots": [
            {
                "slot_number":         1,
                "slot_key":            "doc1",
                "label":               "Ration Card",
                "sla_days":            0,
                "required_for_unlock": 1,
                "statuses": [
                    {"status_value": "not_checked", "label": "Not Checked",              "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
                    {"status_value": "present",     "label": "Name on Ration Card",      "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 2},
                    {"status_value": "absent",      "label": "Name Not on Ration Card",  "is_terminal": 1, "starts_sla": 0, "color": "red",    "sort_order": 3},
                ],
            },

            # ── Doc Slot 2: Aadhaar ───────────────────────────────────────────
            {
                "slot_number":         2,
                "slot_key":            "doc2",
                "label":               "Aadhaar",
                "sla_days":            14,
                "required_for_unlock": 1,
                "statuses": [
                    {"status_value": "not_checked",          "label": "Not Checked",                         "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
                    {"status_value": "valid",                "label": "Aadhaar Valid",                       "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 2},
                    {"status_value": "internal_correction",  "label": "Internal Correction Initiated (~7d)", "is_terminal": 0, "starts_sla": 1, "color": "blue",   "sort_order": 3},
                    {"status_value": "external_correction",  "label": "Camp / e-Seva Scheduled (~14d)",      "is_terminal": 0, "starts_sla": 1, "color": "purple", "sort_order": 4},
                    {"status_value": "corrected",            "label": "Aadhaar Corrected",                   "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 5},
                ],
            },

            # ── Doc Slot 3: Bank Account ──────────────────────────────────────
            {
                "slot_number":         3,
                "slot_key":            "doc3",
                "label":               "Bank Account",
                "sla_days":            10,
                "required_for_unlock": 1,
                "statuses": [
                    {"status_value": "not_checked",      "label": "Not Checked",                     "is_terminal": 0, "starts_sla": 0, "color": "grey",   "sort_order": 1},
                    {"status_value": "active",           "label": "Active Bank Account",             "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 2},
                    {"status_value": "dormant",          "label": "Dormant – Reactivation Pending",  "is_terminal": 0, "starts_sla": 1, "color": "orange", "sort_order": 3},
                    {"status_value": "pan_pending",      "label": "No Account – PAN Pending",        "is_terminal": 0, "starts_sla": 1, "color": "orange", "sort_order": 4},
                    {"status_value": "account_opening",  "label": "Account Opening in Progress",     "is_terminal": 0, "starts_sla": 1, "color": "blue",   "sort_order": 5},
                    {"status_value": "account_opened",   "label": "Account Opened & Active",         "is_terminal": 1, "starts_sla": 0, "color": "green",  "sort_order": 6},
                ],
            },
        ],

        # ── Final statuses ────────────────────────────────────────────────────
        "final_statuses": [
            {"status_value": "not_applied", "label": "Not Applied",              "is_goal": 0, "is_negative": 0, "requires_unlock": 0, "color": "grey",   "sort_order": 1},
            {"status_value": "applied",     "label": "Applied on e-Sevai (30d)", "is_goal": 0, "is_negative": 0, "requires_unlock": 1, "color": "blue",   "sort_order": 2},
            {"status_value": "active",      "label": "Pension Active",           "is_goal": 1, "is_negative": 0, "requires_unlock": 1, "color": "green",  "sort_order": 3},
            {"status_value": "rejected",    "label": "Application Rejected",     "is_goal": 0, "is_negative": 1, "requires_unlock": 0, "color": "red",    "sort_order": 4},
        ],
    })

    doc.insert(ignore_permissions=True)
    frappe.db.commit()
    frappe.logger().info("Seeded Entitlement Config E2 (Old Age Pension)")
