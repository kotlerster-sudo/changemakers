"""
Scheduled tasks for the Changemakers app.
Wired into hooks.py → scheduler_events.
"""
import frappe


def enrol_new_oap_eligibles():
    """
    Daily job: create Generic Beneficiary (E2) records for individuals
    who have turned 60 since the last run.

    Uses a NOT EXISTS subquery so it only touches the delta — existing
    records are never re-queried or touched.
    """
    if not frappe.db.exists("Entitlement Config", "E2"):
        return

    new_rows = frappe.db.sql("""
        SELECT
            i.name                   AS ind_id,
            i.name_of_the_individual AS full_name,
            i.dob                    AS dob,
            h.street_name            AS street
        FROM `tabIndividual Profile-WRP` i
        LEFT JOIN `tabHousehold Profile-WRP` h ON h.name = i.hhid
        WHERE
            i.status = 'Active- ஆக்டிவ்'
            AND i.dob IS NOT NULL
            AND i.dob != ''
            AND TIMESTAMPDIFF(YEAR, i.dob, CURDATE()) >= 60
            AND NOT EXISTS (
                SELECT 1 FROM `tabGeneric Beneficiary` gb
                WHERE gb.entitlement = 'E2'
                  AND gb.source_docname = i.name
            )
    """, as_dict=True)

    if not new_rows:
        return

    frappe.logger().info(f"enrol_new_oap_eligibles: {len(new_rows)} newly eligible individual(s)")

    all_streets = list({r.street for r in new_rows if r.street})
    co_map = {}
    if all_streets:
        street_rows = frappe.get_all(
            "Street List  - WRP",
            filters={"name": ["in", all_streets]},
            fields=["name", "added_by_co"],
        )
        co_map = {s.name: s.added_by_co for s in street_rows}

    created = 0
    for r in new_rows:
        if not r.street:
            continue
        try:
            frappe.get_doc({
                "doctype":          "Generic Beneficiary",
                "entitlement":      "E2",
                "beneficiary_name": str(r.full_name or ""),
                "date_of_birth":    r.dob,
                "source_docname":   str(r.ind_id),
                "street":           r.street,
                "assigned_co":      co_map.get(r.street) or "",
                "doc1_status":      "not_checked",
                "doc2_status":      "not_checked",
                "doc3_status":      "not_checked",
                "final_status":     "not_applied",
                "visit_count":      0,
            }).insert(ignore_permissions=True)
            created += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(),
                             f"enrol_new_oap_eligibles: insert failed for {r.ind_id}")

    frappe.db.commit()
    frappe.logger().info(f"enrol_new_oap_eligibles: {created} record(s) created")
