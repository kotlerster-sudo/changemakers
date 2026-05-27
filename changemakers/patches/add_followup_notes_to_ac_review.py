"""
Add followup_notes (Long Text) to WRP AC Review.

ac_notes (the original Cleared/Blocked note) stays as historical data.
followup_notes is an append-only log of post-resolution notes from ACs.

Idempotent.
"""
import frappe


def execute():
    frappe.reload_doc("frappe_changemakers", "doctype", "wrp_ac_review", force=True)
    frappe.db.commit()
