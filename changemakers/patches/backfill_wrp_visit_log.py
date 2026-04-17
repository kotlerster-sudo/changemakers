"""
Backfill WRP Visit Log from two sources:

Source 1 — last_visited_at on Individual Profile-WRP
  Each individual's last_visited_at = the date shown in the daily coverage report
  for that day. Across all dates this is equivalent to running the report for
  every historical date and collecting the results.
  Limitation: only one entry per individual (their most recent visit).
  For visit_count = 1 individuals this is complete.

Source 2 — WRP Status Log
  Each log entry (field_changed, changed_at, co_id, hh_name) represents a visit
  where something was updated. Gives us additional (individual × date) pairs for
  individuals who had status changes on dates other than their last_visited_at.

Run once; idempotent — uses INSERT IGNORE with a deterministic name hash.
"""
import frappe


def execute():
    if not frappe.db.table_exists("WRP Visit Log"):
        return

    # ── Source 1: last_visited_at per individual ──────────────────────────────
    # One row per individual — the date shown in daily coverage report for that day
    frappe.db.sql("""
        INSERT IGNORE INTO `tabWRP Visit Log`
            (name, individual, hh_name, co_id,
             street_name, intervention_unit, implementing_org,
             visited_at,
             creation, modified, owner, modified_by, docstatus)
        SELECT
            SUBSTR(MD5(CONCAT('lv|', ip.name, '|', DATE(ip.last_visited_at))), 1, 10),
            ip.name,
            ip.hhid,
            sl.added_by_co,
            sl.name,
            sl.intervention_units,
            sl.implementing_org,
            ip.last_visited_at,
            NOW(), NOW(), 'Administrator', 'Administrator', 0
        FROM `tabIndividual Profile-WRP` ip
        JOIN `tabHousehold Profile-WRP` hh ON hh.name = ip.hhid
        JOIN `tabStreet List  - WRP`    sl ON sl.name  = hh.street_name
        WHERE ip.last_visited_at IS NOT NULL
          AND ip.visit_count > 0
          AND ip.status = 'Active- ஆக்டிவ்'
          AND hh.survay_status   = 'Occupied/உள்ளனர்'
          AND hh.availability_for = 'Going Ahead/துவங்கலாம்'
    """)

    # ── Source 2: WRP Status Log entries (individual × date pairs) ────────────
    # A status change = CO visited that day. Gives earlier visits not captured
    # by last_visited_at. One row per (individual, date) — deduped by name hash.
    frappe.db.sql("""
        INSERT IGNORE INTO `tabWRP Visit Log`
            (name, individual, hh_name, co_id,
             street_name, intervention_unit, implementing_org,
             visited_at,
             creation, modified, owner, modified_by, docstatus)
        SELECT
            SUBSTR(MD5(CONCAT('sl|', log.individual, '|', DATE(log.changed_at))), 1, 10),
            log.individual,
            log.hh_name,
            log.co_id,
            log.street_name,
            log.intervention_unit,
            log.implementing_org,
            MIN(log.changed_at),
            NOW(), NOW(), 'Administrator', 'Administrator', 0
        FROM `tabWRP Status Log` log
        WHERE log.individual IS NOT NULL
          AND log.individual != ''
          AND log.co_id IS NOT NULL
          AND log.co_id != ''
        GROUP BY log.individual, DATE(log.changed_at)
    """)

    frappe.db.commit()
    frappe.logger().info("Backfilled WRP Visit Log from last_visited_at + WRP Status Log")
