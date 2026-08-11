"""
PM Chennai Dashboard API
------------------------
Composition layer for the unified Programme Manager view. Wraps existing
dashboard_api / generic_dashboard_api / ecp_api and adds cross-programme
rollups; also merges auto-derived and manual (Programme Blocker Note) blockers.

Design: never re-implement a query the existing modules already run.
Every endpoint is thin.
"""

import json
import frappe
from collections import defaultdict
from frappe.utils import (
    getdate,
    nowdate,
    get_first_day,
    get_last_day,
    add_months,
    formatdate,
)

from changemakers import dashboard_api, generic_dashboard_api, ecp_api


# ── Small helpers ─────────────────────────────────────────────────────────────

def _parse(filters):
    if isinstance(filters, str):
        try:
            return json.loads(filters) or {}
        except Exception:
            return {}
    return filters or {}


def _month_range(month):
    """Given YYYY-MM or a date string, return (first_day, last_day) as strings."""
    if not month:
        d = getdate(nowdate())
    else:
        try:
            d = getdate(month if len(str(month)) > 7 else f"{month}-01")
        except Exception:
            d = getdate(nowdate())
    return str(get_first_day(d)), str(get_last_day(d))


def _cmchis_filters(org, iu, month):
    date_from, date_to = _month_range(month)
    f = {"date_from": date_from, "date_to": date_to}
    if org:
        f["implementing_org"] = org
    if iu:
        f["intervention_unit"] = iu
    return f


def _safe_ecp_coverage(org, iu):
    """Wrap ecp_api.get_ecp_coverage; return empty coverage on any exception."""
    try:
        return ecp_api.get_ecp_coverage(
            implementing_org=org or None,
            intervention_unit=iu or None,
        )
    except Exception as exc:
        frappe.log_error(
            title="pm_dashboard_api: ECP coverage failed",
            message=frappe.get_traceback(),
        )
        return {"rows": [], "total_elderly": 0, "total_hh": 0,
                "_error": str(exc)[:200]}


def _safe_cmchis_overview(org, iu, month):
    """
    Wrap dashboard_api.get_dashboard_overview so a schema issue on one
    subsystem (e.g. stale local bench missing sd.designation) doesn't take
    the whole dashboard down. Returns None on failure; callers handle.
    """
    try:
        r = dashboard_api.get_dashboard_overview(_cmchis_filters(org, iu, month))
        if isinstance(r, dict) and r.get("error") == "no_access":
            return {"_no_access": True}
        return r
    except Exception as exc:
        frappe.log_error(
            title="pm_dashboard_api: CMCHIS overview failed",
            message=frappe.get_traceback(),
        )
        return {"_error": str(exc)[:200]}


# ── Scheme catalogue: CMCHIS (E1, legacy) + enabled generic entitlements ─────

def _all_entitlements(geography=None):
    """
    Returns list of {code, name, is_legacy}. CMCHIS (E1) is always first;
    the generic layer excludes E1 by design.
    """
    out = [{"code": "E1", "name": "CMCHIS", "is_legacy": True}]
    for c in generic_dashboard_api._get_enabled_entitlements(geography):
        out.append({"code": c.entitlement_code, "name": c.entitlement_name, "is_legacy": False})
    return out


# ── Endpoint 1: Top-strip overview + today's flags ───────────────────────────

@frappe.whitelist()
def get_overview(month=None, implementing_org=None, intervention_unit=None):
    date_from, date_to = _month_range(month)

    # CMCHIS side (legacy) — one call returns structure + alerts + pipeline
    cmchis = _safe_cmchis_overview(implementing_org, intervention_unit, month)
    if isinstance(cmchis, dict) and cmchis.get("_no_access"):
        return {"error": "no_access"}
    cmchis = cmchis or {}
    cmchis_err = cmchis.get("_error")

    struct = cmchis.get("structure", {}) or {}
    alerts = cmchis.get("alerts", {}) or {}
    pipe = cmchis.get("pipeline", {}) or {}

    # Per-entitlement quick saturation (E2+ via generic layer)
    entitlement_summary = []
    for e in _all_entitlements():
        if e["is_legacy"]:
            landed = int(pipe.get("goal") or pipe.get("active") or 0)
            total = int(pipe.get("total") or sum(int(v) for k, v in pipe.items() if k != "total") or 0)
            sat = round(landed / total * 100, 1) if total else 0
            entitlement_summary.append({
                "code": "E1", "name": "CMCHIS",
                "saturation_pct": sat, "landed": landed, "total": total,
            })
        else:
            try:
                po = generic_dashboard_api.get_programme_overview(
                    entitlement_code=e["code"],
                    implementing_org=implementing_org or None,
                    intervention_unit=intervention_unit or None,
                )
                entitlement_summary.append({
                    "code": e["code"], "name": e["name"],
                    "saturation_pct": po.get("saturation_pct", 0),
                    "landed": po.get("goal_count", 0),
                    "total": po.get("total", 0),
                })
            except Exception as exc:
                entitlement_summary.append({
                    "code": e["code"], "name": e["name"],
                    "saturation_pct": 0, "landed": 0, "total": 0,
                    "error": str(exc)[:120],
                })

    # ECP coverage (single call, guarded)
    ecp = _safe_ecp_coverage(implementing_org, intervention_unit)

    # Today's flags — from CMCHIS alerts + unresolved manual blockers
    flags = _todays_flags(alerts, month)

    return {
        "month": {"from": date_from, "to": date_to, "label": formatdate(date_from, "MMMM yyyy")},
        "structure": struct,
        "entitlements": entitlement_summary,
        "ecp_summary": {
            "total_elderly": ecp.get("total_elderly", 0),
            "total_hh": ecp.get("total_hh", 0),
            "ecos": len(ecp.get("rows", [])),
        },
        "alerts": alerts,
        "flags": flags,
        "warnings": ([f"CMCHIS subsystem: {cmchis_err}"] if cmchis_err else []),
    }


def _todays_flags(alerts, month):
    flags = []
    thresholds = {
        "cmchis_sla": ("CMCHIS applications past SLA", "red"),
        "aadhaar_external_sla": ("Aadhaar external-correction cases past SLA", "red"),
        "aadhaar_internal_sla": ("Aadhaar internal-correction cases past SLA", "amber"),
        "income_sla": ("Income cert cases past SLA", "amber"),
        "stagnant_14d": ("Households stagnant 14+ days", "amber"),
        "visited_no_change_7d": ("Visited in 7d with zero status change", "amber"),
    }
    for k, (label, colour) in thresholds.items():
        v = int(alerts.get(k) or 0)
        if v > 0:
            flags.append({"kind": k, "label": label, "count": v, "colour": colour})

    # Unresolved manual blockers this month
    date_from, _ = _month_range(month)
    unresolved = frappe.get_all(
        "Programme Blocker Note",
        filters={"month": date_from, "resolved": 0},
        fields=["name", "entitlement_code", "blocker_text"],
        limit=20,
    )
    for u in unresolved:
        flags.append({
            "kind": "manual_blocker",
            "label": f"{u.entitlement_code}: {u.blocker_text[:120]}",
            "count": 1,
            "colour": "red",
            "ref": u.name,
        })
    return flags


# ── Endpoint 2: Entitlements view (one card per scheme) ──────────────────────

@frappe.whitelist()
def get_entitlements_view(month=None, implementing_org=None, intervention_unit=None):
    date_from, date_to = _month_range(month)
    cards = []

    for e in _all_entitlements():
        if e["is_legacy"]:
            cards.append(_cmchis_card(implementing_org, intervention_unit, month))
        else:
            cards.append(_generic_card(e, implementing_org, intervention_unit, month))

    # Merge manual blocker text onto matching card
    notes = _blocker_notes_by_code(month)
    for c in cards:
        note = notes.get(c["code"])
        if note:
            c["blocker"] = {
                "source": "manual",
                "text": note["blocker_text"],
                "owner_action": note.get("owner_action") or "",
                "resolved": bool(note.get("resolved")),
                "note_name": note["name"],
            }

    return {
        "month": {"from": date_from, "to": date_to, "label": formatdate(date_from, "MMMM yyyy")},
        "cards": cards,
    }


def _cmchis_card(org, iu, month):
    ovr = _safe_cmchis_overview(org, iu, month) or {}
    err = ovr.get("_error")
    pipe = ovr.get("pipeline", {}) or {}
    alerts = ovr.get("alerts", {}) or {}

    landed = int(pipe.get("goal") or pipe.get("active") or 0)
    total = int(pipe.get("total") or 0)
    if not total:
        total = sum(int(v or 0) for k, v in pipe.items() if k != "total")
    sat = round(landed / total * 100, 1) if total else 0

    # Auto-blocker heuristic: any SLA over threshold, or subsystem error
    auto = _cmchis_auto_blocker(alerts)
    if err and not auto:
        auto = {"source": "auto", "text": f"CMCHIS query error: {err}"}

    return {
        "code": "E1", "name": "CMCHIS", "is_legacy": True,
        "saturation_pct": sat, "landed": landed, "total": total,
        "buckets": {k: int(v or 0) for k, v in pipe.items() if k != "total"},
        "blocker": auto,
    }


def _generic_card(e, org, iu, month):
    try:
        po = generic_dashboard_api.get_programme_overview(
            entitlement_code=e["code"],
            implementing_org=org or None,
            intervention_unit=iu or None,
        )
    except Exception as exc:
        return {
            "code": e["code"], "name": e["name"], "is_legacy": False,
            "saturation_pct": 0, "landed": 0, "total": 0, "buckets": {},
            "blocker": {"source": "auto", "text": f"Data error: {str(exc)[:120]}"},
        }

    auto = _generic_auto_blocker(po)
    return {
        "code": e["code"], "name": e["name"], "is_legacy": False,
        "saturation_pct": po.get("saturation_pct", 0),
        "landed": po.get("goal_count", 0),
        "total": po.get("total", 0),
        "buckets": po.get("bucket_counts", {}),
        "sla_overdue": po.get("sla_overdue_count", 0),
        "pending_ac_reviews": po.get("pending_ac_reviews", 0),
        "blocker": auto,
    }


def _cmchis_auto_blocker(alerts):
    hits = []
    if int(alerts.get("cmchis_sla") or 0) > 20:
        hits.append(f"{alerts['cmchis_sla']} CMCHIS applications past SLA")
    if int(alerts.get("aadhaar_external_sla") or 0) > 30:
        hits.append(f"{alerts['aadhaar_external_sla']} Aadhaar external-correction cases past SLA")
    if int(alerts.get("stagnant_14d") or 0) > 100:
        hits.append(f"{alerts['stagnant_14d']} households stagnant 14+ days")
    if not hits:
        return None
    return {"source": "auto", "text": " · ".join(hits)}


def _generic_auto_blocker(po):
    sla = int(po.get("sla_overdue_count") or 0)
    pending = int(po.get("pending_ac_reviews") or 0)
    if sla == 0 and pending == 0:
        return None
    parts = []
    if sla > 0:
        parts.append(f"{sla} cases SLA-overdue")
    if pending > 0:
        parts.append(f"{pending} pending AC reviews")
    return {"source": "auto", "text": " · ".join(parts)}


def _blocker_notes_by_code(month):
    date_from, _ = _month_range(month)
    rows = frappe.get_all(
        "Programme Blocker Note",
        filters={"month": date_from},
        fields=["name", "entitlement_code", "blocker_text", "owner_action", "resolved"],
    )
    return {r.entitlement_code: r for r in rows}


# ── Endpoint 3: Elderly care (ECP) view ──────────────────────────────────────

@frappe.whitelist()
def get_elderly_view(month=None, implementing_org=None, intervention_unit=None):
    date_from, date_to = _month_range(month)

    coverage = _safe_ecp_coverage(implementing_org, intervention_unit)

    try:
        evrat = _evrat_stats(implementing_org, intervention_unit, date_from, date_to)
    except Exception as exc:
        frappe.log_error(title="pm_dashboard_api: EVRAT stats failed",
                         message=frappe.get_traceback())
        evrat = {"available": False, "total": 0, "this_month": 0,
                 "risk_distribution": {}, "_error": str(exc)[:200]}

    try:
        home_visits = _home_visits_stats(implementing_org, intervention_unit,
                                         date_from, date_to)
    except Exception as exc:
        frappe.log_error(title="pm_dashboard_api: Home visits stats failed",
                         message=frappe.get_traceback())
        home_visits = {"available": False, "this_month": 0, "by_eco": [],
                       "_error": str(exc)[:200]}

    warnings = []
    if coverage.get("_error"): warnings.append(f"ECP coverage: {coverage['_error']}")
    if evrat.get("_error"):    warnings.append(f"EVRAT: {evrat['_error']}")
    if home_visits.get("_error"): warnings.append(f"Home Visit: {home_visits['_error']}")

    return {
        "month": {"from": date_from, "to": date_to, "label": formatdate(date_from, "MMMM yyyy")},
        "coverage": coverage,
        "evrat": evrat,
        "home_visits": home_visits,
        "warnings": warnings,
    }


def _scoped_streets(implementing_org, intervention_unit):
    return generic_dashboard_api._get_scope_streets(implementing_org, intervention_unit, None)


def _evrat_stats(org, iu, date_from, date_to):
    """
    EVRAT Assessment - ECP is DB-resident (created via FC UI, not in git).
    Guard with table-exists + field-detect so a fresh bench or a schema
    variant doesn't 500 the whole dashboard.
    """
    if not _table_exists("EVRAT Assessment - ECP"):
        return {"available": False, "total": 0, "this_month": 0, "risk_distribution": {}}

    link_field = _detect_field(
        "EVRAT Assessment - ECP",
        ["individual_profile", "individual", "beneficiary", "individual_id"],
    )

    streets = _scoped_streets(org, iu)
    params = {"date_from": date_from, "date_to": date_to}
    scope_cond = ""
    join_clause = ""
    if link_field:
        join_clause = (
            f"LEFT JOIN `tabIndividual Profile-WRP` ipw "
            f"ON CAST(ipw.name AS CHAR) = ev.{link_field}"
        )
        if streets is not None:
            if not streets:
                return {"available": True, "total": 0, "this_month": 0,
                        "risk_distribution": {}, "scope_applied": True}
            scope_cond = " AND ipw.street IN %(streets)s"
            params["streets"] = tuple(streets)

    total = int(frappe.db.sql(
        f"SELECT COUNT(*) AS n FROM `tabEVRAT Assessment - ECP` ev "
        f"{join_clause} WHERE 1=1 {scope_cond}",
        params, as_dict=True,
    )[0].n or 0)

    this_month = int(frappe.db.sql(
        f"SELECT COUNT(*) AS n FROM `tabEVRAT Assessment - ECP` ev "
        f"{join_clause} "
        f"WHERE ev.creation >= %(date_from)s AND ev.creation <= %(date_to)s {scope_cond}",
        params, as_dict=True,
    )[0].n or 0)

    risk_field = _detect_field("EVRAT Assessment - ECP",
                               ["overall_risk", "risk_level", "risk"])
    risk_distribution = {}
    if risk_field:
        rows = frappe.db.sql(
            f"SELECT ev.{risk_field} AS bucket, COUNT(*) AS n "
            f"FROM `tabEVRAT Assessment - ECP` ev {join_clause} "
            f"WHERE 1=1 {scope_cond} GROUP BY ev.{risk_field}",
            params, as_dict=True,
        )
        risk_distribution = {(r.bucket or "Unknown"): int(r.n or 0) for r in rows}

    return {
        "available": True,
        "total": total,
        "this_month": this_month,
        "risk_distribution": risk_distribution,
        "scope_applied": bool(link_field),
    }


def _home_visits_stats(org, iu, date_from, date_to):
    if not _table_exists("Home Visit - ECP"):
        return {"available": False, "this_month": 0, "by_eco": []}

    link_field = _detect_field(
        "Home Visit - ECP",
        ["individual_profile", "individual", "beneficiary", "individual_id"],
    )

    streets = _scoped_streets(org, iu)
    params = {"date_from": date_from, "date_to": date_to}
    scope_cond = ""
    join_clause = ""
    if link_field:
        join_clause = (
            f"LEFT JOIN `tabIndividual Profile-WRP` ipw "
            f"ON CAST(ipw.name AS CHAR) = hv.{link_field} "
            f"LEFT JOIN `tabStreet List  - WRP` sl ON sl.name = ipw.street"
        )
        if streets is not None:
            if not streets:
                return {"available": True, "this_month": 0, "by_eco": [], "scope_applied": True}
            scope_cond = " AND ipw.street IN %(streets)s"
            params["streets"] = tuple(streets)

    this_month = int(frappe.db.sql(
        f"SELECT COUNT(*) AS n FROM `tabHome Visit - ECP` hv {join_clause} "
        f"WHERE hv.creation >= %(date_from)s AND hv.creation <= %(date_to)s {scope_cond}",
        params, as_dict=True,
    )[0].n or 0)

    by_eco = []
    if link_field:
        by_eco_rows = frappe.db.sql(
            f"SELECT COALESCE(sl.eco_allotted, 'Unassigned') AS eco, COUNT(*) AS n "
            f"FROM `tabHome Visit - ECP` hv {join_clause} "
            f"WHERE hv.creation >= %(date_from)s AND hv.creation <= %(date_to)s {scope_cond} "
            f"GROUP BY sl.eco_allotted ORDER BY n DESC",
            params, as_dict=True,
        )
        by_eco = [{"eco": r.eco, "count": int(r.n or 0)} for r in by_eco_rows]

    return {
        "available": True,
        "this_month": this_month,
        "by_eco": by_eco,
        "scope_applied": bool(link_field),
    }


# ── Endpoint 4: CO / AC / Org performance ────────────────────────────────────

@frappe.whitelist()
def get_performance_view(month=None, implementing_org=None,
                         intervention_unit=None, pivot="co"):
    """
    pivot: 'co' | 'ac' | 'org'
    Returns per-entity rollup across CMCHIS (E1) + all generic entitlements + ECP visits.
    """
    date_from, date_to = _month_range(month)
    streets = _scoped_streets(implementing_org, intervention_unit)
    if streets == []:
        return {"pivot": pivot, "rows": [],
                "month": {"from": date_from, "to": date_to,
                          "label": formatdate(date_from, "MMMM yyyy")}}
    scope_streets = tuple(streets) if streets else None

    # Entitlement-side rollup (CMCHIS + generic) — count Generic Beneficiary
    # rows that reached final_status "active" this month, plus goal_status_value
    # for any config. Legacy CMCHIS uses a separate table, so we tally both.
    entitlement_rows = _entitlement_landed_this_month(
        scope_streets, date_from, date_to, pivot
    )

    # ECP visits this month (guarded — DB-resident table may not have expected columns)
    try:
        ecp_rows = _ecp_visits_this_month(scope_streets, date_from, date_to, pivot)
    except Exception:
        frappe.log_error(title="pm_dashboard_api: ECP visits pivot failed",
                         message=frappe.get_traceback())
        ecp_rows = []

    # Merge into unified per-entity rows
    merged = defaultdict(lambda: {"entity": "", "cmchis_landed": 0,
                                  "e2_landed": 0, "ecp_visits": 0, "other": {}})
    for r in entitlement_rows:
        key = r["entity"] or "Unassigned"
        m = merged[key]
        m["entity"] = key
        if r["code"] == "E1":
            m["cmchis_landed"] += int(r["n"])
        elif r["code"] == "E2":
            m["e2_landed"] += int(r["n"])
        else:
            m["other"].setdefault(r["code"], 0)
            m["other"][r["code"]] += int(r["n"])
    for r in ecp_rows:
        key = r["entity"] or "Unassigned"
        merged[key]["entity"] = key
        merged[key]["ecp_visits"] += int(r["n"])

    rows = sorted(
        merged.values(),
        key=lambda x: (x["cmchis_landed"] + x["e2_landed"] + x["ecp_visits"]),
        reverse=True,
    )

    return {
        "pivot": pivot,
        "rows": rows,
        "month": {"from": date_from, "to": date_to,
                  "label": formatdate(date_from, "MMMM yyyy")},
    }


def _entity_column(pivot):
    if pivot == "co":
        return "gb.assigned_co", "gb.assigned_co"
    if pivot == "ac":
        return "sl.ac_alloted", "sl.ac_alloted"
    return "sl.implementing_org", "sl.implementing_org"


def _entitlement_landed_this_month(scope_streets, date_from, date_to, pivot):
    """
    Uses Generic Beneficiary for E2+ (final_status transitions this month).
    For CMCHIS (E1), reuses dashboard_api's CO performance query for the
    same period and re-pivots for AC/Org.
    """
    out = []
    entity_expr, _ = _entity_column(pivot)

    # Generic entitlements
    scope_cond = ""
    params = {"date_from": date_from, "date_to": date_to}
    if scope_streets is not None:
        scope_cond = " AND gb.street IN %(streets)s"
        params["streets"] = scope_streets

    rows = frappe.db.sql(
        f"""
        SELECT gb.entitlement AS code,
               {entity_expr} AS entity,
               COUNT(*) AS n
        FROM `tabGeneric Beneficiary` gb
        LEFT JOIN `tabStreet List  - WRP` sl ON sl.name = gb.street
        WHERE gb.entitlement != 'E1'
          AND gb.final_status = 'active'
          AND gb.modified >= %(date_from)s
          AND gb.modified <= %(date_to)s
          {scope_cond}
        GROUP BY gb.entitlement, entity
        """,
        params,
        as_dict=True,
    )
    for r in rows:
        out.append({"code": r.code, "entity": r.entity or "Unassigned", "n": r.n or 0})

    # CMCHIS side — count Household transitions to a Received/Active status this
    # month via WRP Status Log. Keeps this endpoint self-contained.
    cmchis_rows = frappe.db.sql(
        f"""
        SELECT {'sl.ac_alloted' if pivot == 'ac' else
                'sl.implementing_org' if pivot == 'org' else
                'wsl.co_id'} AS entity,
               COUNT(*) AS n
        FROM `tabWRP Status Log` wsl
        LEFT JOIN `tabHousehold Profile-WRP` hh ON hh.name = wsl.hh_name
        LEFT JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        WHERE wsl.field_changed = 'cmchis_status'
          AND wsl.new_value LIKE 'Active%%'
          AND wsl.changed_at >= %(date_from)s
          AND wsl.changed_at <= %(date_to)s
          {("AND sl.name IN %(streets)s" if scope_streets is not None else "")}
        GROUP BY entity
        """,
        {**params, **({"streets": scope_streets} if scope_streets is not None else {})},
        as_dict=True,
    )
    for r in cmchis_rows:
        out.append({"code": "E1", "entity": r.entity or "Unassigned", "n": r.n or 0})

    return out


def _ecp_visits_this_month(scope_streets, date_from, date_to, pivot):
    if not _table_exists("Home Visit - ECP"):
        return []
    link_field = _detect_field(
        "Home Visit - ECP",
        ["individual_profile", "individual", "beneficiary", "individual_id"],
    )
    if not link_field:
        return []
    entity_col = ("sl.eco_allotted" if pivot == "co"
                  else "sl.ac_alloted" if pivot == "ac"
                  else "sl.implementing_org")
    scope_cond = ""
    params = {"date_from": date_from, "date_to": date_to}
    if scope_streets is not None:
        scope_cond = " AND ipw.street IN %(streets)s"
        params["streets"] = scope_streets
    rows = frappe.db.sql(
        f"""
        SELECT {entity_col} AS entity, COUNT(*) AS n
        FROM `tabHome Visit - ECP` hv
        LEFT JOIN `tabIndividual Profile-WRP` ipw
          ON CAST(ipw.name AS CHAR) = hv.{link_field}
        LEFT JOIN `tabStreet List  - WRP` sl ON sl.name = ipw.street
        WHERE hv.creation >= %(date_from)s AND hv.creation <= %(date_to)s
        {scope_cond}
        GROUP BY entity
        """,
        params,
        as_dict=True,
    )
    return [{"entity": r.entity or "Unassigned", "n": r.n or 0} for r in rows]


# ── Endpoint 5: Blockers view ────────────────────────────────────────────────

@frappe.whitelist()
def get_blockers_view(month=None, implementing_org=None, intervention_unit=None):
    date_from, date_to = _month_range(month)
    # Manual notes
    manual = frappe.get_all(
        "Programme Blocker Note",
        filters={"month": date_from},
        fields=["name", "entitlement_code", "blocker_text", "owner_action",
                "resolved", "resolved_at", "modified"],
        order_by="resolved asc, modified desc",
    )

    # Auto derived — collect the same alerts as get_overview and per-entitlement
    # sla counts. Return in a normalised shape so the UI can render both alike.
    auto = []
    cmchis = _safe_cmchis_overview(implementing_org, intervention_unit, month) or {}
    if not cmchis.get("_no_access"):
        auto_cm = _cmchis_auto_blocker(cmchis.get("alerts", {}) or {})
        if auto_cm:
            auto.append({"entitlement_code": "E1", "text": auto_cm["text"]})
        elif cmchis.get("_error"):
            auto.append({"entitlement_code": "E1",
                         "text": f"CMCHIS query error: {cmchis['_error']}"})

    for e in _all_entitlements():
        if e["is_legacy"]:
            continue
        try:
            po = generic_dashboard_api.get_programme_overview(
                entitlement_code=e["code"],
                implementing_org=implementing_org or None,
                intervention_unit=intervention_unit or None,
            )
            b = _generic_auto_blocker(po)
            if b:
                auto.append({"entitlement_code": e["code"], "text": b["text"]})
        except Exception:
            pass

    return {
        "month": {"from": date_from, "to": date_to,
                  "label": formatdate(date_from, "MMMM yyyy")},
        "manual": manual,
        "auto": auto,
    }


@frappe.whitelist()
def save_blocker_note(entitlement_code, month, blocker_text,
                      owner_action="", resolved=0):
    """Upsert a Programme Blocker Note keyed on (entitlement, month)."""
    date_from = str(get_first_day(getdate(month if len(str(month)) > 7 else f"{month}-01")))
    name = f"BLK-{entitlement_code}-{date_from}"
    if frappe.db.exists("Programme Blocker Note", name):
        doc = frappe.get_doc("Programme Blocker Note", name)
        doc.blocker_text = blocker_text
        doc.owner_action = owner_action or ""
        doc.resolved = int(resolved or 0)
        doc.save(ignore_permissions=False)
    else:
        doc = frappe.get_doc({
            "doctype": "Programme Blocker Note",
            "entitlement_code": entitlement_code,
            "month": date_from,
            "blocker_text": blocker_text,
            "owner_action": owner_action or "",
            "resolved": int(resolved or 0),
        })
        doc.insert(ignore_permissions=False)
    frappe.db.commit()
    return {"ok": True, "name": doc.name}


# ── Endpoint 6: Unified drill-down ───────────────────────────────────────────

@frappe.whitelist()
def get_drilldown_unified(level="org", parent=None, month=None,
                          implementing_org=None, intervention_unit=None):
    """
    level: 'org' | 'iu' | 'street' | 'hh' | 'individual'
    parent: the identifier at the previous level (e.g. street name for 'hh').
    Returns rows with per-entitlement chips.
    """
    date_from, date_to = _month_range(month)

    org = implementing_org or None
    iu = intervention_unit or None

    if level == "org":
        return _dd_org(org, iu)
    if level == "iu":
        return _dd_iu(parent or org)
    if level == "street":
        return _dd_street(iu=parent or iu, org=org)
    if level == "hh":
        return _dd_household(parent)
    if level == "individual":
        return _dd_individual(parent)
    return {"rows": []}


def _dd_org(org=None, iu=None):
    filters = {"settlement_selection_status": ["not in", ["No", "Yes, but not for Phase 1"]]}
    if iu:
        filters["intervention_units"] = iu
    if org:
        filters["implementing_org"] = org
    rows = frappe.db.sql(
        """
        SELECT sl.implementing_org AS entity,
               COUNT(DISTINCT sl.name) AS streets,
               COUNT(DISTINCT sl.intervention_units) AS ius
        FROM `tabStreet List  - WRP` sl
        WHERE sl.settlement_selection_status NOT IN ('No', 'Yes, but not for Phase 1')
          {org_filter}
          {iu_filter}
        GROUP BY sl.implementing_org
        ORDER BY sl.implementing_org
        """.format(
            org_filter=("AND sl.implementing_org = %(org)s" if org else ""),
            iu_filter=("AND sl.intervention_units = %(iu)s" if iu else ""),
        ),
        {"org": org, "iu": iu},
        as_dict=True,
    )
    return {"level": "org", "rows": rows}


def _dd_iu(org):
    rows = frappe.db.sql(
        """
        SELECT sl.intervention_units AS entity,
               COUNT(DISTINCT sl.name) AS streets
        FROM `tabStreet List  - WRP` sl
        WHERE sl.settlement_selection_status NOT IN ('No', 'Yes, but not for Phase 1')
          {org_filter}
        GROUP BY sl.intervention_units
        ORDER BY sl.intervention_units
        """.format(org_filter=("AND sl.implementing_org = %(org)s" if org else "")),
        {"org": org},
        as_dict=True,
    )
    return {"level": "iu", "rows": rows}


def _dd_street(iu=None, org=None):
    """`iu` is the IU name; `org` optionally narrows further."""
    rows = frappe.db.sql(
        """
        SELECT sl.name AS entity,
               sl.added_by_co AS co,
               sl.ac_alloted AS ac,
               sl.implementing_org AS org,
               COUNT(hh.name) AS hh_count
        FROM `tabStreet List  - WRP` sl
        LEFT JOIN `tabHousehold Profile-WRP` hh ON hh.street_name = sl.name
        WHERE sl.settlement_selection_status NOT IN ('No', 'Yes, but not for Phase 1')
          {iu_filter}
          {org_filter}
        GROUP BY sl.name
        ORDER BY sl.name
        """.format(
            iu_filter=("AND sl.intervention_units = %(iu)s" if iu else ""),
            org_filter=("AND sl.implementing_org = %(org)s" if org else ""),
        ),
        {"iu": iu, "org": org},
        as_dict=True,
    )
    return {"level": "street", "rows": rows}


def _dd_household(street):
    rows = frappe.db.sql(
        """
        SELECT hh.name AS entity,
               hh.respondent,
               hh.cmchis_status,
               (SELECT COUNT(*) FROM `tabIndividual Profile-WRP` ipw
                 WHERE ipw.hhid = hh.name) AS members
        FROM `tabHousehold Profile-WRP` hh
        WHERE hh.street_name = %(street)s
        ORDER BY hh.name
        """,
        {"street": street},
        as_dict=True,
    )
    return {"level": "hh", "rows": rows}


def _dd_individual(hh):
    """Return individuals in a household with per-entitlement chips."""
    inds = frappe.db.sql(
        """
        SELECT name, first_name, gender, age, status
        FROM `tabIndividual Profile-WRP`
        WHERE hhid = %(hh)s
        ORDER BY age DESC
        """,
        {"hh": hh},
        as_dict=True,
    )
    if not inds:
        return {"level": "individual", "rows": []}

    # Entitlement chips per individual — Generic Beneficiary rows
    ind_names_str = [str(i.name) for i in inds]
    entitlement_map = defaultdict(dict)
    if ind_names_str:
        rows = frappe.get_all(
            "Generic Beneficiary",
            filters={"source_docname": ["in", ind_names_str]},
            fields=["source_docname", "entitlement", "final_status",
                    "doc1_status", "doc2_status", "doc3_status", "visit_count"],
        )
        for r in rows:
            entitlement_map[str(r.source_docname)][r.entitlement] = {
                "final_status": r.final_status or "",
                "doc_states": [r.doc1_status, r.doc2_status, r.doc3_status],
                "visits": int(r.visit_count or 0),
            }

    # ECP EVRAT presence (guarded — probe schema before querying)
    evrat_present = set()
    if ind_names_str:
        try:
            link_field = _detect_field(
                "EVRAT Assessment - ECP",
                ["individual_profile", "individual", "beneficiary", "individual_id"],
            )
            if link_field:
                rows = frappe.db.sql(
                    f"SELECT DISTINCT {link_field} AS ind "
                    f"FROM `tabEVRAT Assessment - ECP` "
                    f"WHERE {link_field} IN %(inds)s",
                    {"inds": tuple(ind_names_str)},
                    as_dict=True,
                )
                evrat_present = {r.ind for r in rows}
        except Exception:
            frappe.log_error(title="pm_dashboard_api: EVRAT chip probe failed",
                             message=frappe.get_traceback())

    for i in inds:
        key = str(i.name)
        i["entitlements"] = entitlement_map.get(key, {})
        i["evrat"] = key in evrat_present

    return {"level": "individual", "rows": inds}


# ── Tiny utilities ───────────────────────────────────────────────────────────

def _table_exists(doctype):
    try:
        return bool(frappe.db.table_exists(doctype))
    except Exception:
        return False


def _detect_field(doctype, candidates):
    """Return the first candidate that exists as a column on the doctype table."""
    if not _table_exists(doctype):
        return None
    table = f"tab{doctype}"
    try:
        cols = frappe.db.sql(
            "SELECT COLUMN_NAME FROM information_schema.COLUMNS "
            "WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s",
            (table,),
            as_dict=True,
        )
        col_names = {c.COLUMN_NAME for c in cols}
        for c in candidates:
            if c in col_names:
                return c
    except Exception:
        pass
    return None


# ── Filter meta for the top bar ──────────────────────────────────────────────

@frappe.whitelist()
def get_filter_meta():
    """Cascading filter options: implementing_org → intervention_units."""
    rows = frappe.get_all(
        "Street List  - WRP",
        filters={"settlement_selection_status": ["not in", ["No", "Yes, but not for Phase 1"]]},
        fields=["implementing_org", "intervention_units"],
    )
    orgs = sorted({r.implementing_org for r in rows if r.implementing_org})
    seen = {}
    for r in rows:
        if not r.intervention_units:
            continue
        seen[(r.implementing_org, r.intervention_units)] = {
            "org": r.implementing_org, "iu": r.intervention_units,
        }
    ius = sorted(seen.values(), key=lambda x: (x["org"] or "", x["iu"] or ""))
    return {"orgs": orgs, "ius": ius}
