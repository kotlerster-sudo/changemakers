"""
Neon makeover for WRP Performance workspace.
- Gradient header, coloured section labels with emoji
- Shortcut tile colours: Purple / Green / Red / Cyan
"""

import json
import frappe


def execute():
    if not frappe.db.exists("Workspace", "WRP Performance"):
        return

    # ── Shortcut colours ───────────────────────────────────────────────────────
    color_map = {
        "CO CMCHIS Performance":    "Purple",
        "CO Daily Coverage":        "Green",
        "CMCHIS Delay Analysis":    "Red",
        "CMCHIS Pipeline Dashboard": "Cyan",
    }
    for link_to, color in color_map.items():
        frappe.db.sql(
            "UPDATE `tabWorkspace Shortcut` SET color = %s WHERE parent = %s AND link_to = %s",
            (color, "WRP Performance", link_to),
        )

    # ── Content blocks ─────────────────────────────────────────────────────────
    grad = (
        "background:linear-gradient(90deg,#e040fb,#40c4ff);"
        "-webkit-background-clip:text;-webkit-text-fill-color:transparent;"
        "font-weight:900"
    )
    sub = "font-size:0.82em;font-weight:700;text-transform:uppercase;letter-spacing:1.5px"

    content = [
        {
            "id": "wrp_h1", "type": "header",
            "data": {
                "text": "<span class=\"h4\" style=\"" + grad + "\">⚡ WRP Performance</span>",
                "col": 12,
            },
        },
        {
            "id": "wrp_p1", "type": "paragraph",
            "data": {
                "text": "<span style=\"color:#9e9e9e;font-size:0.9em\">"
                        "CMCHIS progress and pipeline bottleneck tracking "
                        "across COs, Streets and Intervention Units.</span>",
                "col": 12,
            },
        },
        {
            "id": "wrp_p2", "type": "paragraph",
            "data": {
                "text": "<span style=\"color:#e040fb;" + sub + "\">📊 Performance</span>",
                "col": 12,
            },
        },
        {
            "id": "wrp_s1", "type": "shortcut",
            "data": {"shortcut_name": "CO CMCHIS Performance", "col": 4},
        },
        {
            "id": "wrp_p3", "type": "paragraph",
            "data": {
                "text": "<span style=\"color:#00c853;" + sub + "\">📅 Daily Coverage</span>",
                "col": 12,
            },
        },
        {
            "id": "wrp_s3", "type": "shortcut",
            "data": {"shortcut_name": "CO Daily Coverage", "col": 4},
        },
        {
            "id": "wrp_p4", "type": "paragraph",
            "data": {
                "text": "<span style=\"color:#ff1744;" + sub + "\">🔥 Delay &amp; Bottleneck Analysis</span>",
                "col": 12,
            },
        },
        {
            "id": "wrp_s2", "type": "shortcut",
            "data": {"shortcut_name": "CMCHIS Delay Analysis", "col": 4},
        },
        {
            "id": "wrp_p5", "type": "paragraph",
            "data": {
                "text": "<span style=\"color:#40c4ff;" + sub + "\">🚀 Pipeline Dashboard</span>",
                "col": 12,
            },
        },
        {
            "id": "wrp_s4", "type": "shortcut",
            "data": {"shortcut_name": "CMCHIS Pipeline Dashboard", "col": 4},
        },
    ]

    frappe.db.sql(
        "UPDATE tabWorkspace SET content = %s WHERE name = %s",
        (json.dumps(content), "WRP Performance"),
    )
    frappe.db.commit()
