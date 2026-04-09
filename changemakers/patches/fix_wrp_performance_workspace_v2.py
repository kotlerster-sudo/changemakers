import frappe
import json


def execute():
    """Force WRP Performance workspace settings, shortcuts and content."""
    if not frappe.db.exists("Workspace", "WRP Performance"):
        return

    doc = frappe.get_doc("Workspace", "WRP Performance")

    # Core settings
    doc.parent_page = "WRP"
    doc.public = 1
    doc.is_hidden = 0
    doc.for_user = ""
    doc.module = "Frappe Changemakers"
    doc.hide_custom = 0

    # Ensure both report shortcuts exist
    existing_links = {s.link_to for s in doc.shortcuts}

    if "CO CMCHIS Performance" not in existing_links:
        doc.append("shortcuts", {
            "label": "CO CMCHIS Performance",
            "link_to": "CO CMCHIS Performance",
            "type": "Report",
            "color": "Blue",
        })

    if "CMCHIS Delay Analysis" not in existing_links:
        doc.append("shortcuts", {
            "label": "CMCHIS Delay Analysis",
            "link_to": "CMCHIS Delay Analysis",
            "type": "Report",
            "color": "Orange",
        })

    # Update content JSON to show both shortcuts
    doc.content = json.dumps([
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
    ])

    doc.save(ignore_permissions=True)
    frappe.db.commit()
