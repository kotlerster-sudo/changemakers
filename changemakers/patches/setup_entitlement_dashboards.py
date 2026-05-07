"""
Creates three OAP Workspace pages and links each to its Custom HTML Block.
HTML block content is loaded via fixtures (custom_html_block.json).
Idempotent.
"""
import json
import frappe

WORKSPACES = [
    {
        "name":            "OAP Programme",
        "title":           "OAP Programme Dashboard",
        "html_block_name": "Entitlement Programme Dashboard",
        "roles":           ["WRP-PM", "WRP-HR", "WRP-MIS", "System Manager"],
    },
    {
        "name":            "OAP AC Review",
        "title":           "OAP AC Review Dashboard",
        "html_block_name": "Entitlement AC Dashboard",
        "roles":           ["WRP-AC", "WRP-PM", "System Manager"],
    },
    {
        "name":            "OAP MIS",
        "title":           "OAP MIS Dashboard",
        "html_block_name": "Entitlement MIS Dashboard",
        "roles":           ["WRP-MIS", "WRP-PM", "System Manager"],
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
            )
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"setup_entitlement_dashboards: {ws['name']}")

    frappe.db.commit()


def _upsert_workspace(name, title, roles, html_block_name, module="Frappe Changemakers"):
    block_id = name.lower().replace(" ", "_") + "_block"
    content = json.dumps([
        {
            "id": block_id,
            "type": "custom-block",
            "data": {"custom_block_name": html_block_name, "col": 12},
        }
    ])

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

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)
