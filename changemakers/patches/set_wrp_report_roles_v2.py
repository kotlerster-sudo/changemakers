import frappe
import json


def execute():
    reports = [
        "CO CMCHIS Performance",
        "CMCHIS Pipeline Dashboard",
        "CO Daily Coverage",
        "CMCHIS Delay Analysis",
        "WRP Status Transitions",
        "WRP Saturation Progress",
    ]
    roles = [
        "System Manager",
        "Admin (Partner)",
        "Program Manager",
        "Partner SMT",
        "WRP-PM",
        "WRP-AC",
        "WRP-MIS",
    ]

    for report_name in reports:
        if not frappe.db.exists("Report", report_name):
            continue

        # Fetch roles already in the DB for this report
        existing = {
            r[0] for r in frappe.db.sql(
                "SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='Report'",
                report_name
            )
        }

        for role in roles:
            if role in existing:
                continue
            frappe.db.sql("""
                INSERT INTO `tabHas Role`
                    (name, creation, modified, modified_by, owner,
                     parent, parentfield, parenttype, role)
                VALUES
                    (%s, NOW(), NOW(), 'Administrator', 'Administrator',
                     %s, 'roles', 'Report', %s)
            """, (frappe.generate_hash(length=10), report_name, role))

    frappe.db.commit()

    # ── Ensure WRP Saturation Progress shortcut is in WRP Performance workspace ──
    _ensure_saturation_shortcut()


def _ensure_saturation_shortcut():
    report_name = "WRP Saturation Progress"
    if not frappe.db.exists("Workspace", "WRP Performance"):
        return

    doc = frappe.get_doc("Workspace", "WRP Performance")

    existing_links = {s.link_to for s in doc.shortcuts}
    if report_name not in existing_links:
        doc.append("shortcuts", {
            "label":   "Saturation Progress",
            "link_to": report_name,
            "type":    "Report",
            "color":   "Purple",
        })

    content = json.loads(doc.content or "[]")
    existing_names = {
        item.get("data", {}).get("shortcut_name")
        for item in content
        if item.get("type") == "shortcut"
    }
    if report_name not in existing_names:
        content += [
            {"id": "wrp_sat_h", "type": "paragraph",
             "data": {"text": "Baseline & Progress", "col": 12}},
            {"id": "wrp_sat_s", "type": "shortcut",
             "data": {"shortcut_name": report_name, "col": 4}},
        ]
        doc.content = json.dumps(content)

    doc.flags.ignore_links = True
    doc.save(ignore_permissions=True)
    frappe.db.commit()
