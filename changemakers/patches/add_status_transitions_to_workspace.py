import frappe
import json


def execute():
    """Add WRP Status Transitions shortcut to WRP Performance workspace."""
    if not frappe.db.exists("Workspace", "WRP Performance"):
        return

    doc = frappe.get_doc("Workspace", "WRP Performance")

    existing_links = {s.link_to for s in doc.shortcuts}
    if "WRP Status Transitions" not in existing_links:
        doc.append("shortcuts", {
            "label":   "WRP Status Transitions",
            "link_to": "WRP Status Transitions",
            "type":    "Report",
            "color":   "Red",
        })

    # Rebuild content to include the new shortcut
    content = json.loads(doc.content or "[]")

    # Check if it's already in content
    existing_shortcut_names = {
        item.get("data", {}).get("shortcut_name")
        for item in content
        if item.get("type") == "shortcut"
    }

    if "WRP Status Transitions" not in existing_shortcut_names:
        content += [
            {"id": "wrp_p4", "type": "paragraph", "data": {
                "text": "Status Tracking", "col": 12}},
            {"id": "wrp_s5", "type": "shortcut", "data": {
                "shortcut_name": "WRP Status Transitions", "col": 4}},
        ]
        doc.content = json.dumps(content)

    doc.save(ignore_permissions=True)
    frappe.db.commit()
