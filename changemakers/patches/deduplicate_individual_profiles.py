"""
Deduplication patch for Individual Profile-WRP.
Identifies duplicates by ipid (if set) or hhid + name_of_the_individual.
Keeps the record with the LATEST modified timestamp.
Moves Document Vault Items to the kept record before deleting.
"""

import frappe


def execute():
    groups = {}

    # Strategy 1: same ipid
    rows = frappe.db.sql(
        "SELECT name, ipid, modified FROM `tabIndividual Profile-WRP`"
        " WHERE ipid IS NOT NULL AND ipid != ''"
        " ORDER BY ipid, modified DESC",
        as_dict=True,
    )
    by_ipid = {}
    for r in rows:
        by_ipid.setdefault(r.ipid, []).append(r.name)
    for ipid, names in by_ipid.items():
        if len(names) > 1:
            groups[("ipid", ipid)] = {"keep": names[0], "delete": names[1:]}

    # Strategy 2: same hhid + name_of_the_individual
    rows2 = frappe.db.sql(
        "SELECT name, hhid, name_of_the_individual, modified"
        " FROM `tabIndividual Profile-WRP`"
        " WHERE hhid IS NOT NULL AND hhid != ''"
        "   AND name_of_the_individual IS NOT NULL AND name_of_the_individual != ''"
        " ORDER BY hhid, name_of_the_individual, modified DESC",
        as_dict=True,
    )
    by_name_hh = {}
    for r in rows2:
        k = (r.hhid, (r.name_of_the_individual or "").strip().lower())
        by_name_hh.setdefault(k, []).append(r.name)
    for k, names in by_name_hh.items():
        if len(names) > 1:
            gkey = ("name_hh", k)
            if gkey not in groups:
                groups[gkey] = {"keep": names[0], "delete": names[1:]}

    total_to_delete = sum(len(g["delete"]) for g in groups.values())
    print(f"[Dedup] Duplicate groups found : {len(groups)}")
    print(f"[Dedup] Records to delete      : {total_to_delete}")

    if not groups:
        print("[Dedup] Nothing to do.")
        return

    deleted = 0
    errors = 0

    to_delete = {}
    for g in groups.values():
        for d in g["delete"]:
            to_delete[d] = g["keep"]

    for del_name, keep_name in to_delete.items():
        try:
            frappe.db.sql(
                "UPDATE `tabDocument Vault Item` SET parent = %s WHERE parent = %s",
                (keep_name, del_name),
            )
            frappe.delete_doc(
                "Individual Profile-WRP",
                del_name,
                force=True,
                ignore_permissions=True,
                delete_permanently=True,
            )
            deleted += 1
        except Exception as e:
            print(f"[Dedup] ERROR deleting {del_name}: {e}")
            errors += 1

    frappe.db.commit()
    print(f"[Dedup] Done. Deleted: {deleted} | Errors: {errors}")
