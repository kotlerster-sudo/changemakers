"""
Bulk status update from Excel workbooks.

Usage:
    bench --site chennai.dignifiedlife.in execute changemakers.bulk_status_update.run \
        --kwargs '{"files": ["/path/to/org1.xlsx", "/path/to/org2.xlsx", "/path/to/org3.xlsx", "/path/to/org4.xlsx"]}'
"""

import frappe
import pandas as pd
import os
from datetime import datetime

BATCH_SIZE = 500


def _find_col(df, *candidates):
    """Return the first column name that contains any candidate string (case-insensitive)."""
    for col in df.columns:
        for c in candidates:
            if c.lower() in col.lower():
                return col
    return None


def _clean(val):
    """Return stripped string or None if empty/NaN."""
    if val is None:
        return None
    s = str(val).strip()
    return None if s in ("", "nan", "None", "NaT") else s


def _parse_date(val):
    """Return YYYY-MM-DD string or None."""
    if val is None or str(val).strip() in ("", "nan", "None", "NaT"):
        return None
    if isinstance(val, (datetime,)):
        return val.strftime("%Y-%m-%d")
    try:
        return pd.to_datetime(val).strftime("%Y-%m-%d")
    except Exception:
        return None


def run(files=None):
    if not files:
        print("ERROR: No files provided. Pass files as a list of absolute paths.")
        return

    ind_updated = 0
    hh_updated  = 0
    ind_skipped = 0
    hh_skipped  = 0
    errors      = []
    hh_seen     = {}   # HHID → cmchis_status, to update each household only once

    for filepath in files:
        if not os.path.exists(filepath):
            print(f"File not found, skipping: {filepath}")
            continue

        print(f"\nReading {os.path.basename(filepath)} ...")
        try:
            df = pd.read_excel(filepath, dtype=str)
        except Exception as e:
            print(f"  Could not read file: {e}")
            continue

        df.columns = [str(c).strip() for c in df.columns]

        # Locate columns by partial name match to handle Tamil suffixes
        col_ind_id      = _find_col(df, "Individual ID")
        col_hhid        = _find_col(df, "HHID")
        col_aadhaar     = _find_col(df, "Aadhaar Status")
        col_income      = _find_col(df, "Income Status")
        col_cmchis      = _find_col(df, "CMCHIS Status")
        col_visited     = _find_col(df, "Last Visited At")
        col_notes       = _find_col(df, "Field notes", "Notes")

        print(f"  Columns mapped — ind_id:{col_ind_id}  hhid:{col_hhid}  "
              f"aadhaar:{col_aadhaar}  income:{col_income}  cmchis:{col_cmchis}  "
              f"visited:{col_visited}  notes:{col_notes}")

        batch_count = 0

        for idx, row in df.iterrows():
            individual_id = _clean(row.get(col_ind_id))
            hhid          = _clean(row.get(col_hhid))
            aadhaar       = _clean(row.get(col_aadhaar))
            income        = _clean(row.get(col_income))
            cmchis        = _clean(row.get(col_cmchis))
            visited       = _parse_date(row.get(col_visited))
            notes         = _clean(row.get(col_notes))

            # ── Individual Profile-WRP ────────────────────────────────
            if individual_id:
                upd = {}
                if aadhaar:  upd["aadhaar_status"]  = aadhaar
                if income:   upd["income_status"]   = income
                if visited:  upd["last_visited_at"] = visited
                if notes:    upd["notes"]            = notes

                if upd:
                    if frappe.db.exists("Individual Profile-WRP", individual_id):
                        try:
                            frappe.db.set_value(
                                "Individual Profile-WRP", individual_id,
                                upd, update_modified=False
                            )
                            ind_updated += 1
                            batch_count += 1
                        except Exception as e:
                            errors.append(f"Row {idx+2} | Ind {individual_id}: {e}")
                    else:
                        ind_skipped += 1

            # ── Household Profile-WRP (once per HHID) ────────────────
            if hhid and cmchis and hhid not in hh_seen:
                hh_seen[hhid] = cmchis
                if frappe.db.exists("Household Profile-WRP", hhid):
                    try:
                        frappe.db.set_value(
                            "Household Profile-WRP", hhid,
                            "cmchis_status", cmchis, update_modified=False
                        )
                        hh_updated += 1
                        batch_count += 1
                    except Exception as e:
                        errors.append(f"Row {idx+2} | HH {hhid}: {e}")
                else:
                    hh_skipped += 1

            if batch_count >= BATCH_SIZE:
                frappe.db.commit()
                print(f"  Committed {BATCH_SIZE} rows... "
                      f"(ind: {ind_updated}, hh: {hh_updated})")
                batch_count = 0

        frappe.db.commit()
        print(f"  File done — ind updated: {ind_updated}, hh updated: {hh_updated}")

    print(f"\n{'='*50}")
    print(f"COMPLETE")
    print(f"  Individuals updated : {ind_updated}")
    print(f"  Individuals skipped : {ind_skipped}  (ID not found in DB)")
    print(f"  Households updated  : {hh_updated}")
    print(f"  Households skipped  : {hh_skipped}  (HHID not found in DB)")
    if errors:
        print(f"\n  ERRORS ({len(errors)}):")
        for err in errors[:30]:
            print(f"    {err}")
        if len(errors) > 30:
            print(f"    ... and {len(errors) - 30} more")
    print("="*50)
