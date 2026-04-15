"""
WRP Saturation Baseline & Daily Progress
-----------------------------------------
One row per day from the baseline date (first log entry in scope) to today.
The first row is the BASELINE — the pre-app state reconstructed from the
old_bucket of each household's first ever WRP Status Log entry.

Columns per row:
  Total HH | Unvisited | Pending Both | Pending Aadhaar | Pending Income
  | Docs Ready | Applied | Active | Rejected
  | Coverage % (visited / total)
  | Saturation % (active / total)
  | Δ Active (daily change)

Chart: dual-line — Saturation % and Coverage % over time.

Filters: CO, Street, Intervention Unit, Implementing Org, AC,
         optional baseline date override, optional to-date.
Org-scoping: WRP roles automatically see only their organisation.
"""

import frappe
from frappe.utils import getdate, nowdate
from collections import defaultdict


AADHAAR_RECEIVED = "Aadhaar Received"
INCOME_READY     = {"Income Cert Received", "Income Cert Expired"}

BUCKETS = [
    "unvisited", "missing_both", "missing_aadhaar",
    "missing_income", "docs_ready", "applied", "active", "rejected",
]


# ── Bucket classification (mirrors flutter_api / wrp_status_logger) ───────────

def _current_bucket(hh_cmchis, max_visits, members):
    c = (hh_cmchis or "").lower()
    if "active"   in c:                    return "active"
    if "rejected" in c:                    return "rejected"
    if "applied"  in c and "not" not in c: return "applied"
    if int(max_visits or 0) == 0:          return "unvisited"
    for m in members:
        if ((m.get("aadhaar_status") or "") == AADHAAR_RECEIVED and
                (m.get("income_status") or "") in INCOME_READY):
            return "docs_ready"
    has_a = any((m.get("aadhaar_status") or "") == AADHAAR_RECEIVED for m in members)
    has_i = any((m.get("income_status")  or "") in INCOME_READY      for m in members)
    if has_a: return "missing_income"
    if has_i: return "missing_aadhaar"
    return "missing_both"


# ── Scope filter ──────────────────────────────────────────────────────────────

def _scope_cond(filters):
    """
    Returns (cond_str, vals_dict) for JOINing through Street List - WRP.
    Returns (None, {}) when the current user has no org access.
    """
    cond = ""
    vals = {}

    if filters.get("co"):
        cond += " AND sl.added_by_co = %(co)s"
        vals["co"] = filters["co"]
    if filters.get("street"):
        cond += " AND sl.name = %(street)s"
        vals["street"] = filters["street"]
    if filters.get("intervention_unit"):
        cond += " AND sl.intervention_units = %(iu)s"
        vals["iu"] = filters["intervention_unit"]
    if filters.get("implementing_org"):
        cond += " AND sl.implementing_org = %(org)s"
        vals["org"] = filters["implementing_org"]
    if filters.get("ac"):
        cond += " AND sl.ac_alloted = %(ac)s"
        vals["ac"] = filters["ac"]

    # Automatic org-level scoping for WRP roles
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        org = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "organisation"
        )
        if not org:
            return None, {}
        cond += " AND sl.implementing_org = %(user_org)s"
        vals["user_org"] = org

    return cond, vals


# ── Entry point ───────────────────────────────────────────────────────────────

def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data, chart = get_data_and_chart(filters)
    return columns, data, None, chart


def get_columns():
    return [
        {"fieldname": "date",            "label": "Date",                 "fieldtype": "Data",    "width": 150},
        {"fieldname": "total_hh",        "label": "Total HH",             "fieldtype": "Int",     "width": 80},
        {"fieldname": "unvisited",       "label": "Unvisited",            "fieldtype": "Int",     "width": 90},
        {"fieldname": "missing_both",    "label": "Pending Both",         "fieldtype": "Int",     "width": 105},
        {"fieldname": "missing_aadhaar", "label": "Pending Aadhaar",      "fieldtype": "Int",     "width": 125},
        {"fieldname": "missing_income",  "label": "Pending Income",       "fieldtype": "Int",     "width": 115},
        {"fieldname": "docs_ready",      "label": "Docs Ready",           "fieldtype": "Int",     "width": 95},
        {"fieldname": "applied",         "label": "Applied",              "fieldtype": "Int",     "width": 80},
        {"fieldname": "active",          "label": "Active",               "fieldtype": "Int",     "width": 80},
        {"fieldname": "rejected",        "label": "Rejected",             "fieldtype": "Int",     "width": 80},
        {"fieldname": "coverage_pct",    "label": "Coverage %",           "fieldtype": "Percent", "width": 100},
        {"fieldname": "saturation_pct",  "label": "Saturation %",         "fieldtype": "Percent", "width": 115},
        {"fieldname": "delta_active",    "label": "\u0394 Active",        "fieldtype": "Data",    "width": 80},
    ]


# ── Main logic ────────────────────────────────────────────────────────────────

def get_data_and_chart(filters):
    today = getdate(nowdate())

    to_date = getdate(filters["to_date"]) if filters.get("to_date") else today

    sc, sv = _scope_cond(filters)
    if sc is None:
        return [], None

    # ── 1. All HHs in scope ───────────────────────────────────────────────────
    hh_rows = frappe.db.sql(
        """
        SELECT hh.name AS hh_name, hh.cmchis_status
        FROM `tabHousehold Profile-WRP` hh
        JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        WHERE hh.survay_status    = 'Occupied/\u0b89\u0bb3\u0bcd\u0bb3\u0ba9\u0bb0\u0bcd'
          AND hh.availability_for = 'Going Ahead/\u0ba4\u0bc1\u0bb5\u0b99\u0bcd\u0b95\u0bb2\u0bbe\u0bae\u0bcd'
          {sc}
        """.format(sc=sc),
        sv, as_dict=True,
    )
    if not hh_rows:
        return [], None

    hh_cmchis_map = {r.hh_name: r.cmchis_status or "" for r in hh_rows}
    hh_set        = set(hh_cmchis_map.keys())
    total_hh      = len(hh_set)

    # ── 2. Individual rows → current bucket per HH ───────────────────────────
    ind_rows = frappe.db.sql(
        """
        SELECT ip.hhid, ip.visit_count, ip.aadhaar_status, ip.income_status
        FROM `tabIndividual Profile-WRP` ip
        JOIN `tabHousehold Profile-WRP` hh ON hh.name = ip.hhid
        JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        WHERE ip.status           = 'Active- \u0b86\u0b95\u0bcd\u0b9f\u0bbf\u0bb5\u0bcd'
          AND hh.survay_status    = 'Occupied/\u0b89\u0bb3\u0bcd\u0bb3\u0ba9\u0bb0\u0bcd'
          AND hh.availability_for = 'Going Ahead/\u0ba4\u0bc1\u0bb5\u0b99\u0bcd\u0b95\u0bb2\u0bbe\u0bae\u0bcd'
          {sc}
        """.format(sc=sc),
        sv, as_dict=True,
    )

    hh_members = defaultdict(list)
    for ind in ind_rows:
        hh_members[ind.hhid].append(ind)

    current_buckets = {}
    for hh_name in hh_set:
        members    = hh_members.get(hh_name, [])
        max_visits = max((int(m.get("visit_count") or 0) for m in members), default=0)
        current_buckets[hh_name] = _current_bucket(
            hh_cmchis_map[hh_name], max_visits, members
        )

    # ── 3. Log entries for scope HHs ─────────────────────────────────────────
    log_rows = frappe.db.sql(
        """
        SELECT log.hh_name, log.old_bucket, log.new_bucket,
               DATE(log.changed_at) AS log_date
        FROM `tabWRP Status Log` log
        JOIN `tabHousehold Profile-WRP` hh ON hh.name = log.hh_name
        JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        WHERE log.old_bucket IS NOT NULL AND log.old_bucket != ''
          AND log.new_bucket IS NOT NULL AND log.new_bucket != ''
          AND hh.survay_status    = 'Occupied/\u0b89\u0bb3\u0bcd\u0bb3\u0ba9\u0bb0\u0bcd'
          AND hh.availability_for = 'Going Ahead/\u0ba4\u0bc1\u0bb5\u0b99\u0bcd\u0b95\u0bb2\u0bbe\u0bae\u0bcd'
          AND DATE(log.changed_at) <= %(to_date)s
          {sc}
        ORDER BY log.changed_at ASC
        """.format(sc=sc),
        dict(sv, to_date=str(to_date)),
        as_dict=True,
    )

    # ── 4. Baseline date & per-HH baseline bucket ─────────────────────────────
    if not log_rows:
        # No transitions at all — show a single snapshot of current state
        snap = _count_buckets(current_buckets)
        return [_make_row("Today (No transitions yet)", snap, total_hh, None)], None

    # Respect optional from_date override; otherwise earliest log entry
    auto_baseline = log_rows[0].log_date
    if filters.get("from_date"):
        baseline_date = getdate(filters["from_date"])
    else:
        baseline_date = auto_baseline

    # For each HH: baseline = old_bucket of its FIRST log entry on/after baseline_date
    hh_first_log = {}
    for r in log_rows:
        if r.log_date >= baseline_date and r.hh_name not in hh_first_log:
            hh_first_log[r.hh_name] = r.old_bucket

    # HHs with no log entries at all: their current state IS their baseline
    baseline_buckets = {}
    for hh_name in hh_set:
        if hh_name in hh_first_log:
            baseline_buckets[hh_name] = hh_first_log[hh_name]
        else:
            baseline_buckets[hh_name] = current_buckets[hh_name]

    # ── 5. Build daily transition map ─────────────────────────────────────────
    # Keep the LAST new_bucket per HH per day (end-of-day state wins)
    daily_tx = defaultdict(dict)
    for r in log_rows:
        if r.log_date >= baseline_date:
            daily_tx[r.log_date][r.hh_name] = r.new_bucket

    # ── 6. Walk day by day to build snapshots ─────────────────────────────────
    working   = dict(baseline_buckets)
    snapshots = [(_fmt_baseline(baseline_date), _count_buckets(working))]

    for log_date in sorted(daily_tx.keys()):
        for hh_name, new_b in daily_tx[log_date].items():
            if hh_name in working and new_b in BUCKETS:
                working[hh_name] = new_b
        snapshots.append((str(log_date), _count_buckets(working)))

    # Append a final "Today" row if the last log date is before to_date
    last_log_date = sorted(daily_tx.keys())[-1] if daily_tx else baseline_date
    if last_log_date < to_date:
        snapshots.append((_fmt_today(to_date), _count_buckets(working)))

    # ── 7. Build report rows ──────────────────────────────────────────────────
    data     = []
    prev_act = None
    for date_str, snap in snapshots:
        act   = snap["active"]
        delta = (act - prev_act) if prev_act is not None else None
        data.append(_make_row(date_str, snap, total_hh, delta))
        prev_act = act

    # ── 8. Chart ──────────────────────────────────────────────────────────────
    chart = _build_chart(snapshots, total_hh)
    return data, chart


# ── Helpers ───────────────────────────────────────────────────────────────────

def _fmt_baseline(d):
    return str(d) + "  (Baseline)"


def _fmt_today(d):
    return str(d) + "  (Today)"


def _count_buckets(bucket_map):
    counts = {b: 0 for b in BUCKETS}
    for b in bucket_map.values():
        if b in counts:
            counts[b] += 1
    return counts


def _make_row(date_str, snap, total_hh, delta_active):
    visited = total_hh - snap.get("unvisited", 0)
    active  = snap.get("active", 0)
    cov_pct = round(visited / total_hh * 100, 1) if total_hh else 0.0
    sat_pct = round(active  / total_hh * 100, 1) if total_hh else 0.0

    if delta_active is None:
        delta_str = ""
    elif delta_active > 0:
        delta_str = "+" + str(delta_active)
    else:
        delta_str = str(delta_active)

    return {
        "date":            date_str,
        "total_hh":        total_hh,
        "unvisited":       snap.get("unvisited",       0),
        "missing_both":    snap.get("missing_both",    0),
        "missing_aadhaar": snap.get("missing_aadhaar", 0),
        "missing_income":  snap.get("missing_income",  0),
        "docs_ready":      snap.get("docs_ready",      0),
        "applied":         snap.get("applied",         0),
        "active":          active,
        "rejected":        snap.get("rejected",        0),
        "coverage_pct":    cov_pct,
        "saturation_pct":  sat_pct,
        "delta_active":    delta_str,
    }


def _build_chart(snapshots, total_hh):
    if not total_hh or len(snapshots) < 2:
        return None

    labels   = [s[0] for s in snapshots]
    sat_vals = [
        round(s[1].get("active", 0) / total_hh * 100, 1)
        for s in snapshots
    ]
    cov_vals = [
        round((total_hh - s[1].get("unvisited", 0)) / total_hh * 100, 1)
        for s in snapshots
    ]

    return {
        "data": {
            "labels": labels,
            "datasets": [
                {"name": "Saturation % (Active)", "values": sat_vals},
                {"name": "Coverage % (Visited)",  "values": cov_vals},
            ],
        },
        "type":        "line",
        "colors":      ["#7C3AED", "#2563EB"],
        "fieldtype":   "Percent",
        "title":       "Saturation & Coverage Trend",
        "axisOptions": {"xIsSeries": 1},
    }
