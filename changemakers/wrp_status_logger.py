"""
WRP Status Logger
-----------------
Fires on before_save for Individual Profile-WRP and Household Profile-WRP.
Writes one row to WRP Status Log for every tracked field that changes value,
including the household's pipeline bucket before and after the change.

Pipeline buckets (in order):
  unvisited → missing_both → missing_aadhaar / missing_income → docs_ready
  → applied → active  (or → rejected at any point)
"""

import frappe
from frappe.utils import now_datetime

AADHAAR_RECEIVED = "Aadhaar Received"
INCOME_READY     = {"Income Cert Received", "Income Cert Expired"}

IND_TRACKED = ["aadhaar_status", "income_status"]
HH_TRACKED  = ["cmchis_status"]


def _skip():
    return (
        frappe.flags.in_migrate
        or frappe.flags.in_import
        or frappe.flags.in_install
        or frappe.flags.in_test
        or frappe.flags.in_patch
    )


# ── Bucket computation ────────────────────────────────────────────────────────

def _compute_hh_bucket(hh_name, hh_cmchis=None, ind_override=None):
    """
    Return the pipeline bucket for hh_name.

    hh_cmchis     – pass the cmchis_status to use; if None, reads from DB.
    ind_override  – {ind_name: {field: value, …}} to override one member's
                    field values (used to simulate the post-save state while
                    still in before_save, when DB still has old values).

    Buckets: unvisited | missing_both | missing_aadhaar | missing_income
             | docs_ready | applied | active | rejected
    """
    c = (hh_cmchis or "").lower()
    if "active" in c:
        return "active"
    if "rejected" in c:
        return "rejected"
    if "applied" in c and "not" not in c:
        return "applied"

    members = frappe.db.sql(
        """SELECT name, visit_count, aadhaar_status, income_status
           FROM `tabIndividual Profile-WRP`
           WHERE hhid = %(hh)s AND status = 'Active- ஆக்டிவ்'""",
        {"hh": hh_name},
        as_dict=True,
    )

    if ind_override:
        for m in members:
            if m["name"] in ind_override:
                m.update(ind_override[m["name"]])

    if not members:
        return "unvisited"

    max_visits = max(int(m.get("visit_count") or 0) for m in members)
    if max_visits == 0:
        return "unvisited"

    # docs_ready: at least one member has BOTH aadhaar AND income
    for m in members:
        if (m.get("aadhaar_status") or "") == AADHAAR_RECEIVED and \
           (m.get("income_status") or "") in INCOME_READY:
            return "docs_ready"

    has_aadhaar = any((m.get("aadhaar_status") or "") == AADHAAR_RECEIVED for m in members)
    has_income  = any((m.get("income_status")  or "") in INCOME_READY      for m in members)

    if has_aadhaar:
        return "missing_income"   # has aadhaar but no one has both yet
    if has_income:
        return "missing_aadhaar"  # has income but no aadhaar
    return "missing_both"


# ── Context & insert ──────────────────────────────────────────────────────────

def _get_hh_context(hh_name):
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


def _insert_visit_log(individual, hh_name, ctx):
    """Write one row to WRP Visit Log for a raw visit (visit_count increment)."""
    frappe.db.sql(
        """
        INSERT INTO `tabWRP Visit Log`
            (name, individual, hh_name, co_id,
             street_name, intervention_unit, implementing_org,
             visited_at,
             creation, modified, owner, modified_by, docstatus)
        VALUES
            (%(name)s, %(individual)s, %(hh_name)s, %(co_id)s,
             %(street_name)s, %(intervention_unit)s, %(implementing_org)s,
             %(now)s,
             %(now)s, %(now)s, %(user)s, %(user)s, 0)
        """,
        {
            "name":              frappe.generate_hash(length=10),
            "individual":        individual or "",
            "hh_name":           hh_name or "",
            "co_id":             ctx.get("co_id") or "",
            "street_name":       ctx.get("street_name") or "",
            "intervention_unit": ctx.get("intervention_unit") or "",
            "implementing_org":  ctx.get("implementing_org") or "",
            "now":               str(now_datetime()),
            "user":              frappe.session.user,
        },
    )


def _insert_log(hh_name, individual, field, old_val, new_val,
                old_bucket, new_bucket, ctx):
    now  = str(now_datetime())
    user = frappe.session.user
    frappe.db.sql(
        """
        INSERT INTO `tabWRP Status Log`
            (name, hh_name, hhid, individual, field_changed,
             old_value, new_value, old_bucket, new_bucket,
             changed_at, changed_by,
             co_id, co_name, ac_name, pm_name,
             street_name, intervention_unit, implementing_org,
             creation, modified, owner, modified_by, docstatus)
        VALUES
            (%(name)s, %(hh_name)s, %(hhid)s, %(individual)s, %(field)s,
             %(old_val)s, %(new_val)s, %(old_bucket)s, %(new_bucket)s,
             %(now)s, %(user)s,
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
            "old_bucket":        old_bucket or "",
            "new_bucket":        new_bucket or "",
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


# ── Hook handlers ─────────────────────────────────────────────────────────────

def log_individual_status_change(doc, method):
    if _skip():
        return
    old_doc = doc.get_doc_before_save()
    if not old_doc:
        return  # new record

    hh_name = doc.hhid
    if not hh_name:
        return

    changed_fields = [f for f in IND_TRACKED if old_doc.get(f) != doc.get(f)]
    visit_incremented = int(doc.get("visit_count") or 0) > int(old_doc.get("visit_count") or 0)

    if not changed_fields and not visit_incremented:
        return

    hh_cmchis = frappe.db.get_value("Household Profile-WRP", hh_name, "cmchis_status") or ""
    ctx = _get_hh_context(hh_name)

    if visit_incremented:
        _insert_visit_log(doc.name, hh_name, ctx)

    if not changed_fields:
        return

    # Before: DB still has old values for this individual (we're in before_save)
    old_bucket = _compute_hh_bucket(hh_name, hh_cmchis=hh_cmchis)

    # After: same DB, but override this individual with the incoming new values
    new_bucket = _compute_hh_bucket(
        hh_name,
        hh_cmchis=hh_cmchis,
        ind_override={doc.name: {
            "aadhaar_status": doc.aadhaar_status or "",
            "income_status":  doc.income_status  or "",
            "visit_count":    doc.visit_count     or 0,
        }},
    )

    for field in changed_fields:
        _insert_log(hh_name, doc.name, field,
                    old_doc.get(field), doc.get(field),
                    old_bucket, new_bucket, ctx)


def log_hh_status_change(doc, method):
    if _skip():
        return
    old_doc = doc.get_doc_before_save()
    if not old_doc:
        return

    changed_fields = [f for f in HH_TRACKED if old_doc.get(f) != doc.get(f)]
    if not changed_fields:
        return

    hh_name = doc.name
    ctx = _get_hh_context(hh_name)

    for field in changed_fields:
        old_val = old_doc.get(field) or ""
        new_val = doc.get(field) or ""
        # Bucket uses old/new cmchis_status; member state is unchanged
        old_bucket = _compute_hh_bucket(hh_name, hh_cmchis=old_val)
        new_bucket = _compute_hh_bucket(hh_name, hh_cmchis=new_val)
        _insert_log(hh_name, None, field, old_val, new_val,
                    old_bucket, new_bucket, ctx)
