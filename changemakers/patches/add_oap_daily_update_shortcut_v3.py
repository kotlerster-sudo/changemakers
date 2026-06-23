import frappe
import json

# setup_entitlement_dashboards rebuilds workspace `content` to only the dashboard
# custom_block, which dropped the Daily Update Report shortcut that
# set_wrp_report_roles_v2 had added (it survived only in the shortcuts child).
# Re-add it to the rendered content idempotently so MIS/PM see it.

REPORT = "Entitlement Daily Update Report"
WORKSPACES = ["OAP MIS Dashboard", "OAP Programme Dashboard"]


def execute():
    if not frappe.db.exists("Report", REPORT):
        return
    for ws in WORKSPACES:
        if frappe.db.exists("Workspace", ws):
            _ensure(ws)
    frappe.db.commit()


def _ensure(ws):
    doc = frappe.get_doc("Workspace", ws)

    if REPORT not in {s.link_to for s in doc.shortcuts}:
        doc.append("shortcuts", {
            "label": "Daily Update Report",
            "link_to": REPORT,
            "type": "Report",
            "color": "Blue",
        })

    content = json.loads(doc.content or "[]")
    names = {i.get("data", {}).get("shortcut_name")
             for i in content if i.get("type") == "shortcut"}
    if REPORT not in names:
        content += [
            {"id": "oap_daily_h", "type": "paragraph",
             "data": {"text": "Daily Tracking", "col": 12}},
            {"id": "oap_daily_s", "type": "shortcut",
             "data": {"shortcut_name": REPORT, "col": 4}},
        ]
        doc.content = json.dumps(content)

    _old = frappe.flags.ignore_links
    frappe.flags.ignore_links = True
    try:
        doc.save(ignore_permissions=True)
    finally:
        frappe.flags.ignore_links = _old
