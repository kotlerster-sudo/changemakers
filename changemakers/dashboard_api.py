"""
WRP Programme Dashboard API
-----------------------------
get_dashboard_overview  — all summary metrics in one call
get_drilldown           — paginated list for any metric at any hierarchy level

Hierarchy levels: org → iu → street → co → hh → individual
"""

import frappe
from frappe.utils import nowdate, now_datetime, get_first_day, getdate
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

    # Staff role counts — always scoped to same streets as the rest of the dashboard.
    # Uses a subquery so street/IU/org filters all work correctly.
    def _wrp_role_count(role):
        r = frappe.db.sql(f"""
            SELECT COUNT(DISTINCT hr.parent) AS cnt
            FROM `tabHas Role` hr
            JOIN `tabStaff details - WRP` sd ON sd.mail_id = hr.parent
            WHERE hr.role = %(role)s AND hr.parenttype = 'User'
              AND sd.organisation IN (
                  SELECT DISTINCT sl.implementing_org
                  FROM `tabStreet List  - WRP` sl
                  WHERE 1=1 {sc}
              )
        """, {**sv, "role": role}, as_dict=True)
        return int(r[0].cnt if r else 0)
    pms = _wrp_role_count("WRP-PM")
    acs = _wrp_role_count("WRP-AC")

    # 2. Pipeline (using same bucket logic as saturation report)
    pipeline = _pipeline_counts(sc, v)

    # 3. SLA violations
    sla = _sla_counts(sc, v)

    # 4. Stagnation
    stagnant = _stagnant_count(sc, v)
    visited_no_change_7d = _visited_no_change(sc, v, days=7)

    # 5. CO performance — date range defaults to current calendar month
    today      = nowdate()
    date_from  = filters.get("date_from") or str(get_first_day(today))
    date_to    = filters.get("date_to")   or today
    co_perf = _co_performance(sc, sv, date_from, date_to)

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
    """
    Use tabWRP Status Log to find when the status was last set to the 'applied'
    value — that is the real SLA clock start, not last_visited_at or hh.modified.
    """
    def _cnt_ind(field, pat, sla_days, extra_cond=""):
        # field is a safe internal constant (aadhaar_status / income_status)
        row = frappe.db.sql(f"""
            SELECT COUNT(DISTINCT ip.name) AS cnt
            FROM `tabIndividual Profile-WRP` ip
            JOIN `tabHousehold Profile-WRP` hh ON hh.name = ip.hhid
            JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
            JOIN (
                SELECT individual, MAX(changed_at) AS applied_at
                FROM `tabWRP Status Log`
                WHERE field_changed = %(field_name)s
                  AND new_value LIKE %(pat)s
                GROUP BY individual
            ) la ON la.individual = ip.name
            WHERE ip.status = %(ind_active)s
              AND hh.survay_status = %(occupied)s
              AND hh.availability_for = %(going_ahead)s
              AND hh.cmchis_status NOT LIKE '%%Active%%'
              AND hh.cmchis_status NOT LIKE '%%Rejected%%'
              AND ip.{field} LIKE %(pat)s
              {extra_cond}
              AND DATEDIFF(NOW(), la.applied_at) > %(sla)s {sc}
        """, {**v, "pat": pat, "sla": sla_days, "field_name": field}, as_dict=True)
        return int(row[0].cnt if row else 0)

    cmchis_row = frappe.db.sql(f"""
        SELECT COUNT(DISTINCT hh.name) AS cnt
        FROM `tabHousehold Profile-WRP` hh
        JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        JOIN (
            SELECT hh_name, MAX(changed_at) AS applied_at
            FROM `tabWRP Status Log`
            WHERE field_changed = 'cmchis_status'
              AND new_value LIKE '%%Applied%%'
              AND new_value NOT LIKE '%%Not Applied%%'
            GROUP BY hh_name
        ) la ON la.hh_name = hh.name
        WHERE hh.survay_status = %(occupied)s
          AND hh.availability_for = %(going_ahead)s
          AND hh.cmchis_status LIKE '%%Applied%%'
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND DATEDIFF(NOW(), la.applied_at) > 5 {sc}
    """, v, as_dict=True)

    return {
        "aadhaar_internal": _cnt_ind("aadhaar_status", "%Internal Applied%", 15),
        "aadhaar_external": _cnt_ind("aadhaar_status", "%External Applied%", 15),
        "income": _cnt_ind(
            "income_status", "%Applied%", 4,
            "AND ip.income_status NOT LIKE '%%Received%%' AND ip.income_status NOT LIKE '%%Expired%%'",
        ),
        "cmchis": int(cmchis_row[0].cnt if cmchis_row else 0),
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

def _co_performance(sc, sv, date_from=None, date_to=None):
    """
    Returns COs grouped by update-rate bucket (<25, 25-50, 50-75, >75 of target)
    and low-impact COs (many visits, few transitions).
    Target = 30 HH/day. Window defaults to current calendar month.
    """
    today     = nowdate()
    date_from = date_from or str(get_first_day(today))
    date_to   = date_to   or today
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

    date_vals = {**log_sv, "date_from": date_from, "date_to": date_to}

    # Update rate: distinct (date × hh) from Status Log — visits that changed something
    log_rows = frappe.db.sql(f"""
        SELECT
            co_id AS co,
            COUNT(DISTINCT CONCAT(DATE(changed_at), '|', hh_name)) AS update_hh_days,
            COUNT(DISTINCT DATE(changed_at))                         AS active_days,
            SUM(CASE WHEN old_bucket IS NOT NULL AND old_bucket != new_bucket
                     THEN 1 ELSE 0 END)                              AS bucket_changes
        FROM `tabWRP Status Log`
        WHERE DATE(changed_at) BETWEEN %(date_from)s AND %(date_to)s
          AND co_id IS NOT NULL AND co_id != '' {log_sc}
        GROUP BY co_id
    """, date_vals, as_dict=True)

    # Raw visit rate: distinct (date × hh) and distinct active days from WRP Visit Log
    visit_rows = frappe.db.sql(f"""
        SELECT
            co_id AS co,
            COUNT(DISTINCT CONCAT(DATE(visited_at), '|', hh_name)) AS raw_hh_days,
            COUNT(DISTINCT DATE(visited_at))                         AS visit_active_days
        FROM `tabWRP Visit Log`
        WHERE DATE(visited_at) BETWEEN %(date_from)s AND %(date_to)s
          AND co_id IS NOT NULL AND co_id != '' {log_sc}
        GROUP BY co_id
    """, date_vals, as_dict=True)
    raw_visit_map = {r.co: (int(r.raw_hh_days or 0), int(r.visit_active_days or 0)) for r in visit_rows}

    # Resolve CO names
    co_names = {
        r.name: r.full_name or r.name
        for r in frappe.get_all("Staff details - WRP", fields=["name", "full_name"])
    }

    TARGET_PER_DAY = 30
    below_25, below_50, below_75, low_impact = [], [], [], []

    # Also include COs that appear in visit log but not in status log
    all_co_ids = set(r.co for r in log_rows) | set(raw_visit_map.keys())
    log_map = {r.co: r for r in log_rows}

    for co in all_co_ids:
        r           = log_map.get(co)
        update_days = int(r.update_hh_days or 0) if r else 0
        status_active_days = int(r.active_days or 0) if r else 0
        raw_days, visit_active_days = raw_visit_map.get(co, (0, 0))
        changes     = int(r.bucket_changes or 0) if r else 0
        total_hh    = hh_map.get(co, 0)

        # Active days = max of status-log days and visit-log days
        # Ensures COs who visited without updating aren't penalised
        active_days  = max(status_active_days, visit_active_days) or 1

        target_total  = TARGET_PER_DAY * active_days
        update_pct    = round(update_days / target_total * 100) if target_total else 0
        raw_visit_pct = round(raw_days    / target_total * 100) if target_total else 0

        entry = {
            "co":              co,
            "co_name":         co_names.get(co, co),
            "total_hh":        total_hh,
            "update_hh_days":  update_days,
            "raw_hh_days":     raw_days,
            "active_days":     active_days,
            "update_pct":      update_pct,
            "raw_visit_pct":   raw_visit_pct,
            "rate_pct":        update_pct,   # buckets still use update rate
            "bucket_changes":  changes,
        }

        if update_pct < 25:
            below_25.append(entry)
        elif update_pct < 50:
            below_50.append(entry)
        elif update_pct < 75:
            below_75.append(entry)

        # Low impact: 10+ update-days but <20% resulted in a bucket change
        if update_days >= 10 and (changes / update_days) < 0.20:
            entry["impact_ratio"] = round(changes / update_days * 100, 1)
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
        # inject parent into scope — map current level to the PARENT's filter field
        # (e.g. arriving at "iu" means the parent was an org → filter implementing_org)
        parent_field = {
            "iu":         "implementing_org",
            "street":     "intervention_unit",
            "co":         "street",
            "hh":         "co",
            "individual": "co",
        }.get(level)
        if parent_field:
            filters[parent_field] = parent

    sc, sv = _scope(filters)
    if sc is None:
        return {"rows": [], "columns": []}

    v = _v(sv)

    # Dispatch
    dispatch = {
        "unvisited":             _dd_unvisited,
        "missing_both":          lambda sc, v: _dd_pipeline_bucket(sc, v, "missing_both"),
        "missing_aadhaar":       lambda sc, v: _dd_pipeline_bucket(sc, v, "missing_aadhaar"),
        "missing_income":        lambda sc, v: _dd_pipeline_bucket(sc, v, "missing_income"),
        "docs_ready":            lambda sc, v: _dd_pipeline_bucket(sc, v, "docs_ready"),
        "applied":               lambda sc, v: _dd_pipeline_bucket(sc, v, "applied"),
        "active":                lambda sc, v: _dd_pipeline_bucket(sc, v, "active"),
        "rejected":              lambda sc, v: _dd_pipeline_bucket(sc, v, "rejected"),
        "visited_no_change_7d":  _dd_visited_no_change,
        "stagnant_14d":          _dd_stagnant,
        "aadhaar_internal_sla":  lambda sc, v: _dd_sla_individuals(sc, v, "aadhaar_status", "%Internal Applied%", 15, "Aadhaar"),
        "aadhaar_external_sla":  lambda sc, v: _dd_sla_individuals(sc, v, "aadhaar_status", "%External Applied%", 15, "Aadhaar"),
        "income_sla":            lambda sc, v: _dd_sla_individuals(sc, v, "income_status",  "%Applied%",           4, "Income"),
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

def _dd_pipeline_bucket(sc, v, bucket):
    """Drilldown for any pipeline bucket except unvisited (which has its own fn)."""
    # CMCHIS-status based buckets — simple HH-level filter
    if bucket == "active":
        extra = "AND hh.cmchis_status LIKE '%%Active%%'"
    elif bucket == "rejected":
        extra = "AND hh.cmchis_status LIKE '%%Rejected%%'"
    elif bucket == "applied":
        # "applied" in status AND "not" not in status (mirrors Python bucket logic)
        extra = ("AND LOWER(hh.cmchis_status) LIKE '%%applied%%' "
                 "AND LOWER(hh.cmchis_status) NOT LIKE '%%not%%' "
                 "AND hh.cmchis_status NOT LIKE '%%Active%%' "
                 "AND hh.cmchis_status NOT LIKE '%%Rejected%%'")
    else:
        # Visited, not terminal, not applied — differentiated by doc status
        not_terminal = ("AND hh.cmchis_status NOT LIKE '%%Active%%' "
                        "AND hh.cmchis_status NOT LIKE '%%Rejected%%' "
                        "AND NOT (LOWER(hh.cmchis_status) LIKE '%%applied%%' "
                        "         AND LOWER(hh.cmchis_status) NOT LIKE '%%not%%') ")
        visited      = ("AND EXISTS (SELECT 1 FROM `tabIndividual Profile-WRP` iv "
                        "  WHERE iv.hhid = hh.name AND iv.status = %(ind_active)s "
                        "  AND iv.visit_count > 0) ")
        no_both      = ("AND NOT EXISTS (SELECT 1 FROM `tabIndividual Profile-WRP` im "
                        "  WHERE im.hhid = hh.name AND im.status = %(ind_active)s "
                        "  AND im.aadhaar_status = 'Aadhaar Received' "
                        "  AND im.income_status IN ('Income Cert Received','Income Cert Expired')) ")
        has_aadhaar  = ("AND EXISTS (SELECT 1 FROM `tabIndividual Profile-WRP` im "
                        "  WHERE im.hhid = hh.name AND im.status = %(ind_active)s "
                        "  AND im.aadhaar_status = 'Aadhaar Received') ")
        no_aadhaar   = ("AND NOT EXISTS (SELECT 1 FROM `tabIndividual Profile-WRP` im "
                        "  WHERE im.hhid = hh.name AND im.status = %(ind_active)s "
                        "  AND im.aadhaar_status = 'Aadhaar Received') ")
        has_income   = ("AND EXISTS (SELECT 1 FROM `tabIndividual Profile-WRP` im "
                        "  WHERE im.hhid = hh.name AND im.status = %(ind_active)s "
                        "  AND im.income_status IN ('Income Cert Received','Income Cert Expired')) ")
        no_income    = ("AND NOT EXISTS (SELECT 1 FROM `tabIndividual Profile-WRP` im "
                        "  WHERE im.hhid = hh.name AND im.status = %(ind_active)s "
                        "  AND im.income_status IN ('Income Cert Received','Income Cert Expired')) ")

        if bucket == "docs_ready":
            extra = not_terminal + visited + has_aadhaar + has_income
        elif bucket == "missing_both":
            extra = not_terminal + visited + no_both + no_aadhaar + no_income
        elif bucket == "missing_aadhaar":
            extra = not_terminal + visited + no_both + no_aadhaar + has_income
        elif bucket == "missing_income":
            extra = not_terminal + visited + no_both + has_aadhaar + no_income
        else:
            extra = not_terminal + visited

    rows = frappe.db.sql(f"""
        {_hh_select()}
          {extra} {sc}
        ORDER BY sl.implementing_org, sl.name
    """, v, as_dict=True)

    cols = [
        {"label": "Household",    "fieldname": "hh_id"},
        {"label": "Respondent",   "fieldname": "respondent"},
        {"label": "CMCHIS Status","fieldname": "cmchis_status"},
        {"label": "Street",       "fieldname": "street"},
        {"label": "Org",          "fieldname": "implementing_org"},
        {"label": "CO",           "fieldname": "co"},
    ]
    return rows, cols


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


def _dd_sla_individuals(sc, v, field, status_pat, sla_days, doc_label):
    extra_cond = ""
    if field == "income_status":
        extra_cond = " AND ip.income_status NOT LIKE '%%Received%%' AND ip.income_status NOT LIKE '%%Expired%%'"
    rows = frappe.db.sql(f"""
        SELECT
            ip.name AS individual_id,
            ip.hhid,
            ip.{field} AS doc_status,
            la.applied_at,
            DATEDIFF(NOW(), la.applied_at)           AS days_in_status,
            DATEDIFF(NOW(), la.applied_at) - %(sla)s AS days_overdue,
            sl.name AS street,
            sl.intervention_units AS iu,
            sl.implementing_org,
            sl.added_by_co AS co
        FROM `tabIndividual Profile-WRP` ip
        JOIN `tabHousehold Profile-WRP` hh ON hh.name = ip.hhid
        JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        JOIN (
            SELECT individual, MAX(changed_at) AS applied_at
            FROM `tabWRP Status Log`
            WHERE field_changed = %(field_name)s
              AND new_value LIKE %(pat)s
            GROUP BY individual
        ) la ON la.individual = ip.name
        WHERE ip.status = %(ind_active)s
          AND hh.survay_status = %(occupied)s
          AND hh.availability_for = %(going_ahead)s
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND ip.{field} LIKE %(pat)s
          {extra_cond}
          AND DATEDIFF(NOW(), la.applied_at) > %(sla)s {sc}
        ORDER BY days_overdue DESC
    """, {**v, "pat": status_pat, "sla": sla_days, "field_name": field}, as_dict=True)
    cols = [
        {"label": "Household",           "fieldname": "hhid"},
        {"label": f"{doc_label} Status", "fieldname": "doc_status"},
        {"label": "Applied At",          "fieldname": "applied_at"},
        {"label": "Days Overdue",        "fieldname": "days_overdue"},
        {"label": "Street",              "fieldname": "street"},
        {"label": "CO",                  "fieldname": "co"},
    ]
    return rows, cols


def _dd_cmchis_sla(sc, v):
    rows = frappe.db.sql(f"""
        SELECT
            hh.name AS hh_id,
            hh.respondent,
            hh.cmchis_status,
            la.applied_at,
            DATEDIFF(NOW(), la.applied_at)      AS days_in_status,
            DATEDIFF(NOW(), la.applied_at) - 5  AS days_overdue,
            sl.name AS street,
            sl.intervention_units AS iu,
            sl.implementing_org,
            sl.added_by_co AS co
        FROM `tabHousehold Profile-WRP` hh
        JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        JOIN (
            SELECT hh_name, MAX(changed_at) AS applied_at
            FROM `tabWRP Status Log`
            WHERE field_changed = 'cmchis_status'
              AND new_value LIKE '%%Applied%%'
              AND new_value NOT LIKE '%%Not Applied%%'
            GROUP BY hh_name
        ) la ON la.hh_name = hh.name
        WHERE hh.survay_status = %(occupied)s
          AND hh.availability_for = %(going_ahead)s
          AND hh.cmchis_status LIKE '%%Applied%%'
          AND hh.cmchis_status NOT LIKE '%%Active%%'
          AND hh.cmchis_status NOT LIKE '%%Rejected%%'
          AND DATEDIFF(NOW(), la.applied_at) > 5 {sc}
        ORDER BY days_overdue DESC
    """, v, as_dict=True)
    cols = [
        {"label": "Household",    "fieldname": "hh_id"},
        {"label": "Respondent",   "fieldname": "respondent"},
        {"label": "CMCHIS Status","fieldname": "cmchis_status"},
        {"label": "Applied At",   "fieldname": "applied_at"},
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
        {"label": "CO",              "fieldname": "co_name"},
        {"label": "Update Rate %",   "fieldname": "update_pct"},
        {"label": "Visit Rate %",    "fieldname": "raw_visit_pct"},
        {"label": "Update Days",     "fieldname": "update_hh_days"},
        {"label": "Raw Visit Days",  "fieldname": "raw_hh_days"},
        {"label": "Active Days",     "fieldname": "active_days"},
        {"label": "Total HH",        "fieldname": "total_hh"},
    ]
    return rows, cols


def _dd_co_low_impact(sc, sv):
    perf = _co_performance(sc, sv)
    rows = perf["low_impact"]
    cols = [
        {"label": "CO",              "fieldname": "co_name"},
        {"label": "Update Days",     "fieldname": "update_hh_days"},
        {"label": "Raw Visit Days",  "fieldname": "raw_hh_days"},
        {"label": "Bucket Changes",  "fieldname": "bucket_changes"},
        {"label": "Impact %",        "fieldname": "impact_ratio"},
        {"label": "Active Days",     "fieldname": "active_days"},
        {"label": "Total HH",        "fieldname": "total_hh"},
    ]
    return rows, cols


# ── Application Trends ───────────────────────────────────────────────────────

def _trends_scope(filters):
    """Build scope cond+vals for Status Log queries, with user-org restriction."""
    sc = ""
    sv = {}
    if filters.get("implementing_org"):
        sc += " AND implementing_org = %(org)s"
        sv["org"] = filters["implementing_org"]
    if filters.get("intervention_unit"):
        sc += " AND intervention_unit = %(iu)s"
        sv["iu"] = filters["intervention_unit"]
    if filters.get("ac"):
        sc += " AND ac_name = %(ac)s"
        sv["ac"] = filters["ac"]
    if filters.get("street"):
        sc += " AND street_name = %(street)s"
        sv["street"] = filters["street"]
    if filters.get("co"):
        sc += " AND co_id = %(co)s"
        sv["co"] = filters["co"]
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        org = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "organisation"
        )
        if org:
            sc += " AND implementing_org = %(user_org)s"
            sv["user_org"] = org
    return sc, sv


# field → (SQL pattern, exclude pattern, count column)
# CMCHIS is household-level so count hh_name; Aadhaar/Income are individual-level.
_METRIC_DEF = {
    "aadhaar": ("aadhaar_status", "%Applied%",            None,               "individual"),
    "income":  ("income_status",  "%Income Cert Applied%", None,              "individual"),
    "cmchis":  ("cmchis_status",  "%Applied%",            "%Not Applied%",    "hh_name"),
}


@frappe.whitelist()
def get_application_trends(date_from=None, date_to=None, group_by="day", filters=None):
    """
    Per-period counts of Aadhaar, Income Cert, and CMCHIS applications.
    group_by: "day" | "week" | "month"
    Returns {aadhaar, income, cmchis} each as list of {period, label, count},
    plus {totals} as {aadhaar, income, cmchis} counts over the full period.
    """
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    today     = nowdate()
    date_from = date_from or str(get_first_day(today))
    date_to   = date_to   or today

    if group_by == "month":
        period_expr = "DATE_FORMAT(changed_at, '%%Y-%%m')"
        label_expr  = "DATE_FORMAT(changed_at, '%%b %%Y')"
    elif group_by == "week":
        period_expr = "DATE_FORMAT(DATE_SUB(changed_at, INTERVAL WEEKDAY(changed_at) DAY), '%%Y-%%m-%%d')"
        label_expr  = "DATE_FORMAT(DATE_SUB(changed_at, INTERVAL WEEKDAY(changed_at) DAY), '%%d %%b')"
    else:
        period_expr = "DATE(changed_at)"
        label_expr  = "DATE_FORMAT(changed_at, '%%d %%b')"

    sc, sv = _trends_scope(filters)
    sv.update({"date_from": date_from, "date_to": date_to})

    def _fetch(field, pattern, exclude, count_col):
        excl = f"AND new_value NOT LIKE %(excl)s" if exclude else ""
        qv   = {**sv, "field": field, "pattern": pattern}
        if exclude:
            qv["excl"] = exclude
        rows = frappe.db.sql(f"""
            SELECT {period_expr} AS period,
                   {label_expr}  AS label,
                   COUNT(DISTINCT {count_col}) AS cnt
            FROM `tabWRP Status Log`
            WHERE DATE(changed_at) BETWEEN %(date_from)s AND %(date_to)s
              AND field_changed = %(field)s
              AND new_value LIKE %(pattern)s
              {excl} {sc}
            GROUP BY period
            ORDER BY period
        """, qv, as_dict=True)
        return [{"period": str(r.period), "label": str(r.label), "count": int(r.cnt)} for r in rows]

    def _total(field, pattern, exclude, count_col):
        # Cumulative up to date_to — counts every distinct entity that was ever
        # logged with this status transition up to the end of the selected window.
        # This avoids undercounting when applications started before date_from.
        excl = f"AND new_value NOT LIKE %(excl)s" if exclude else ""
        qv   = {**sv, "field": field, "pattern": pattern}
        if exclude:
            qv["excl"] = exclude
        row = frappe.db.sql(f"""
            SELECT COUNT(DISTINCT {count_col}) AS cnt
            FROM `tabWRP Status Log`
            WHERE DATE(changed_at) <= %(date_to)s
              AND field_changed = %(field)s
              AND new_value LIKE %(pattern)s
              {excl} {sc}
        """, qv, as_dict=True)
        return int(row[0].cnt if row else 0)

    result = {}
    totals = {}
    for key, (field, pattern, exclude, count_col) in _METRIC_DEF.items():
        result[key] = _fetch(field, pattern, exclude, count_col)
        totals[key] = _total(field, pattern, exclude, count_col)

    result["totals"] = totals
    return result


@frappe.whitelist()
def get_application_drilldown(metric, date_from, date_to, level="org", filters=None):
    """
    Drilldown for a summary card.
    metric: aadhaar | income | cmchis
    level:  org | iu | street | hh
    filters: {implementing_org, intervention_unit, street_name, ac, co}
    """
    if isinstance(filters, str):
        filters = json.loads(filters)
    filters = filters or {}

    if metric not in _METRIC_DEF:
        return []

    field, pattern, exclude, count_col = _METRIC_DEF[metric]
    sc, sv = _trends_scope(filters)
    sv.update({"date_from": date_from, "date_to": date_to,
               "field": field, "pattern": pattern})

    excl = f"AND new_value NOT LIKE %(excl)s" if exclude else ""
    if exclude:
        sv["excl"] = exclude

    base_where = f"""
        WHERE DATE(changed_at) BETWEEN %(date_from)s AND %(date_to)s
          AND field_changed = %(field)s
          AND new_value LIKE %(pattern)s
          {excl} {sc}
    """

    if level == "org":
        rows = frappe.db.sql(f"""
            SELECT implementing_org AS label,
                   COUNT(DISTINCT {count_col}) AS cnt
            FROM `tabWRP Status Log` {base_where}
            GROUP BY implementing_org
            ORDER BY cnt DESC
        """, sv, as_dict=True)
        return [{"label": r.label or "—", "count": int(r.cnt), "key": r.label} for r in rows]

    if level == "iu":
        rows = frappe.db.sql(f"""
            SELECT intervention_unit AS label,
                   COUNT(DISTINCT {count_col}) AS cnt
            FROM `tabWRP Status Log` {base_where}
            GROUP BY intervention_unit
            ORDER BY cnt DESC
        """, sv, as_dict=True)
        return [{"label": r.label or "—", "count": int(r.cnt), "key": r.label} for r in rows]

    if level == "street":
        rows = frappe.db.sql(f"""
            SELECT street_name AS label,
                   COUNT(DISTINCT {count_col}) AS cnt
            FROM `tabWRP Status Log` {base_where}
            GROUP BY street_name
            ORDER BY cnt DESC
        """, sv, as_dict=True)
        return [{"label": r.label or "—", "count": int(r.cnt), "key": r.label} for r in rows]

    if level == "hh":
        if metric == "cmchis":
            rows = frappe.db.sql(f"""
                SELECT hh_name, street_name, intervention_unit, implementing_org,
                       ac_name, co_name, MAX(DATE(changed_at)) AS applied_on
                FROM `tabWRP Status Log` {base_where}
                GROUP BY hh_name, street_name, intervention_unit, implementing_org, ac_name, co_name
                ORDER BY applied_on DESC
            """, sv, as_dict=True)
            return [{
                "hh":     r.hh_name, "street": r.street_name,
                "iu":     r.intervention_unit, "org": r.implementing_org,
                "ac":     r.ac_name, "co": r.co_name, "date": str(r.applied_on),
            } for r in rows]
        else:
            rows = frappe.db.sql(f"""
                SELECT individual, hh_name, street_name, co_name,
                       MAX(DATE(changed_at)) AS applied_on
                FROM `tabWRP Status Log` {base_where}
                  AND individual IS NOT NULL AND individual != ''
                GROUP BY individual, hh_name, street_name, co_name
                ORDER BY applied_on DESC
            """, sv, as_dict=True)
            return [{
                "individual": r.individual, "hh": r.hh_name,
                "street":     r.street_name, "co": r.co_name,
                "date":       str(r.applied_on),
            } for r in rows]

    return []


@frappe.whitelist()
def get_trends_filter_meta():
    """Distinct values for Application Trends filter dropdowns."""
    sc = ""
    sv = {}
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        org = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "organisation"
        )
        if org:
            sc = "AND implementing_org = %(user_org)s"
            sv["user_org"] = org

    def _distinct(col):
        rows = frappe.db.sql(
            f"SELECT DISTINCT {col} AS v FROM `tabWRP Status Log` WHERE {col} IS NOT NULL AND {col} != '' {sc} ORDER BY {col}",
            sv, as_dict=True
        )
        return [r.v for r in rows]

    return {
        "orgs":    _distinct("implementing_org"),
        "ius":     _distinct("intervention_unit"),
        "acs":     _distinct("ac_name"),
        "streets": _distinct("street_name"),
        "cos":     frappe.db.sql(
            f"SELECT DISTINCT co_id AS v, co_name AS label FROM `tabWRP Status Log` WHERE co_id IS NOT NULL AND co_id != '' {sc} ORDER BY co_name",
            sv, as_dict=True
        ),
    }


# ── AC Review ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_ac_review_list(ac=None, status="Pending AC Review", street=None, intervention_unit=None):
    """
    Returns the AC Review list for the dashboard.
    Defaults to Pending items; pass status='' to see all.
    """
    if not frappe.db.table_exists("WRP AC Review"):
        return []

    conds = []
    vals = {"today": nowdate()}

    if ac:
        conds.append("ac_alloted = %(ac)s")
        vals["ac"] = ac
    if status:
        conds.append("status = %(status)s")
        vals["status"] = status
    if street:
        conds.append("street = %(street)s")
        vals["street"] = street
    if intervention_unit:
        conds.append("intervention_unit = %(iu)s")
        vals["iu"] = intervention_unit

    where = ("WHERE " + " AND ".join(conds)) if conds else ""

    return frappe.db.sql(f"""
        SELECT
            name,
            household,
            respondent,
            street,
            ac_alloted,
            co,
            visit_count,
            escalation_date,
            DATEDIFF(%(today)s, escalation_date) AS days_pending,
            status,
            ac_notes,
            resolved_date,
            intervention_unit,
            implementing_org
        FROM `tabWRP AC Review`
        {where}
        ORDER BY
            FIELD(status, 'Pending AC Review', 'Blocked – No Resolution', 'Cleared – Will Apply'),
            days_pending DESC
    """, vals, as_dict=True)


@frappe.whitelist()
def get_ac_review_filter_meta():
    """
    Returns distinct IU, street, and AC values for cascading filter dropdowns.
    Each street entry carries its IU and AC so the frontend can cascade without
    extra round-trips.
    """
    if not frappe.db.table_exists("WRP AC Review"):
        return {"ius": [], "streets": [], "acs": []}

    rows = frappe.db.sql("""
        SELECT DISTINCT intervention_unit, street, ac_alloted
        FROM `tabWRP AC Review`
        WHERE intervention_unit IS NOT NULL AND intervention_unit != ''
        ORDER BY intervention_unit, street
    """, as_dict=True)

    ius     = sorted({r.intervention_unit for r in rows if r.intervention_unit})
    streets = [{"name": r.street, "iu": r.intervention_unit, "ac": r.ac_alloted or ""} for r in rows if r.street]
    acs     = [{"ac": r.ac_alloted, "iu": r.intervention_unit} for r in rows if r.ac_alloted]

    return {"ius": ius, "streets": streets, "acs": acs}


@frappe.whitelist()
def resolve_ac_review(name, status, ac_notes=""):
    """AC resolves an escalated household — updates status and resolved_date."""
    allowed = {"Cleared – Will Apply", "Blocked – No Resolution"}
    if status not in allowed:
        frappe.throw(f"Invalid status. Must be one of: {', '.join(allowed)}")

    doc = frappe.get_doc("WRP AC Review", name)
    doc.status = status
    doc.ac_notes = ac_notes
    doc.resolved_date = nowdate()
    doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {"ok": True}

