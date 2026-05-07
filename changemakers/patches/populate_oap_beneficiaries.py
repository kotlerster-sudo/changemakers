"""
Populate Generic Beneficiary records for Old Age Pension (E2).

Source: Individual Profile-WRP where age >= 60 and status = Active.
Street and CO are resolved via Household Profile-WRP → Street List - WRP.

Idempotent: skips individuals already imported (matched by source_docname + E2).

Run manually:
  bench --site <site> execute changemakers.patches.populate_oap_beneficiaries.execute

Dry-run (prints counts, creates nothing):
  bench --site <site> execute changemakers.patches.populate_oap_beneficiaries.execute --kwargs '{"dry_run": true}'
"""
import frappe
from frappe.utils import getdate, nowdate


ENTITLEMENT = "E2"
BATCH_SIZE  = 200
ACTIVE_STATUS = "Active- ஆக்டிவ்"


def execute(dry_run=False):
    if not frappe.db.exists("Entitlement Config", ENTITLEMENT):
        frappe.logger().warning("populate_oap_beneficiaries: E2 not seeded — run after deploy")
        return

    # ── Build set of already-imported source IDs ──────────────────────────────
    existing = set(frappe.get_all(
        "Generic Beneficiary",
        filters={"entitlement": ENTITLEMENT, "source_docname": ["!=", ""]},
        pluck="source_docname",
    ))
    frappe.logger().info(f"populate_oap: {len(existing)} existing E2 records")

    # ── Fetch all eligible individuals in one SQL query ───────────────────────
    rows = frappe.db.sql("""
        SELECT
            i.name            AS ind_id,
            i.name_of_the_individual AS full_name,
            i.dob             AS dob,
            i.hhid            AS hhid,
            h.street_name     AS street
        FROM `tabIndividual Profile-WRP` i
        LEFT JOIN `tabHousehold Profile-WRP` h ON h.name = i.hhid
        WHERE
            i.status = %(status)s
            AND i.dob IS NOT NULL
            AND i.dob != ''
            AND TIMESTAMPDIFF(YEAR, i.dob, CURDATE()) >= 60
        ORDER BY i.name
    """, {"status": ACTIVE_STATUS}, as_dict=True)

    frappe.logger().info(f"populate_oap: {len(rows)} eligible individuals aged 60+")

    # ── Build CO lookup: street → added_by_co ─────────────────────────────────
    all_streets = list({r.street for r in rows if r.street})
    co_map = {}
    if all_streets:
        street_rows = frappe.get_all(
            "Street List  - WRP",
            filters={"name": ["in", all_streets]},
            fields=["name", "added_by_co"],
        )
        co_map = {s.name: s.added_by_co for s in street_rows}

    # ── Create records ─────────────────────────────────────────────────────────
    created = skipped_existing = skipped_no_street = 0

    for i, r in enumerate(rows):
        ind_id = str(r.ind_id)

        if ind_id in existing:
            skipped_existing += 1
            continue

        if not r.street:
            skipped_no_street += 1
            frappe.logger().debug(f"populate_oap: skipping {ind_id} — no street (hhid={r.hhid})")
            continue

        if dry_run:
            created += 1
            continue

        try:
            doc = frappe.get_doc({
                "doctype":        "Generic Beneficiary",
                "entitlement":    ENTITLEMENT,
                "beneficiary_name": str(r.full_name or ""),
                "date_of_birth":  r.dob,
                "source_docname": ind_id,
                "street":         r.street,
                "assigned_co":    co_map.get(r.street) or "",
                "doc1_status":    "not_checked",
                "doc2_status":    "not_checked",
                "doc3_status":    "not_checked",
                "final_status":   "not_applied",
                "visit_count":    0,
            })
            doc.insert(ignore_permissions=True)
            created += 1
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"populate_oap: insert failed for ind {ind_id}")
            continue

        # Commit in batches to keep transactions small
        if created % BATCH_SIZE == 0:
            frappe.db.commit()
            frappe.logger().info(f"populate_oap: {created} created so far…")

    frappe.db.commit()

    summary = (
        f"populate_oap {'[DRY RUN] ' if dry_run else ''}complete — "
        f"eligible={len(rows)}, created={created}, "
        f"skipped_existing={skipped_existing}, skipped_no_street={skipped_no_street}"
    )
    frappe.logger().info(summary)
    print(summary)
