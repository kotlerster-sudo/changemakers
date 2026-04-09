"""
WRP Status Logger
-----------------
Fires on before_save for Individual Profile-WRP and Household Profile-WRP.
Writes one row to WRP Status Log for every tracked field that changes value.

Tracked fields:
  Individual Profile-WRP  → aadhaar_status, income_status
  Household Profile-WRP   → cmchis_status
"""

import frappe
from frappe.utils import now_datetime

IND_TRACKED = ["aadhaar_status", "income_status"]
HH_TRACKED  = ["cmchis_status"]


def _skip():
    """Suppress logging during migrations, imports, fixture loads, and tests."""
    return (
        frappe.flags.in_migrate
        or frappe.flags.in_import
        or frappe.flags.in_install
        or frappe.flags.in_test
        or frappe.flags.in_patch
    )


def _get_hh_context(hh_name):
    """Fetch CO / street / IU / org context for a household (single SQL call)."""
    rows = frappe.db.sql(
        """
        SELECT
            hh.hhid                  AS hhid,
            sl.name                  AS street_name,
            sl.added_by_co           AS co_id,
            sl.intervention_units    AS intervention_unit,
            sl.implementing_org      AS implementing_org,
            sl.ac_alloted            AS ac_name,
            staff.full_name          AS co_name,
            pm_staff.full_name       AS pm_name
        FROM `tabHousehold Profile-WRP` hh
        LEFT JOIN `tabStreet List  - WRP` sl
            ON sl.name = hh.street_name
        LEFT JOIN `tabStaff details - WRP` staff
            ON staff.name = sl.added_by_co
        LEFT JOIN (
            SELECT organisation, MIN(full_name) AS full_name
            FROM `tabStaff details - WRP`
            WHERE desigination = 'Project Manager'
              AND current_employee_status != 'Inactive'
            GROUP BY organisation
        ) pm_staff ON pm_staff.organisation = sl.implementing_org
        WHERE hh.name = %s
        LIMIT 1
        """,
        hh_name,
        as_dict=True,
    )
    return rows[0] if rows else {}


def _insert_log(hh_name, individual, field, old_val, new_val, ctx):
    now = str(now_datetime())
    user = frappe.session.user
    frappe.db.sql(
        """
        INSERT INTO `tabWRP Status Log`
            (name, hh_name, hhid, individual, field_changed,
             old_value, new_value, changed_at, changed_by,
             co_id, co_name, ac_name, pm_name,
             street_name, intervention_unit, implementing_org,
             creation, modified, owner, modified_by, docstatus)
        VALUES
            (%(name)s, %(hh_name)s, %(hhid)s, %(individual)s, %(field)s,
             %(old_val)s, %(new_val)s, %(now)s, %(user)s,
             %(co_id)s, %(co_name)s, %(ac_name)s, %(pm_name)s,
             %(street_name)s, %(intervention_unit)s, %(implementing_org)s,
             %(now)s, %(now)s, %(user)s, %(user)s, 0)
        """,
        {
            "name":              frappe.generate_hash(length=10),
            "hh_name":           hh_name or "",
            "hhid":              ctx.get("hhid") or "",
            "individual":        individual or "",
            "field":             field,
            "old_val":           old_val or "",
            "new_val":           new_val or "",
            "now":               now,
            "user":              user,
            "co_id":             ctx.get("co_id") or "",
            "co_name":           ctx.get("co_name") or "",
            "ac_name":           ctx.get("ac_name") or "",
            "pm_name":           ctx.get("pm_name") or "",
            "street_name":       ctx.get("street_name") or "",
            "intervention_unit": ctx.get("intervention_unit") or "",
            "implementing_org":  ctx.get("implementing_org") or "",
        },
    )


def log_individual_status_change(doc, method):
    if _skip():
        return
    old_doc = doc.get_doc_before_save()
    if not old_doc:
        return  # new record — no transition to log

    changed_fields = [
        f for f in IND_TRACKED
        if old_doc.get(f) != doc.get(f)
    ]
    if not changed_fields:
        return

    ctx = _get_hh_context(doc.hhid)
    for field in changed_fields:
        _insert_log(doc.hhid, doc.name, field, old_doc.get(field), doc.get(field), ctx)


def log_hh_status_change(doc, method):
    if _skip():
        return
    old_doc = doc.get_doc_before_save()
    if not old_doc:
        return

    changed_fields = [
        f for f in HH_TRACKED
        if old_doc.get(f) != doc.get(f)
    ]
    if not changed_fields:
        return

    ctx = _get_hh_context(doc.name)
    for field in changed_fields:
        _insert_log(doc.name, None, field, old_doc.get(field), doc.get(field), ctx)
