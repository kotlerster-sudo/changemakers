import frappe


def execute():
    """
    Roles and workspace shortcut for WRP Saturation Progress are handled
    entirely by set_wrp_report_roles_v2 (after_migrate hook), which runs
    after fixtures are synced and the Report doc exists in the DB.

    This patch is intentionally a no-op — it exists only so patches.txt
    does not cause a missing-module error on older sites.
    """
    frappe.db.commit()
