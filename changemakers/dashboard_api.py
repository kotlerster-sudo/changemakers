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

    # Staff role counts — scope-aware: join Has Role to Staff details via mail_id
    org_filter = sv.get("implementing_org") or sv.get("user_org")
    if org_filter:
        def _role_count_for_org(role, org):
            r = frappe.db.sql("""
                SELECT COUNT(DISTINCT hr.parent) AS cnt
                FROM `tabHas Role` hr
                JOIN `tabStaff details - WRP` sd ON sd.mail_id = hr.parent
                WHERE hr.role = %s AND hr.parenttype = 'User'
                  AND sd.organisation = %s
            """, (role, org), as_dict=True)
            return int(r[0].cnt if r else 0)
        pms = _role_count_for_org("WRP-PM", org_filter)
        acs = _role_count_for_org("WRP-AC", org_filter)
    else:
        pms = frappe.db.count("Has Role", {"role": "WRP-PM", "parenttype": "User"})
        acs = frappe.db.count("Has Role", {"role": "WRP-AC", "parenttype": "User"})

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
