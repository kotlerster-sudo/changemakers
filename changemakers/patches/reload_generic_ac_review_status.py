import frappe


def execute():
	frappe.reload_doc("Frappe Changemakers", "DocType", "Generic AC Review", force=True)
