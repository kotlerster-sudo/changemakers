import frappe
import json


WRP_ROLES = [
    "System Manager", "Admin (Partner)", "Program Manager",
    "Partner SMT", "WRP-PM", "WRP-AC", "WRP-MIS",
]

REPORT_NAME = "WRP Saturation Progress"


def execute():
    """Add WRP Saturation Progress report roles and workspace shortcut."""

    # ── 1. Set report roles ───────────────────────────────────────────────────
    if frappe.db.exists("Report", REPORT_NAME):
        report = frappe.get_doc("Report", REPORT_NAME)
        existing_roles = {r.role for r in report.roles}
        changed = False
        for role in WRP_ROLES:
            if role not in existing_roles and frappe.db.exists("Role", role):
                report.append("roles", {"role": role})
                changed = True
        if changed:
            report.save(ignore_permissions=True)

    # ── 2. Add workspace shortcut ─────────────────────────────────────────────
    if not frappe.db.exists("Workspace", "WRP Performance"):
        frappe.db.commit()
        return

    doc = frappe.get_doc("Workspace", "WRP Performance")

    existing_links = {s.link_to for s in doc.shortcuts}
    if REPORT_NAME not in existing_links:
        doc.append("shortcuts", {
            "label":   "Saturation Progress",
            "link_to": REPORT_NAME,
            "type":    "Report",
            "color":   "Purple",
        })

    content = json.loads(doc.content or "[]")
    existing_shortcut_names = {
        item.get("data", {}).get("shortcut_name")
        for item in content
        if item.get("type") == "shortcut"
    }

    if REPORT_NAME not in existing_shortcut_names:
        content += [
            {"id": "wrp_sat_h", "type": "paragraph", "data": {
                "text": "Baseline & Progress", "col": 12}},
            {"id": "wrp_sat_s", "type": "shortcut", "data": {
                "shortcut_name": REPORT_NAME, "col": 4}},
        ]
        doc.content = json.dumps(content)

    doc.flags.ignore_links = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
