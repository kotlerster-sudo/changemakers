"""Creates the ECP workspace pointing to the ECP Coverage Dashboard HTML block."""
import json
import frappe


def execute():
    if not frappe.db.exists("DocType", "Workspace"):
        return

    name = "ECP"
    html_block_name = "ECP Coverage Dashboard"
    block_id = "ecp_block"
    content = json.dumps([{
        "id": block_id,
        "type": "custom_block",
        "data": {"custom_block_name": html_block_name, "col": 12},
    }])

    if frappe.db.exists("Workspace", name):
        doc = frappe.get_doc("Workspace", name)
    else:
        doc = frappe.new_doc("Workspace")
        doc.name = name

    doc.title = "ECP"
    doc.label = "ECP"
    doc.module = "Frappe Changemakers"
    doc.is_standard = 0
    doc.public = 1
    doc.content = content

    doc.set("roles", [])
    for role in ["WRP-PM", "WRP-MIS", "System Manager"]:
        doc.append("roles", {"role": role})

    doc.set("custom_blocks", [])
    doc.append("custom_blocks", {"custom_block_name": html_block_name, "label": ""})

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)

    frappe.db.commit()
