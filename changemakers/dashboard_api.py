"""
WRP Programme Dashboard API
-----------------------------
get_dashboard_overview  — all summary metrics in one call
get_drilldown           — paginated list for any metric at any hierarchy level

Hierarchy levels: org → iu → street → co → hh → individual
"""

import frappe
from frappe.utils import nowdate, now_datetime
import json

# ── Tamil literals used in status fields ────────────────────────────────────
OCCUPIED    = "Occupied/\u0b89\u0bb3\u0bcd\u0bb3\u0ba9\u0bb0\u0bcd"
GOING_AHEAD = "Going Ahead/\u0ba4\u0bc1\u0bb5\u0b99\u0bcd\u0b95\u0bb2\u0bbe\u0bae\u0bcd"
IND_ACTIVE  = "Active- \u0b86\u0b95\u0bcd\u0b9f\u0bbf\u0bb5\u0bcd"

HH_BASE = """
    FROM `tabHousehold Profile-WRP` hh
    JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
    WHERE hh.survay_status = %(occupied)s
      AND hh.availability_for = %(going_ahead)s
"""

BASE_VALS = {"occupied": OCCUPIED, "going_ahead": GOING_AHEAD, "ind_active": IND_ACTIVE}


# ── Scope ────────────────────────────────────────────────────────────────────

def _scope(filters):
    cond, vals = "", {}
    if filters.get("implementing_org"):
        cond += " AND sl.implementing_org = %(implementing_org)s"
        vals["implementing_org"] = filters["implementing_org"]
    if filters.get("intervention_unit"):
        cond += " AND sl.intervention_units = %(iu)s"
        vals["iu"] = filters["intervention_unit"]
    if filters.get("street"):
        cond += " AND sl.name = %(street)s"
        vals["street"] = filters["street"]
    if filters.get("co"):
        cond += " AND sl.added_by_co = %(co)s"
        vals["co"] = filters["co"]
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        org = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "organisation"
        )
        if not org:
            return None, None   # no access
        cond += " AND sl.implementing_org = %(user_org)s"
        vals["user_org"] = org
    return cond, vals


def _v(scope_vals):
    """Merge base vals with scope vals."""
    return {**BASE_VALS, **scope_vals}


# ── Overview ─────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard_overview(filters=None):
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    sc, sv = _scope(filters)
    if sc is None:
        return {"error": "no_access"}

    v = _v(sv)

    # 1. Structure
    struct = frappe.db.sql(f"""
        SELECT
            COUNT(DISTINCT sl.implementing_org)  AS orgs,
            COUNT(DISTINCT sl.intervention_units) AS ius,
            COUNT(DISTINCT sl.name)               AS streets,
            COUNT(DISTINCT sl.added_by_co)        AS cos
        FROM `tabStreet List  - WRP` sl
        WHERE 1=1 {sc}
    """, sv, as_dict=True)[0]

    # Staff role counts — use Frappe role assignments (avoids schema dependency)
    pms = frappe.db.count("Has Role", {"role": "WRP-PM", "parenttype": "User"})
    acs = frappe.db.count("Has Role", {"role": "WRP-AC", "parenttype": "User"})

    # 2. Pipeline (using same bucket logic as saturation report)
    pipeline = _pipeline_counts(sc, v)

    # 3. SLA violations
    sla = _sla_counts(sc, v)

    # 4. Stagnation
    stagnant = _stagnant_count(sc, v)
    visited_no_change_7d = _visited_no_change(sc, v, days=7)

    # 5. CO performance
    co_perf = _co_performance(sc, sv)

    return {
        "structure": {
            "orgs":    int(struct.orgs    or 0),
            "ius":     int(struct.ius     or 0),
            "streets": int(struct.streets or 0),
            "cos":     int(struct.cos     or 0),
            "pms":     pms,
            "acs":     acs,
        },
        "pipeline":  pipeline,
        "alerts": {
            "visited_no_change_7d":   visited_no_change_7d,
            "stagnant_14d":           stagnant,
            "aadhaar_internal_sla":   sla["aadhaar_internal"],
            "aadhaar_external_sla":   sla["aadhaar_external"],
            "income_sla":             sla["income"],
            "cmchis_sla":             sla["cmchis"],
        },
        "co_performance": co_perf,
    }


# ── Pipeline bucket counts ────────────────────────────────────────────────────

def _pipeline_counts(sc, v):
    """Count HHs per pipeline bucket."""
    hh_rows = frappe.db.sql(f"""
        SELECT hh.name AS hh_name, hh.cmchis_status
        {HH_BASE} {sc}
    """, v, as_dict=True)

    ind_rows = frappe.db.sql(f"""
        SELECT ip.hhid, ip.visit_count, ip.aadhaar_status, ip.income_status
        FROM `tabIndividual Profile-WRP` ip
        JOIN `tabHousehold Profile-WRP` hh ON hh.name = ip.hhid
        JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        WHERE ip.status = %(ind_active)s
          AND hh.survay_status = %(occupied)s
          AND hh.availability_for = %(going_ahead)s {sc}
    """, v, as_dict=True)

    from collections import defaultdict
    hh_members = defaultdict(list)
    for r in ind_rows:
        hh_members[r.hhid].append(r)

    AADHAAR_RECEIVED = "Aadhaar Received"
    INCOME_READY = {"Income Cert Received", "Income Cert Expired"}

    counts = {k: 0 for k in [
        "unvisited", "missing_both", "missing_aadhaar",
        "missing_income", "docs_ready", "applied", "active", "rejected"
    ]}

    for r in hh_rows:
        c = (r.cmchis_status or "").lower()
        members = hh_members.get(r.hh_name, [])
        max_v = max((int(m.visit_count or 0) for m in members), default=0)

        if "active" in c:
            bucket = "active"
        elif "rejected" in c:
            bucket = "rejected"
        elif "applied" in c and "not" not in c:
            bucket = "applied"
        elif max_v == 0:
            bucket = "unvisited"
        else:
            has_a = any((m.aadhaar_status or "") == AADHAAR_RECEIVED for m in members)
            has_i = any((m.income_status or "") in INCOME_READY for m in members)
            any_both = any(
                (m.aadhaar_status or "") == AADHAAR_RECEIVED and
                (m.income_status or "") in INCOME_READY
                for m in members
            )
            if any_both:
                bucket = "docs_ready"
            elif has_a:
                bucket = "missing_income"
            elif has_i:
                bucket = "missing_aadhaar"
            else:
                bucket = "missing_both"
        counts[bucket] += 1

    counts["total"] = sum(counts.values())
    return counts


# ── SLA violation counts ──────────────────────────────────────────────────────

def _sla_counts(sc, v):
    def _cnt(extra_cond, extra_vals=None):
        qv = {**v, **(extra_vals or {})}
        row = frappe.db.sql(f"""
            SELECT COUNT(DISTINCT ip.hhid) AS cnt
            FROM `tabIndividual Profile-WRP` ip
            JOIN `tabHousehold Profile-WRP` hh ON hh.name = ip.hhid
            JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
            WHERE ip.status = %(ind_active)s
              AND hh.survay_status = %(occupied)s
              AND hh.availability_for = %(going_ahead)s
              AND hh.cmchis_status NOT LIKE '%%Active%%'
              AND hh.cmchis_status NOT LIKE '%%Rejected%%'
              {extra_cond} {sc}
        """, qv, as_dict=True)
        return int(row[0].cnt if row else 0)

    return {
        "aadhaar_internal": _cnt(
            "AND ip.aadhaar_status LIKE %(pat)s "
            "AND (ip.last_visited_at IS NULL OR DATEDIFF(NOW(), ip.last_visited_at) > 15)",
            {"pat": "%Internal Applied%"},
        ),
        "aadhaar_external": _cnt(
            "AND ip.aadhaar_status LIKE %(pat)s "
            "AND (ip.last_visited_at IS NULL OR DATEDIFF(NOW(), ip.last_visited_at) > 15)",
            {"pat": "%External Applied%"},
        ),
        "income": _cnt(
            "AND ip.income_status LIKE %(pat)s "
            "AND ip.income_status NOT LIKE '%%Received%%' "
            "AND ip.income_status NOT LIKE '%%Expired%%' "
            "AND (ip.last_visited_at IS NULL OR DATEDIFF(NOW(), ip.last_visited_at) > 4)",
            {"pat": "%Applied%"},
        ),
        "cmchis": frappe.db.sql(f"""
            SELECT COUNT(DISTINCT hh.name) AS cnt
            {HH_BASE}
              AND hh.cmchis_status LIKE '%%Applied%%'
              AND hh.cmchis_status NOT LIKE '%%Active%%'
              AND hh.cmchis_status NOT LIKE '%%Rejected%%'
              AND DATEDIFF(NOW(), hh.modified) > 5 {sc}
        """, v, as_dict=True)[0].cnt or 0,
    }


# ── Stagnation ────────────────────────────────────────────────────────────────

def _visited_no_change(sc, v, days=7):
    row = frappe.db.sql(f"""
        SELECT COUNT(DISTINCT hh.name) AS cnt
        {HH_BASE}
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND EXISTS (
              SELECT 1 FROM `tabIndividual Profile-WRP` ip2
              WHERE ip2.hhid = hh.name AND ip2.status = %(ind_active)s AND ip2.visit_count > 0
          )
          AND hh.name NOT IN (
              SELECT DISTINCT hh_name FROM `tabWRP Status Log`
              WHERE DATE(changed_at) >= DATE_SUB(CURDATE(), INTERVAL %(days)s DAY)
              AND hh_name IS NOT NULL
          ) {sc}
    """, {**v, "days": days}, as_dict=True)
    return int(row[0].cnt if row else 0)


def _stagnant_count(sc, v):
    """HHs with 2+ visits and no bucket change in 14 days, not terminal."""
    row = frappe.db.sql(f"""
        SELECT COUNT(DISTINCT hh.name) AS cnt
        {HH_BASE}
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND (
              SELECT SUM(ip2.visit_count) FROM `tabIndividual Profile-WRP` ip2
              WHERE ip2.hhid = hh.name AND ip2.status = %(ind_active)s
          ) >= 2
          AND hh.name NOT IN (
              SELECT DISTINCT hh_name FROM `tabWRP Status Log`
              WHERE DATE(changed_at) >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
              AND hh_name IS NOT NULL
          ) {sc}
    """, v, as_dict=True)
    return int(row[0].cnt if row else 0)


# ── CO performance ────────────────────────────────────────────────────────────

def _co_performance(sc, sv):
    """
    Returns COs grouped by visit-rate bucket (<25, 25-50, 50-75, >75 of target)
    and low-impact COs (many visits, few transitions).
    Target = 30 HH/day.
    """
    # HH assignment counts per CO
    hh_counts = frappe.db.sql(f"""
        SELECT sl.added_by_co AS co, COUNT(DISTINCT hh.name) AS total_hh
        {HH_BASE} {sc}
        GROUP BY sl.added_by_co
    """, _v(sv), as_dict=True)
    hh_map = {r.co: int(r.total_hh) for r in hh_counts if r.co}

    # Log stats per CO over last 30 days
    log_sc = ""
    log_sv = {}
    if sv.get("implementing_org"):
        log_sc += " AND implementing_org = %(implementing_org)s"
        log_sv["implementing_org"] = sv["implementing_org"]
    if sv.get("user_org"):
        log_sc += " AND implementing_org = %(user_org)s"
        log_sv["user_org"] = sv["user_org"]
    if sv.get("co"):
        log_sc += " AND co_id = %(co)s"
        log_sv["co"] = sv["co"]

    log_rows = frappe.db.sql(f"""
        SELECT
            co_id AS co,
            COUNT(DISTINCT CONCAT(DATE(changed_at), '|', hh_name)) AS hh_day_visits,
            COUNT(DISTINCT DATE(changed_at))                         AS active_days,
            SUM(CASE WHEN old_bucket IS NOT NULL AND old_bucket != new_bucket
                     THEN 1 ELSE 0 END)                              AS bucket_changes
        FROM `tabWRP Status Log`
        WHERE changed_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)
          AND co_id IS NOT NULL AND co_id != '' {log_sc}
        GROUP BY co_id
    """, log_sv, as_dict=True)

    # Resolve CO names
    co_names = {
        r.name: r.full_name or r.name
        for r in frappe.get_all("Staff details - WRP", fields=["name", "full_name"])
    }

    TARGET_PER_DAY = 30
    below_25, below_50, below_75, low_impact = [], [], [], []

    for r in log_rows:
        co = r.co
        active_days = int(r.active_days or 1)
        hh_day = int(r.hh_day_visits or 0)
        changes = int(r.bucket_changes or 0)
        total_hh = hh_map.get(co, 0)

        avg_per_day = hh_day / active_days if active_days else 0
        target_total = TARGET_PER_DAY * active_days
        rate_pct = round(hh_day / target_total * 100) if target_total else 0

        entry = {
            "co":           co,
            "co_name":      co_names.get(co, co),
            "total_hh":     total_hh,
            "hh_day_visits":hh_day,
            "active_days":  active_days,
            "avg_per_day":  round(avg_per_day, 1),
            "rate_pct":     rate_pct,
            "bucket_changes": changes,
        }

        if rate_pct < 25:
            below_25.append(entry)
        elif rate_pct < 50:
            below_50.append(entry)
        elif rate_pct < 75:
            below_75.append(entry)

        # Low impact: visited 10+ HH-days but <20% resulted in bucket change
        if hh_day >= 10 and (changes / hh_day) < 0.20:
            entry["impact_ratio"] = round(changes / hh_day * 100, 1)
            low_impact.append(entry)

    for lst in [below_25, below_50, below_75, low_impact]:
        lst.sort(key=lambda x: x["rate_pct"])

    return {
        "below_25":   below_25,
        "below_50":   below_50,
        "below_75":   below_75,
        "low_impact": low_impact,
        "counts": {
            "below_25":   len(below_25),
            "below_50":   len(below_50),
            "below_75":   len(below_75),
            "low_impact": len(low_impact),
        },
    }


# ── Drill-down ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_drilldown(metric, level="org", parent=None, filters=None):
    """
    Generic drill-down for any metric at any hierarchy level.

    metric:  unvisited | visited_no_change_7d | stagnant_14d |
             aadhaar_internal_sla | aadhaar_external_sla |
             income_sla | cmchis_sla |
             co_below_25 | co_below_50 | co_below_75 | co_low_impact
    level:   org | iu | street | co | hh | individual
    parent:  value of the parent level (e.g. org name when level=iu)
    """
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}
    if parent:
        # inject parent into scope
        level_field = {
            "org":    "implementing_org",
            "iu":     "intervention_unit",
            "street": "street",
            "co":     "co",
        }.get(level)
        if level_field:
            filters[level_field] = parent

    sc, sv = _scope(filters)
    if sc is None:
        return {"rows": [], "columns": []}

    v = _v(sv)

    # Dispatch
    dispatch = {
        "unvisited":             _dd_unvisited,
        "visited_no_change_7d":  _dd_visited_no_change,
        "stagnant_14d":          _dd_stagnant,
        "aadhaar_internal_sla":  lambda sc, v: _dd_sla_individuals(sc, v, "%Internal Applied%", 15, "Aadhaar"),
        "aadhaar_external_sla":  lambda sc, v: _dd_sla_individuals(sc, v, "%External Applied%", 15, "Aadhaar"),
        "income_sla":            lambda sc, v: _dd_sla_individuals(sc, v, "%Applied%",           4,  "Income"),
        "cmchis_sla":            _dd_cmchis_sla,
        "co_below_25":           lambda sc, sv: _dd_co_perf(sc, sv, max_rate=25),
        "co_below_50":           lambda sc, sv: _dd_co_perf(sc, sv, min_rate=25, max_rate=50),
        "co_below_75":           lambda sc, sv: _dd_co_perf(sc, sv, min_rate=50, max_rate=75),
        "co_low_impact":         _dd_co_low_impact,
    }

    fn = dispatch.get(metric)
    if not fn:
        return {"rows": [], "columns": [], "error": f"Unknown metric: {metric}"}

    # For CO metrics pass sv not v
    if metric.startswith("co_"):
        rows, columns = fn(sc, sv)
    else:
        rows, columns = fn(sc, v)

    # If not at leaf level, group by next hierarchy
    if level in ("org", "iu", "street") and not metric.startswith("co_"):
        rows, columns = _aggregate_by_level(rows, level, metric)

    return {"rows": rows, "columns": columns, "metric": metric, "level": level}


def _aggregate_by_level(rows, level, metric):
    """Roll up HH/individual rows into org/iu/street summary."""
    group_field = {"org": "implementing_org", "iu": "iu", "street": "street"}.get(level, "implementing_org")
    from collections import defaultdict
    groups = defaultdict(list)
    for r in rows:
        key = r.get(group_field) or r.get("implementing_org") or "Unknown"
        groups[key].append(r)
    agg = [{"name": k, "count": len(v), "_rows": v} for k, v in sorted(groups.items())]
    cols = [
        {"label": level.upper(), "fieldname": "name"},
        {"label": "Count",       "fieldname": "count"},
    ]
    return agg, cols


# ── Drill-down leaf queries ───────────────────────────────────────────────────

def _hh_select(extra_fields=""):
    return f"""
        SELECT
            hh.name AS hh_id,
            hh.respondent,
            hh.cmchis_status,
            sl.name AS street,
            sl.intervention_units AS iu,
            sl.implementing_org,
            sl.added_by_co AS co
            {extra_fields}
        {HH_BASE}
    """

def _dd_unvisited(sc, v):
    rows = frappe.db.sql(f"""
        {_hh_select()}
          AND NOT EXISTS (
              SELECT 1 FROM `tabIndividual Profile-WRP` ip2
              WHERE ip2.hhid = hh.name AND ip2.status = %(ind_active)s AND ip2.visit_count > 0
          ) {sc}
        ORDER BY sl.implementing_org, sl.name
    """, v, as_dict=True)
    cols = [
        {"label": "Household",    "fieldname": "hh_id"},
        {"label": "Respondent",   "fieldname": "respondent"},
        {"label": "Street",       "fieldname": "street"},
        {"label": "Org",          "fieldname": "implementing_org"},
        {"label": "CO",           "fieldname": "co"},
    ]
    return rows, cols


def _dd_visited_no_change(sc, v):
    rows = frappe.db.sql(f"""
        {_hh_select(", (SELECT MAX(DATE(changed_at)) FROM `tabWRP Status Log` l WHERE l.hh_name = hh.name) AS last_change")}
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND EXISTS (
              SELECT 1 FROM `tabIndividual Profile-WRP` ip2
              WHERE ip2.hhid = hh.name AND ip2.status = %(ind_active)s AND ip2.visit_count > 0
          )
          AND hh.name NOT IN (
              SELECT DISTINCT hh_name FROM `tabWRP Status Log`
              WHERE DATE(changed_at) >= DATE_SUB(CURDATE(), INTERVAL 7 DAY)
              AND hh_name IS NOT NULL
          ) {sc}
        ORDER BY last_change ASC
    """, v, as_dict=True)
    cols = [
        {"label": "Household",    "fieldname": "hh_id"},
        {"label": "Respondent",   "fieldname": "respondent"},
        {"label": "CMCHIS Status","fieldname": "cmchis_status"},
        {"label": "Last Change",  "fieldname": "last_change"},
        {"label": "Street",       "fieldname": "street"},
        {"label": "CO",           "fieldname": "co"},
    ]
    return rows, cols


def _dd_stagnant(sc, v):
    rows = frappe.db.sql(f"""
        {_hh_select(", (SELECT MAX(DATE(changed_at)) FROM `tabWRP Status Log` l WHERE l.hh_name = hh.name) AS last_change, (SELECT SUM(ip2.visit_count) FROM `tabIndividual Profile-WRP` ip2 WHERE ip2.hhid = hh.name AND ip2.status = %(ind_active)s) AS total_visits")}
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND (
              SELECT SUM(ip2.visit_count) FROM `tabIndividual Profile-WRP` ip2
              WHERE ip2.hhid = hh.name AND ip2.status = %(ind_active)s
          ) >= 2
          AND hh.name NOT IN (
              SELECT DISTINCT hh_name FROM `tabWRP Status Log`
              WHERE DATE(changed_at) >= DATE_SUB(CURDATE(), INTERVAL 14 DAY)
              AND hh_name IS NOT NULL
          ) {sc}
        ORDER BY last_change ASC
    """, v, as_dict=True)
    cols = [
        {"label": "Household",    "fieldname": "hh_id"},
        {"label": "Respondent",   "fieldname": "respondent"},
        {"label": "Visits",       "fieldname": "total_visits"},
        {"label": "Last Change",  "fieldname": "last_change"},
        {"label": "CMCHIS Status","fieldname": "cmchis_status"},
        {"label": "Street",       "fieldname": "street"},
        {"label": "CO",           "fieldname": "co"},
    ]
    return rows, cols


def _dd_sla_individuals(sc, v, status_pat, sla_days, doc_field):
    col = "aadhaar_status" if doc_field == "Aadhaar" else "income_status"
    extra_cond = ""
    if doc_field == "Income":
        extra_cond = " AND ip.income_status NOT LIKE '%%Received%%' AND ip.income_status NOT LIKE '%%Expired%%'"
    rows = frappe.db.sql(f"""
        SELECT
            ip.name AS individual_id,
            ip.hhid,
            ip.{col} AS doc_status,
            DATEDIFF(NOW(), ip.last_visited_at) AS days_since_visit,
            DATEDIFF(NOW(), ip.last_visited_at) - %(sla)s AS days_overdue,
            ip.last_visited_at,
            sl.name AS street,
            sl.intervention_units AS iu,
            sl.implementing_org,
            sl.added_by_co AS co
        FROM `tabIndividual Profile-WRP` ip
        JOIN `tabHousehold Profile-WRP` hh ON hh.name = ip.hhid
        JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        WHERE ip.status = %(ind_active)s
          AND hh.survay_status = %(occupied)s
          AND hh.availability_for = %(going_ahead)s
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND ip.{col} LIKE %(pat)s
          {extra_cond}
          AND (ip.last_visited_at IS NULL OR DATEDIFF(NOW(), ip.last_visited_at) > %(sla)s) {sc}
        ORDER BY days_overdue DESC
    """, {**v, "pat": status_pat, "sla": sla_days}, as_dict=True)
    cols = [
        {"label": "Household",    "fieldname": "hhid"},
        {"label": f"{doc_field} Status", "fieldname": "doc_status"},
        {"label": "Days Overdue", "fieldname": "days_overdue"},
        {"label": "Last Visit",   "fieldname": "last_visited_at"},
        {"label": "Street",       "fieldname": "street"},
        {"label": "CO",           "fieldname": "co"},
    ]
    return rows, cols


def _dd_cmchis_sla(sc, v):
    rows = frappe.db.sql(f"""
        SELECT
            hh.name AS hh_id,
            hh.respondent,
            hh.cmchis_status,
            DATEDIFF(NOW(), hh.modified) AS days_since_change,
            DATEDIFF(NOW(), hh.modified) - 5 AS days_overdue,
            hh.modified AS last_modified,
            sl.name AS street,
            sl.intervention_units AS iu,
            sl.implementing_org,
            sl.added_by_co AS co
        {HH_BASE}
          AND hh.cmchis_status LIKE '%%Applied%%'
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND DATEDIFF(NOW(), hh.modified) > 5 {sc}
        ORDER BY days_overdue DESC
    """, v, as_dict=True)
    cols = [
        {"label": "Household",    "fieldname": "hh_id"},
        {"label": "Respondent",   "fieldname": "respondent"},
        {"label": "CMCHIS Status","fieldname": "cmchis_status"},
        {"label": "Days Overdue", "fieldname": "days_overdue"},
        {"label": "Street",       "fieldname": "street"},
        {"label": "CO",           "fieldname": "co"},
    ]
    return rows, cols


def _dd_co_perf(sc, sv, min_rate=0, max_rate=100):
    perf = _co_performance(sc, sv)
    all_cos = perf["below_25"] + perf["below_50"] + perf["below_75"]
    rows = [
        r for r in all_cos
        if min_rate <= r["rate_pct"] < max_rate
    ]
    rows.sort(key=lambda x: x["rate_pct"])
    cols = [
        {"label": "CO",             "fieldname": "co_name"},
        {"label": "Visit Rate %",   "fieldname": "rate_pct"},
        {"label": "HH-Day Visits",  "fieldname": "hh_day_visits"},
        {"label": "Active Days",    "fieldname": "active_days"},
        {"label": "Avg/Day",        "fieldname": "avg_per_day"},
        {"label": "Total HH",       "fieldname": "total_hh"},
    ]
    return rows, cols


def _dd_co_low_impact(sc, sv):
    perf = _co_performance(sc, sv)
    rows = perf["low_impact"]
    cols = [
        {"label": "CO",              "fieldname": "co_name"},
        {"label": "HH-Day Visits",   "fieldname": "hh_day_visits"},
        {"label": "Bucket Changes",  "fieldname": "bucket_changes"},
        {"label": "Impact %",        "fieldname": "impact_ratio"},
        {"label": "Active Days",     "fieldname": "active_days"},
        {"label": "Total HH",        "fieldname": "total_hh"},
    ]
    return rows, cols
