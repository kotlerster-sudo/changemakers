"""
Creates three OAP Workspace pages and links each to its Custom HTML Block.
HTML block content is loaded via fixtures (custom_html_block.json).
Idempotent.
"""
import json
import frappe

_DAILY_SHORTCUT = {
    "label":   "Daily Update Report",
    "link_to": "Entitlement Daily Update Report",
    "type":    "Report",
    "color":   "Blue",
}

WORKSPACES = [
    {
        "name":            "OAP Programme Dashboard",
        "title":           "OAP Programme Dashboard",
        "html_block_name": "Entitlement Programme Dashboard",
        "roles":           ["WRP-PM", "WRP-HR", "WRP-MIS", "System Manager"],
        "shortcuts":       [_DAILY_SHORTCUT],
    },
    {
        "name":            "OAP AC Review Dashboard",
        "title":           "OAP AC Review Dashboard",
        "html_block_name": "Entitlement AC Dashboard",
        "roles":           ["WRP-AC", "WRP-PM", "System Manager"],
    },
    {
        "name":            "OAP MIS Dashboard",
        "title":           "OAP MIS Dashboard",
        "html_block_name": "Entitlement MIS Dashboard",
        "roles":           ["WRP-MIS", "WRP-PM", "System Manager"],
        "shortcuts":       [_DAILY_SHORTCUT],
    },
]


def execute():
    if not frappe.db.exists("DocType", "Workspace"):
        return

    for ws in WORKSPACES:
        try:
            _upsert_workspace(
                name=ws["name"],
                title=ws["title"],
                roles=ws["roles"],
                html_block_name=ws["html_block_name"],
                shortcuts=ws.get("shortcuts"),
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"setup_entitlement_dashboards: {ws['name']}")

    frappe.db.commit()


def _upsert_workspace(name, title, roles, html_block_name, module="Frappe Changemakers",
                     shortcuts=None):
    block_id = name.lower().replace(" ", "_") + "_block"
    # Only surface shortcuts whose target actually exists (avoid broken links).
    shortcuts = [s for s in (shortcuts or [])
                 if frappe.db.exists(s["type"], s["link_to"])]

    blocks = [{
        "id": block_id,
        "type": "custom_block",
        "data": {"custom_block_name": html_block_name, "col": 12},
    }]
    if shortcuts:
        blocks.append({"id": block_id + "_sc_hdr", "type": "paragraph",
                       "data": {"text": "Daily Tracking", "col": 12}})
        for i, sc in enumerate(shortcuts):
            # content shortcut block references the shortcut's LABEL via shortcut_name
            blocks.append({"id": block_id + "_sc%d" % i, "type": "shortcut",
                           "data": {"shortcut_name": sc["label"], "col": 4}})
    content = json.dumps(blocks)

    if frappe.db.exists("Workspace", name):
        doc = frappe.get_doc("Workspace", name)
        doc.title = title
        doc.label = title
        doc.content = content
    else:
        doc = frappe.new_doc("Workspace")
        doc.name = name
        doc.title = title
        doc.label = title
        doc.module = module
        doc.is_standard = 0
        doc.public = 1
        doc.content = content

    doc.set("roles", [])
    for role in roles:
        doc.append("roles", {"role": role})

    # custom_blocks child table — required for page_data loader.
    # Leave label blank: desktop.py falls back to custom_block_name as label,
    # which must match the custom_block_name in the content JSON.
    doc.set("custom_blocks", [])
    doc.append("custom_blocks", {
        "custom_block_name": html_block_name,
        "label": "",
    })

    if shortcuts:
        doc.set("shortcuts", [])
        for sc in shortcuts:
            doc.append("shortcuts", {
                "label":   sc["label"],
                "link_to": sc["link_to"],
                "type":    sc["type"],
                "color":   sc.get("color", "Grey"),
            })

    _old = frappe.flags.ignore_links
    frappe.flags.ignore_links = True
    try:
        if doc.is_new():
            doc.insert(ignore_permissions=True)
        else:
            doc.save(ignore_permissions=True)
    finally:
        frappe.flags.ignore_links = _old
