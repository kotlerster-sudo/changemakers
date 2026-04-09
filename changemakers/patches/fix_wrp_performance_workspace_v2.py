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

    # Ensure all report shortcuts exist
    existing_links = {s.link_to for s in doc.shortcuts}

    shortcuts_needed = [
        ("CO CMCHIS Performance",  "Blue"),
        ("CMCHIS Pipeline Dashboard", "Green"),
        ("CMCHIS Delay Analysis",  "Orange"),
        ("CO Daily Coverage",      "Purple"),
        ("WRP Status Transitions", "Red"),
    ]
    for link_to, color in shortcuts_needed:
        if link_to not in existing_links:
            doc.append("shortcuts", {
                "label":   link_to,
                "link_to": link_to,
                "type":    "Report",
                "color":   color,
            })

    # Update content JSON
    doc.content = json.dumps([
        {"id": "wrp_h1", "type": "header", "data": {
            "text": "<span class=\"h4\">WRP Performance</span>", "col": 12}},
        {"id": "wrp_p1", "type": "paragraph", "data": {
            "text": "CMCHIS progress, pipeline, delay and transition tracking.", "col": 12}},
        {"id": "wrp_p2", "type": "paragraph", "data": {"text": "Performance", "col": 12}},
        {"id": "wrp_s1", "type": "shortcut", "data": {
            "shortcut_name": "CO CMCHIS Performance", "col": 4}},
        {"id": "wrp_s4", "type": "shortcut", "data": {
            "shortcut_name": "CO Daily Coverage", "col": 4}},
        {"id": "wrp_p3", "type": "paragraph", "data": {"text": "Pipeline & Delays", "col": 12}},
        {"id": "wrp_s2", "type": "shortcut", "data": {
            "shortcut_name": "CMCHIS Pipeline Dashboard", "col": 4}},
        {"id": "wrp_s3", "type": "shortcut", "data": {
            "shortcut_name": "CMCHIS Delay Analysis", "col": 4}},
        {"id": "wrp_p4", "type": "paragraph", "data": {"text": "Status Tracking", "col": 12}},
        {"id": "wrp_s5", "type": "shortcut", "data": {
            "shortcut_name": "WRP Status Transitions", "col": 4}},
    ])

    doc.save(ignore_permissions=True)
    frappe.db.commit()
