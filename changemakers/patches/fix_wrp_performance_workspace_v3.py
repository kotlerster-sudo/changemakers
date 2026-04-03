import frappe
import json


def execute():
    """Force WRP Performance workspace settings, shortcuts and content via direct DB."""
    if not frappe.db.exists("Workspace", "WRP Performance"):
        return

    # Update scalar fields directly — avoids link validation on parent_page
    frappe.db.set_value(
        "Workspace",
        "WRP Performance",
        {
            "parent_page": "WRP",
            "public": 1,
            "is_hidden": 0,
            "for_user": "",
            "module": "Frappe Changemakers",
            "hide_custom": 0,
            "content": json.dumps([
                {"id": "wrp_h1", "type": "header", "data": {
                    "text": "<span class=\"h4\">WRP Performance</span>", "col": 12}},
                {"id": "wrp_p1", "type": "paragraph", "data": {
                    "text": "CMCHIS progress and pipeline bottleneck tracking.", "col": 12}},
                {"id": "wrp_p2", "type": "paragraph", "data": {
                    "text": "Performance", "col": 12}},
                {"id": "wrp_s1", "type": "shortcut", "data": {
                    "shortcut_name": "CO CMCHIS Performance", "col": 4}},
                {"id": "wrp_p3", "type": "paragraph", "data": {
                    "text": "Delay & Bottleneck Analysis", "col": 12}},
                {"id": "wrp_s2", "type": "shortcut", "data": {
                    "shortcut_name": "CMCHIS Delay Analysis", "col": 4}},
            ]),
        },
        update_modified=False,
    )

    # Ensure both shortcuts exist in the child table
    for shortcut in [
        {"label": "CO CMCHIS Performance", "link_to": "CO CMCHIS Performance",
         "type": "Report", "color": "Blue"},
        {"label": "CMCHIS Delay Analysis", "link_to": "CMCHIS Delay Analysis",
         "type": "Report", "color": "Orange"},
    ]:
        already_exists = frappe.db.sql(
            "SELECT name FROM `tabWorkspace Shortcut` WHERE parent=%s AND link_to=%s LIMIT 1",
            ("WRP Performance", shortcut["link_to"]),
        )
        if not already_exists:
            frappe.db.sql(
                """INSERT INTO `tabWorkspace Shortcut`
                   (name, parent, parenttype, parentfield, idx, label, link_to, type, color)
                   VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
                (
                    frappe.generate_hash(length=10),
                    "WRP Performance", "Workspace", "shortcuts", 0,
                    shortcut["label"], shortcut["link_to"],
                    shortcut["type"], shortcut["color"],
                ),
            )

    frappe.db.commit()
