"""
Deduplication script for Individual Profile-WRP.
Run from Frappe Console at /app/console

STEP 1 — run with dry_run = True to preview what will be deleted
STEP 2 — set dry_run = False and run again to execute

Duplicates are identified by:
  1. Same ipid  (if populated)
  2. Same hhid + name_of_the_individual  (catches migration dupes without ipid)

For each duplicate group the record with the LATEST modified timestamp is kept.
Document Vault Items on deleted records are reassigned to the kept record first.
"""

dry_run = True   # ← change to False to actually delete

# ─────────────────────────────────────────────────────────────────────────────

import frappe
from collections import defaultdict

def _get_duplicate_groups():
    """Return dict: kept_name → [names_to_delete]"""
    groups = {}   # dedup_key → [name ordered by modified desc]

    # Strategy 1: ipid
    rows = frappe.db.sql("""
        SELECT name, ipid, modified
        FROM `tabIndividual Profile-WRP`
        WHERE ipid IS NOT NULL AND ipid != ''
        ORDER BY ipid, modified DESC
    """, as_dict=True)

    by_ipid = defaultdict(list)
    for r in rows:
        by_ipid[r.ipid].append(r.name)

    for ipid, names in by_ipid.items():
        if len(names) > 1:
            key = ("ipid", ipid)
            groups[key] = {"keep": names[0], "delete": names[1:]}

    # Strategy 2: hhid + name_of_the_individual
    rows2 = frappe.db.sql("""
        SELECT name, hhid, name_of_the_individual, modified
        FROM `tabIndividual Profile-WRP`
        WHERE hhid IS NOT NULL AND hhid != ''
          AND name_of_the_individual IS NOT NULL AND name_of_the_individual != ''
        ORDER BY hhid, name_of_the_individual, modified DESC
    """, as_dict=True)

    by_name_hh = defaultdict(list)
    for r in rows2:
        k = (r.hhid, (r.name_of_the_individual or "").strip().lower())
        by_name_hh[k].append(r.name)

    for k, names in by_name_hh.items():
        if len(names) > 1:
            key = ("name_hh", k)
            if key not in groups:
                groups[key] = {"keep": names[0], "delete": names[1:]}

    return groups


def run(dry_run=True):
    groups = _get_duplicate_groups()

    total_to_delete = sum(len(g["delete"]) for g in groups.values())
    print(f"Duplicate groups found : {len(groups)}")
    print(f"Records to delete      : {total_to_delete}")
    print(f"Mode                   : {'DRY RUN — no changes' if dry_run else '*** LIVE DELETE ***'}")
    print("-" * 60)

    if not groups:
        print("Nothing to do.")
        return

    # Preview first 20 groups
    preview_count = 0
    for key, g in groups.items():
        if preview_count >= 20:
            print(f"  ... and {len(groups) - 20} more groups")
            break
        reason = f"ipid={key[1]}" if key[0] == "ipid" else f"hhid={key[1][0]}, name={key[1][1]}"
        print(f"  KEEP   {g['keep']}  |  {reason}")
        for d in g["delete"]:
            print(f"  DELETE {d}")
        preview_count += 1

    if dry_run:
        print("\nDRY RUN complete. Set dry_run = False to execute.")
        return

    # ── Execute ──────────────────────────────────────────────────────────────
    deleted = 0
    errors  = 0

    # Collect all names to delete and their corresponding kept record
    to_delete = {}   # name_to_delete → kept_name
    for g in groups.values():
        for d in g["delete"]:
            to_delete[d] = g["keep"]

    for del_name, keep_name in to_delete.items():
        try:
            # 1. Move Document Vault Items to the kept record
            frappe.db.sql(
                "UPDATE `tabDocument Vault Item` SET parent = %s WHERE parent = %s",
                (keep_name, del_name)
            )

            # 2. Delete the duplicate (force bypasses link checks)
            frappe.delete_doc(
                "Individual Profile-WRP",
                del_name,
                force=True,
                ignore_permissions=True,
                delete_permanently=True,
            )
            deleted += 1

        except Exception as e:
            print(f"  ERROR deleting {del_name}: {e}")
            errors += 1

    frappe.db.commit()
    print(f"\nDone.  Deleted: {deleted}  |  Errors: {errors}")


run(dry_run=dry_run)
