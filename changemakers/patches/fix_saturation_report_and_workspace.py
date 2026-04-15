"""
Force-reloads WRP Saturation Progress from its module JSON (picks up
filter changes) and adds the workspace shortcut using direct SQL so
no ORM link-validation can block it.
"""
import frappe
import json


REPORT   = "WRP Saturation Progress"
WS       = "WRP Performance"


def execute():
    # ── 1. Force reload report definition from module JSON ────────────────────
    try:
        frappe.reload_doc("Frappe Changemakers", "Report", REPORT, force=True)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "reload_doc WRP Saturation Progress")

    # ── 2. Workspace shortcut — direct SQL, zero ORM ──────────────────────────
    if not frappe.db.exists("Workspace", WS):
        frappe.db.commit()
        return

    # 2a. shortcuts child table
    exists = frappe.db.sql(
        "SELECT name FROM `tabWorkspace Shortcut` WHERE parent=%s AND link_to=%s LIMIT 1",
        (WS, REPORT),
    )
    if not exists:
        frappe.db.sql(
            """
            INSERT INTO `tabWorkspace Shortcut`
                (name, creation, modified, modified_by, owner,
                 parent, parentfield, parenttype,
                 label, link_to, type, color)
            VALUES
                (%s, NOW(), NOW(), 'Administrator', 'Administrator',
                 %s, 'shortcuts', 'Workspace',
                 'Saturation Progress', %s, 'Report', 'Purple')
            """,
            (frappe.generate_hash(length=10), WS, REPORT),
        )

    # 2b. content JSON
    raw = frappe.db.get_value("Workspace", WS, "content") or "[]"
    try:
        content = json.loads(raw)
    except Exception:
        content = []

    existing = {
        item.get("data", {}).get("shortcut_name")
        for item in content
        if item.get("type") == "shortcut"
    }
    if REPORT not in existing:
        content += [
            {"id": "wrp_sat_h", "type": "paragraph",
             "data": {"text": "Baseline & Progress", "col": 12}},
            {"id": "wrp_sat_s", "type": "shortcut",
             "data": {"shortcut_name": REPORT, "col": 4}},
        ]
        frappe.db.set_value("Workspace", WS, "content", json.dumps(content))

    frappe.db.commit()
