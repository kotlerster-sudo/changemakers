"""
Generic Entitlement Dashboard API
----------------------------------
Powers three HTML-block workspaces: Programme, AC, MIS.
All endpoints are geography/role-filtered via Entitlement Role Config.
"""

import frappe
from frappe.utils import getdate, nowdate, now_datetime
from collections import defaultdict


# ── Access resolution ─────────────────────────────────────────────────────────

@frappe.whitelist()
def resolve_user_access(entitlement_code=None):
    """
    Returns the current user's access level and geography restriction
    based on Entitlement Role Config mappings.

    Response:
      {
        "access_level": "Programme Manager" | "Area Coordinator" | "MIS" | "CO" | "HR" | "Admin",
        "geography": "Chennai" | "" (empty = all geographies),
        "is_system_manager": true/false,
        "entitlement_code": "E2"
      }
    """
    if frappe.session.user == "Administrator" or "System Manager" in frappe.get_roles():
        return {
            "access_level": "Admin",
            "geography": "",
            "is_system_manager": True,
            "entitlement_code": entitlement_code,
        }

    user_roles = set(frappe.get_roles())
    mappings = frappe.get_all(
        "Entitlement Role Config",
        fields=["role", "access_level", "geography"],
        order_by="access_level asc",
    )

    best_access = None
    best_geography = None
    ACCESS_RANK = {
        "Admin": 6, "Programme Manager": 5, "HR": 4,
        "MIS": 3, "Area Coordinator": 2, "CO": 1,
    }

    for m in mappings:
        if m.role not in user_roles:
            continue
        rank = ACCESS_RANK.get(m.access_level, 0)
        best_rank = ACCESS_RANK.get(best_access, -1)
        if rank > best_rank:
            best_access = m.access_level
            best_geography = m.geography or ""

    if not best_access:
        return {
            "access_level": "CO",
            "geography": "",
            "is_system_manager": False,
            "entitlement_code": entitlement_code,
        }

    return {
        "access_level": best_access,
        "geography": best_geography,
        "is_system_manager": False,
        "entitlement_code": entitlement_code,
    }


def _get_enabled_entitlements(geography=None):
    """Returns list of entitlement codes (excluding legacy E1)."""
    filters = {"enabled": 1, "entitlement_code": ["!=", "E1"]}
    if geography:
        filters["geography"] = geography
    return frappe.get_all(
        "Entitlement Config",
        filters=filters,
        fields=["entitlement_code", "entitlement_name", "geography"],
    )


def _get_streets_for_geography(geography=None, ac_id=None):
    """Returns street list filtered by geography and/or AC."""
    filters = {}
    if ac_id:
        filters["added_by_co"] = ac_id
    streets = frappe.get_all("Street List  - WRP", filters=filters, pluck="name")
    if not streets:
        return []
    if geography:
        pass
    return streets


def _get_scope_streets(implementing_org=None, intervention_unit=None, street=None):
    """
    Returns street names for the given scope filter, or None (= no filter).
    Most specific wins: street > IU > org.
    Returns [] if scope is set but matches nothing (→ zero results).
    """
    if not implementing_org and not intervention_unit and not street:
        return None
    if street:
        return [street]
    filters = {}
    if intervention_unit:
        filters["intervention_units"] = intervention_unit
    else:
        filters["implementing_org"] = implementing_org
    return frappe.get_all("Street List  - WRP", filters=filters, pluck="name")


# ── Programme overview ────────────────────────────────────────────────────────

@frappe.whitelist()
def get_programme_overview(entitlement_code, geography=None,
                           implementing_org=None, intervention_unit=None, street=None):
    """
    Programme Manager / MIS level overview for one scheme.

    Returns pipeline bucket counts, goal %, coverage %, SLA summary,
    and update rate band distribution.
    """
    from changemakers.entitlement_api import (
        _load_config, _bucket, _sla_overdue_days, _filter_active_beneficiaries,
    )

    config = _load_config(entitlement_code)
    filters = {"entitlement": entitlement_code}

    scope_streets = _get_scope_streets(implementing_org, intervention_unit, street)
    if scope_streets is not None:
        if not scope_streets:
            return {
                "entitlement_code": entitlement_code, "entitlement_name": config["name"],
                "total": 0, "visited": 0, "goal_count": 0, "negative_count": 0,
                "saturation_pct": 0, "coverage_pct": 0, "sla_overdue_count": 0,
                "pending_ac_reviews": 0, "bucket_counts": {},
                "update_rate_bands": {"critical": 0, "poor": 0, "acceptable": 0, "good": 0},
                "goal_label": config["final_status_label"],
                "final_status_label": config["final_status_label"],
            }
        filters["street"] = ["in", scope_streets]

    beneficiaries = frappe.get_all(
        "Generic Beneficiary",
        filters=filters,
        fields=["name", "container", "street", "assigned_co",
                "doc1_status", "doc2_status", "doc3_status", "doc4_status",
                "final_status", "visit_count", "last_visited_at",
                "source_docname"],
    )
    beneficiaries = _filter_active_beneficiaries(beneficiaries)

    container_finals = {}
    if config["final_status_at"] == "Household":
        cids = list({b.container for b in beneficiaries if b.container})
        if cids:
            rows = frappe.get_all(
                "Generic Container",
                filters={"name": ["in", cids]},
                fields=["name", "final_status"],
            )
            container_finals = {r.name: r.final_status or "" for r in rows}

    bucket_counts = defaultdict(int)
    sla_overdue_count = 0
    visited_count = 0
    total = len(beneficiaries)

    for b in beneficiaries:
        cf = container_finals.get(b.container, "") if b.container else ""
        bkt = _bucket(config, frappe._dict(b), cf)
        bucket_counts[bkt] += 1
        if int(b.visit_count or 0) > 0:
            visited_count += 1
        if _sla_overdue_days(config, b) > 0:
            sla_overdue_count += 1

    goal_count = bucket_counts.get("goal", 0)
    negative_count = bucket_counts.get("negative", 0)
    saturation_pct = round(goal_count / total * 100, 1) if total else 0
    coverage_pct = round(visited_count / total * 100, 1) if total else 0

    # Update rate bands from Entitlement Status Log
    band_counts = _get_update_rate_bands_summary(entitlement_code, scope_streets=scope_streets)

    # Generic AC Review pending — respect the org/IU/street scope filter.
    # Scope via the linked beneficiary's street (same approach as the Sankey
    # endpoint) so this card narrows in step with every other metric above.
    if scope_streets is not None:
        pending_ac_reviews = frappe.db.sql("""
            SELECT COUNT(*)
            FROM `tabGeneric AC Review`
            WHERE entitlement = %(e)s
              AND status = 'Pending AC Review'
              AND beneficiary IN (
                SELECT name FROM `tabGeneric Beneficiary`
                WHERE entitlement = %(e)s AND street IN %(scope_streets)s
              )
        """, {"e": entitlement_code, "scope_streets": tuple(scope_streets)})[0][0]
    else:
        pending_ac_reviews = frappe.db.count(
            "Generic AC Review",
            {"entitlement": entitlement_code, "status": "Pending AC Review"},
        )

    return {
        "entitlement_code":   entitlement_code,
        "entitlement_name":   config["name"],
        "total":              total,
        "visited":            visited_count,
        "goal_count":         goal_count,
        "negative_count":     negative_count,
        "saturation_pct":     saturation_pct,
        "coverage_pct":       coverage_pct,
        "sla_overdue_count":  sla_overdue_count,
        "pending_ac_reviews": pending_ac_reviews,
        "bucket_counts":      dict(bucket_counts),
        "update_rate_bands":  band_counts,
        "goal_label":         config["final_status_label"],
        "final_status_label": config["final_status_label"],
    }


def _get_update_rate_bands_summary(entitlement_code, scope_streets=None, date_from=None, date_to=None):
    """
    Returns count of COs in each update rate band.
    Update rate = productive visits (at least one status change) / total visits.
    Bands: <25 critical, 25-50 poor, 50-75 acceptable, >75 good.
    """
    from changemakers.entitlement_api import ACTIVE_IND_JOIN, ACTIVE_IND_WHERE, IND_ACTIVE_STATUS

    scope_cond = ""
    if scope_streets is not None:
        if not scope_streets:
            return {"critical": 0, "poor": 0, "acceptable": 0, "good": 0}
        scope_cond = " AND gb.street IN %(scope_streets)s"

    co_rows = frappe.db.sql(f"""
        SELECT gb.assigned_co AS assigned_co, SUM(gb.visit_count) as total_visits
        FROM `tabGeneric Beneficiary` gb
        {ACTIVE_IND_JOIN}
        WHERE gb.entitlement = %(e)s
          AND gb.assigned_co IS NOT NULL AND gb.assigned_co != ''
          AND {ACTIVE_IND_WHERE}
          {scope_cond}
        GROUP BY gb.assigned_co
    """, {
        "e": entitlement_code,
        "_ind_active_status": IND_ACTIVE_STATUS,
        "scope_streets": tuple(scope_streets) if scope_streets else (),
    }, as_dict=True)

    if not co_rows:
        return {"critical": 0, "poor": 0, "acceptable": 0, "good": 0}

    date_cond = "AND changed_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"
    date_vals = {}
    if date_from and date_to:
        date_cond = "AND changed_at BETWEEN %(date_from)s AND %(date_to)s"
        date_vals = {"date_from": date_from + " 00:00:00", "date_to": date_to + " 23:59:59"}
    elif date_from:
        date_cond = "AND changed_at >= %(date_from)s"
        date_vals = {"date_from": date_from + " 00:00:00"}

    co_changes = frappe.db.sql(f"""
        SELECT co, COUNT(*) as changes
        FROM `tabEntitlement Status Log`
        WHERE entitlement = %(e)s
          {date_cond}
          AND co IS NOT NULL AND co != ''
        GROUP BY co
    """, {"e": entitlement_code, **date_vals}, as_dict=True)

    changes_by_co = {r.co: r.changes for r in co_changes}

    bands = {"critical": 0, "poor": 0, "acceptable": 0, "good": 0}
    for row in co_rows:
        total = int(row.total_visits or 0)
        if not total:
            continue
        changes = changes_by_co.get(row.assigned_co, 0)
        rate = min(100, round(changes / total * 100, 1))
        if rate < 25:
            bands["critical"] += 1
        elif rate < 50:
            bands["poor"] += 1
        elif rate < 75:
            bands["acceptable"] += 1
        else:
            bands["good"] += 1

    return bands


# ── CO performance table ──────────────────────────────────────────────────────

@frappe.whitelist()
def get_co_performance_table(entitlement_code, geography=None,
                             implementing_org=None, intervention_unit=None, street=None,
                             date_from=None, date_to=None):
    """
    Per-CO performance table for Programme Manager / MIS workspace.
    Returns a list of COs with their key metrics and update rate band.
    """
    from changemakers.entitlement_api import (
        _load_config, _bucket, _sla_overdue_days, _filter_active_beneficiaries,
    )

    config = _load_config(entitlement_code)
    gb_filters = {"entitlement": entitlement_code}

    scope_streets = _get_scope_streets(implementing_org, intervention_unit, street)
    if scope_streets is not None:
        if not scope_streets:
            return {"rows": [], "entitlement_name": config["name"]}
        gb_filters["street"] = ["in", scope_streets]

    beneficiaries = frappe.get_all(
        "Generic Beneficiary",
        filters=gb_filters,
        fields=["name", "container", "street", "assigned_co",
                "doc1_status", "doc2_status", "doc3_status", "doc4_status",
                "final_status", "visit_count", "last_visited_at",
                "source_docname"],
    )
    beneficiaries = _filter_active_beneficiaries(beneficiaries)

    container_finals = {}
    if config["final_status_at"] == "Household":
        cids = list({b.container for b in beneficiaries if b.container})
        if cids:
            rows = frappe.get_all(
                "Generic Container",
                filters={"name": ["in", cids]},
                fields=["name", "final_status"],
            )
            container_finals = {r.name: r.final_status or "" for r in rows}

    co_buckets = defaultdict(lambda: defaultdict(int))
    co_sla = defaultdict(int)
    co_total = defaultdict(int)
    co_visited = defaultdict(int)

    for b in beneficiaries:
        co = b.assigned_co or "unassigned"
        cf = container_finals.get(b.container, "") if b.container else ""
        bkt = _bucket(config, frappe._dict(b), cf)
        co_buckets[co][bkt] += 1
        co_total[co] += 1
        if int(b.visit_count or 0) > 0:
            co_visited[co] += 1
        if _sla_overdue_days(config, b) > 0:
            co_sla[co] += 1

    # Status change counts per CO (date range or default 30 days)
    _date_cond = "AND changed_at >= DATE_SUB(NOW(), INTERVAL 30 DAY)"
    _date_vals = {}
    if date_from and date_to:
        _date_cond = "AND changed_at BETWEEN %(date_from)s AND %(date_to)s"
        _date_vals = {"date_from": date_from + " 00:00:00", "date_to": date_to + " 23:59:59"}
    elif date_from:
        _date_cond = "AND changed_at >= %(date_from)s"
        _date_vals = {"date_from": date_from + " 00:00:00"}

    co_changes = frappe.db.sql(f"""
        SELECT co, COUNT(*) as changes
        FROM `tabEntitlement Status Log`
        WHERE entitlement = %(e)s
          {_date_cond}
        GROUP BY co
    """, {"e": entitlement_code, **_date_vals}, as_dict=True)
    changes_by_co = {r.co: r.changes for r in co_changes}

    # Pending AC Reviews per CO
    ac_reviews = frappe.db.sql("""
        SELECT co, COUNT(*) as cnt
        FROM `tabGeneric AC Review`
        WHERE entitlement = %(e)s AND status = 'Pending AC Review'
        GROUP BY co
    """, {"e": entitlement_code}, as_dict=True)
    ac_by_co = {r.co: r.cnt for r in ac_reviews}

    # Resolve CO display names
    all_co_ids = list(co_total.keys())
    co_names = {}
    if all_co_ids:
        rows = frappe.get_all(
            "Staff details - WRP",
            filters={"name": ["in", all_co_ids]},
            fields=["name", "full_name"],
        )
        co_names = {r.name: r.full_name or r.name for r in rows}

    result = []
    for co, total in co_total.items():
        if co == "unassigned":
            continue
        buckets = co_buckets[co]
        goal = buckets.get("goal", 0)
        visited = co_visited[co]
        total_visits = sum(
            int(b.visit_count or 0)
            for b in beneficiaries if (b.assigned_co or "unassigned") == co
        )
        changes = changes_by_co.get(co, 0)
        update_rate = min(100, round(changes / max(total_visits, 1) * 100, 1))

        if update_rate < 25:
            band = "critical"
            band_color = "#ef4444"
        elif update_rate < 50:
            band = "poor"
            band_color = "#f97316"
        elif update_rate < 75:
            band = "acceptable"
            band_color = "#eab308"
        else:
            band = "good"
            band_color = "#22c55e"

        result.append({
            "co_id":            co,
            "co_name":          co_names.get(co, co),
            "total":            total,
            "visited":          visited,
            "goal":             goal,
            "docs_in_progress": buckets.get("docs_in_progress", 0),
            "docs_ready":       buckets.get("docs_ready", 0),
            "unvisited":        buckets.get("unvisited", 0),
            "applied_pending":  buckets.get("applied_pending", 0),
            "negative":         buckets.get("negative", 0),
            "saturation_pct":   round(goal / total * 100, 1) if total else 0,
            "coverage_pct":     round(visited / total * 100, 1) if total else 0,
            "sla_overdue":      co_sla.get(co, 0),
            "update_rate":      update_rate,
            "update_rate_band": band,
            "update_rate_color": band_color,
            "pending_ac_review": ac_by_co.get(co, 0),
        })

    result.sort(key=lambda x: -x["saturation_pct"])
    return {"rows": result, "entitlement_name": config["name"]}


# ── Sankey / transitions data ─────────────────────────────────────────────────

@frappe.whitelist()
def get_sankey_data(entitlement_code, days=30, geography=None,
                    implementing_org=None, intervention_unit=None, street=None):
    """
    Bucket-to-bucket transition counts for a Sankey diagram.
    Pulls from Entitlement Status Log (final_status changes only,
    which drive bucket transitions).
    """
    scope_streets = _get_scope_streets(implementing_org, intervention_unit, street)
    scope_cond = ""
    scope_vals = {}
    if scope_streets is not None:
        if not scope_streets:
            return {"bucket_transitions": [], "slot_transitions": [], "days": int(days)}
        scope_cond = "AND beneficiary IN (SELECT name FROM `tabGeneric Beneficiary` WHERE entitlement = %(e)s AND street IN %(scope_streets)s)"
        scope_vals = {"scope_streets": tuple(scope_streets)}

    rows = frappe.db.sql(f"""
        SELECT old_bucket, new_bucket, COUNT(*) as cnt
        FROM `tabEntitlement Status Log`
        WHERE entitlement = %(e)s
          AND doc_slot = 'final_status'
          AND old_bucket != new_bucket
          AND changed_at >= DATE_SUB(NOW(), INTERVAL %(d)s DAY)
          {scope_cond}
        GROUP BY old_bucket, new_bucket
        ORDER BY cnt DESC
    """, {"e": entitlement_code, "d": int(days), **scope_vals}, as_dict=True)

    BUCKET_LABELS = {
        "unvisited":      "Unvisited",
        "docs_in_progress": "Docs In Progress",
        "docs_ready":     "Docs Ready",
        "applied_pending": "Applied – Pending",
        "goal":           "Goal Achieved",
        "negative":       "Closed – Negative",
    }

    transitions = [
        {
            "from":  BUCKET_LABELS.get(r.old_bucket, r.old_bucket),
            "to":    BUCKET_LABELS.get(r.new_bucket, r.new_bucket),
            "count": r.cnt,
        }
        for r in rows
        if r.old_bucket and r.new_bucket
    ]

    # Also gather slot-level transitions (doc changes)
    slot_rows = frappe.db.sql(f"""
        SELECT doc_label, old_label, new_label, COUNT(*) as cnt
        FROM `tabEntitlement Status Log`
        WHERE entitlement = %(e)s
          AND doc_slot != 'final_status'
          AND changed_at >= DATE_SUB(NOW(), INTERVAL %(d)s DAY)
          AND old_label != new_label
          {scope_cond}
        GROUP BY doc_label, old_label, new_label
        ORDER BY cnt DESC
        LIMIT 50
    """, {"e": entitlement_code, "d": int(days), **scope_vals}, as_dict=True)

    return {
        "bucket_transitions": transitions,
        "slot_transitions": [dict(r) for r in slot_rows],
        "days": int(days),
    }


# ── AC Review queue ───────────────────────────────────────────────────────────

@frappe.whitelist()
def get_ac_review_queue(entitlement_code, status_filter="Pending AC Review"):
    """
    Returns Generic AC Review records for the current user's geography/AC scope.

    AC scoping: the `co` field on a Generic AC Review is the field-CO who
    escalated, not the AC. ACs are scoped via `Street List - WRP.ac_alloted`,
    and a review's `container` matches the beneficiary's street, so we filter
    `container IN (streets allotted to this AC)`.
    """
    access = resolve_user_access(entitlement_code)
    filters = {"entitlement": entitlement_code}
    if status_filter:
        filters["status"] = status_filter

    if access["access_level"] == "Area Coordinator":
        ac_staff = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "name"
        )
        if not ac_staff:
            return {"reviews": []}
        ac_streets = frappe.get_all(
            "Street List  - WRP",
            filters={"ac_alloted": ac_staff},
            pluck="name",
        )
        if not ac_streets:
            return {"reviews": []}
        filters["container"] = ["in", ac_streets]

    reviews = frappe.get_all(
        "Generic AC Review",
        filters=filters,
        fields=["name", "beneficiary", "beneficiary_name", "container",
                "co", "escalation_date", "visit_count", "status",
                "ac_notes", "resolved_date"],
        order_by="escalation_date asc",
        limit=500,
    )
    return {"reviews": [dict(r) for r in reviews]}


@frappe.whitelist()
def export_ac_reviews_xlsx(entitlement_code, status_filter=None):
    """
    Download the AC review queue as an .xlsx file.
    MIS coordinators use this to reconcile against external trackers.
    status_filter is optional — empty means all statuses.
    """
    from frappe.utils.xlsxutils import make_xlsx

    filters = {"entitlement": entitlement_code}
    if status_filter:
        filters["status"] = status_filter

    rows = frappe.get_all(
        "Generic AC Review",
        filters=filters,
        fields=["name", "beneficiary", "beneficiary_name", "container",
                "co", "escalation_date", "visit_count", "status",
                "ac_notes", "resolved_date"],
        order_by="escalation_date asc",
    )

    # Resolve CO display names
    co_ids = list({r.co for r in rows if r.co})
    co_names = {}
    if co_ids:
        for r in frappe.get_all(
            "Staff details - WRP",
            filters={"name": ["in", co_ids]},
            fields=["name", "full_name"],
        ):
            co_names[r.name] = r.full_name or r.name

    header = [
        "Review ID", "Beneficiary ID", "Beneficiary Name", "Container",
        "CO ID", "CO Name", "Escalation Date", "Visit Count",
        "Status", "AC Notes", "Resolved Date",
    ]
    data = [header]
    for r in rows:
        data.append([
            r.name or "",
            r.beneficiary or "",
            r.beneficiary_name or "",
            r.container or "",
            r.co or "",
            co_names.get(r.co, ""),
            str(r.escalation_date) if r.escalation_date else "",
            int(r.visit_count or 0),
            r.status or "",
            r.ac_notes or "",
            str(r.resolved_date) if r.resolved_date else "",
        ])

    xlsx_data = make_xlsx(data, "AC Reviews")
    frappe.response["filename"] = f"ac_reviews_{entitlement_code}_{frappe.utils.nowdate()}.xlsx"
    frappe.response["filecontent"] = xlsx_data.getvalue()
    frappe.response["type"] = "binary"


@frappe.whitelist()
def update_ac_review(review_id, status, ac_notes=None):
    """
    Update a Generic AC Review record (AC clears, blocks, closes, or reopens).
    Allowed statuses:
      - 'Cleared – Will Apply'        — docs in hand, CO to apply
      - 'Blocked – No Resolution'     — needs follow-up (still actionable)
      - 'Closed – Unreachable'        — case can't progress; also sets the
                                        beneficiary's final_status to 'closed'
      - 'Pending AC Review'           — reopen (used on previously Blocked
                                        items the AC wants to revisit)
    """
    allowed = {
        "Cleared – Will Apply",
        "Blocked – No Resolution",
        "Closed – Unreachable",
        "Pending AC Review",
    }
    if status not in allowed:
        frappe.throw(f"Invalid status: {status}")

    doc = frappe.get_doc("Generic AC Review", review_id)
    doc.status = status
    if ac_notes:
        doc.ac_notes = ac_notes

    if status == "Pending AC Review":
        # Reopen: clear resolution timestamp so AC can take fresh action
        doc.resolved_date = None
    else:
        doc.resolved_date = nowdate()

    doc.save(ignore_permissions=True)

    # When AC marks a review as Closed, mirror that on the Generic Beneficiary
    # so dashboards/workplans correctly reflect the case as closed-negative.
    if status == "Closed – Unreachable" and doc.beneficiary:
        try:
            beneficiary = frappe.get_doc("Generic Beneficiary", doc.beneficiary)
            if (beneficiary.final_status or "") != "closed":
                old_final = beneficiary.final_status or ""
                beneficiary.final_status = "closed"
                reason = (ac_notes or "").strip()
                stamp = f"[AC closed {nowdate()}]"
                if reason:
                    stamp += f" {reason}"
                beneficiary.notes = ((beneficiary.notes or "") + "\n" + stamp).strip()
                beneficiary.save(ignore_permissions=True)

                # Log the transition so the Daily Update Report picks it up
                try:
                    from changemakers.entitlement_api import _load_config, _log_status
                    config = _load_config(doc.entitlement)
                    _log_status(
                        doc.entitlement, doc.beneficiary, beneficiary.container,
                        "final_status", old_final, "closed", config,
                    )
                except Exception:
                    frappe.log_error(
                        frappe.get_traceback(),
                        "update_ac_review: status log write failed",
                    )
        except Exception:
            frappe.log_error(
                frappe.get_traceback(),
                "update_ac_review: beneficiary close-out failed",
            )

    return {"status": "ok", "review_id": review_id, "new_status": status}


# ── Update rate by CO ─────────────────────────────────────────────────────────

@frappe.whitelist()
def get_update_rate_by_co(entitlement_code, days=30,
                          implementing_org=None, intervention_unit=None, street=None):
    """
    Returns update rate per CO with band classification.
    Used for the bar chart in the Programme Dashboard.
    """
    from changemakers.entitlement_api import ACTIVE_IND_JOIN, ACTIVE_IND_WHERE, IND_ACTIVE_STATUS

    scope_streets = _get_scope_streets(implementing_org, intervention_unit, street)
    scope_cond_gb = ""
    scope_cond_log = ""
    scope_vals = {}
    if scope_streets is not None:
        if not scope_streets:
            return {"rows": [], "days": int(days)}
        scope_cond_gb = "AND gb.street IN %(scope_streets)s"
        scope_cond_log = "AND beneficiary IN (SELECT name FROM `tabGeneric Beneficiary` WHERE entitlement = %(e)s AND street IN %(scope_streets)s)"
        scope_vals = {"scope_streets": tuple(scope_streets)}

    co_visits = frappe.db.sql(f"""
        SELECT gb.assigned_co AS assigned_co, SUM(gb.visit_count) as total_visits
        FROM `tabGeneric Beneficiary` gb
        {ACTIVE_IND_JOIN}
        WHERE gb.entitlement = %(e)s
          AND gb.assigned_co IS NOT NULL AND gb.assigned_co != ''
          AND {ACTIVE_IND_WHERE}
          {scope_cond_gb}
        GROUP BY gb.assigned_co
    """, {"e": entitlement_code, "_ind_active_status": IND_ACTIVE_STATUS, **scope_vals}, as_dict=True)

    co_changes = frappe.db.sql(f"""
        SELECT co, COUNT(*) as changes
        FROM `tabEntitlement Status Log`
        WHERE entitlement = %(e)s
          AND changed_at >= DATE_SUB(NOW(), INTERVAL %(d)s DAY)
          AND co IS NOT NULL AND co != ''
          {scope_cond_log}
        GROUP BY co
    """, {"e": entitlement_code, "d": int(days), **scope_vals}, as_dict=True)
    changes_by_co = {r.co: r.changes for r in co_changes}

    co_ids = [r.assigned_co for r in co_visits if r.assigned_co]
    co_names = {}
    if co_ids:
        rows = frappe.get_all(
            "Staff details - WRP",
            filters={"name": ["in", co_ids]},
            fields=["name", "full_name"],
        )
        co_names = {r.name: r.full_name or r.name for r in rows}

    result = []
    for row in co_visits:
        co = row.assigned_co
        total = int(row.total_visits or 0)
        if not total:
            continue
        changes = changes_by_co.get(co, 0)
        rate = min(100, round(changes / total * 100, 1))

        if rate < 25:
            band, color = "Critical", "#ef4444"
        elif rate < 50:
            band, color = "Poor", "#f97316"
        elif rate < 75:
            band, color = "Acceptable", "#eab308"
        else:
            band, color = "Good", "#22c55e"

        result.append({
            "co_id":   co,
            "co_name": co_names.get(co, co),
            "rate":    rate,
            "band":    band,
            "color":   color,
        })

    result.sort(key=lambda x: -x["rate"])
    return {"rows": result, "days": int(days)}


# ── Scheme list for selector ──────────────────────────────────────────────────

@frappe.whitelist()
def get_dashboard_schemes(geography=None):
    """
    Returns all enabled generic entitlement schemes for the scheme selector dropdown.
    """
    access = resolve_user_access()
    geo = geography or access.get("geography") or None

    filters = {"enabled": 1, "entitlement_code": ["!=", "E1"]}
    if geo:
        filters["geography"] = geo

    schemes = frappe.get_all(
        "Entitlement Config",
        filters=filters,
        fields=["entitlement_code", "entitlement_name", "geography"],
        order_by="entitlement_code asc",
    )
    return {"schemes": [dict(s) for s in schemes]}


@frappe.whitelist()
def get_implementing_orgs(entitlement_code):
    """Returns distinct implementing orgs that have beneficiaries in a scheme."""
    streets = frappe.get_all(
        "Generic Beneficiary",
        filters={"entitlement": entitlement_code},
        pluck="street",
        distinct=True,
    )
    streets = [s for s in streets if s]
    if not streets:
        return {"orgs": []}
    orgs = frappe.get_all(
        "Street List  - WRP",
        filters={"name": ["in", streets]},
        fields=["implementing_org"],
        distinct=True,
    )
    result = sorted(o.implementing_org for o in orgs if o.implementing_org)
    return {"orgs": result}


# ── Auto-escalation helper (called from entitlement_api) ─────────────────────

def maybe_escalate_for_ac_review(entitlement_code, beneficiary_id, visit_count, bucket):
    """
    If a beneficiary in docs_in_progress reaches 3 visits, auto-create a
    Generic AC Review record if one doesn't already exist.
    Called from save_beneficiary_status after save.
    """
    if bucket != "docs_in_progress":
        return
    if int(visit_count) < 3:
        return

    existing = frappe.db.exists(
        "Generic AC Review",
        {"entitlement": entitlement_code, "beneficiary": beneficiary_id,
         "status": "Pending AC Review"},
    )
    if existing:
        return

    b = frappe.db.get_value(
        "Generic Beneficiary",
        beneficiary_id,
        ["beneficiary_name", "container", "street", "assigned_co"],
        as_dict=True,
    ) or {}

    co = frappe.db.get_value(
        "Staff details - WRP", {"mail_id": frappe.session.user}, "name"
    ) or b.get("assigned_co") or ""

    frappe.get_doc({
        "doctype":        "Generic AC Review",
        "entitlement":    entitlement_code,
        "beneficiary":    beneficiary_id,
        "beneficiary_name": b.get("beneficiary_name") or "",
        "container":      b.get("container") or b.get("street") or "",
        "co":             co,
        "escalation_date": nowdate(),
        "visit_count":    int(visit_count),
        "status":         "Pending AC Review",
    }).insert(ignore_permissions=True)


# ── Org progress table ───────────────────────────────────────────────────────

@frappe.whitelist()
def get_org_progress_table(entitlement_code,
                           implementing_org=None, intervention_unit=None, street=None):
    """
    Returns one row per implementing org showing total beneficiaries and
    bucket breakdown — the denominator-vs-progress view for partner NGOs.
    Org is resolved via beneficiary.street → Street List - WRP.implementing_org.
    """
    from changemakers.entitlement_api import (
        _load_config, _bucket, _filter_active_beneficiaries,
    )

    config = _load_config(entitlement_code)
    gb_filters = {"entitlement": entitlement_code}

    scope_streets = _get_scope_streets(implementing_org, intervention_unit, street)
    if scope_streets is not None:
        if not scope_streets:
            return {"rows": [], "entitlement_name": config["name"], "goal_label": config["final_status_label"]}
        gb_filters["street"] = ["in", scope_streets]

    beneficiaries = frappe.get_all(
        "Generic Beneficiary",
        filters=gb_filters,
        fields=["name", "container", "street", "assigned_co",
                "doc1_status", "doc2_status", "doc3_status", "doc4_status",
                "final_status", "visit_count", "last_visited_at",
                "source_docname"],
    )
    beneficiaries = _filter_active_beneficiaries(beneficiaries)

    # Resolve implementing_org per street
    streets = list({b.street for b in beneficiaries if b.street})
    street_org = {}
    if streets:
        rows = frappe.get_all(
            "Street List  - WRP",
            filters={"name": ["in", streets]},
            fields=["name", "implementing_org"],
        )
        street_org = {r.name: r.implementing_org or "Unknown" for r in rows}

    container_finals = {}
    if config["final_status_at"] == "Household":
        cids = list({b.container for b in beneficiaries if b.container})
        if cids:
            rows = frappe.get_all(
                "Generic Container",
                filters={"name": ["in", cids]},
                fields=["name", "final_status"],
            )
            container_finals = {r.name: r.final_status or "" for r in rows}

    org_buckets = defaultdict(lambda: defaultdict(int))
    org_visited = defaultdict(int)
    org_total = defaultdict(int)

    for b in beneficiaries:
        org = street_org.get(b.street, "Unknown") if b.street else "Unknown"
        cf = container_finals.get(b.container, "") if b.container else ""
        bkt = _bucket(config, frappe._dict(b), cf)
        org_buckets[org][bkt] += 1
        org_total[org] += 1
        if int(b.visit_count or 0) > 0:
            org_visited[org] += 1

    result = []
    for org, total in org_total.items():
        buckets = org_buckets[org]
        goal = buckets.get("goal", 0)
        visited = org_visited[org]
        result.append({
            "org":              org,
            "total":            total,
            "visited":          visited,
            "unvisited":        buckets.get("unvisited", 0),
            "docs_in_progress": buckets.get("docs_in_progress", 0),
            "docs_ready":       buckets.get("docs_ready", 0),
            "applied_pending":  buckets.get("applied_pending", 0),
            "goal":             goal,
            "negative":         buckets.get("negative", 0),
            "saturation_pct":   round(goal / total * 100, 1) if total else 0,
            "coverage_pct":     round(visited / total * 100, 1) if total else 0,
        })

    result.sort(key=lambda x: -x["saturation_pct"])
    return {
        "rows":               result,
        "entitlement_name":   config["name"],
        "goal_label":         config["final_status_label"],
    }


# ── Bucket drilldown ──────────────────────────────────────────────────────────

@frappe.whitelist()
def get_bucket_drilldown(entitlement_code, bucket, co_id=None, geography=None,
                         implementing_org=None, intervention_unit=None, street=None):
    """
    Level 1 (co_id=None): per-CO count for a bucket, sorted by count desc.
    Level 2 (co_id given): beneficiary list (up to 200) for that CO+bucket.
    """
    from changemakers.entitlement_api import (
        _load_config, _bucket, _filter_active_beneficiaries,
    )

    config = _load_config(entitlement_code)
    filters = {"entitlement": entitlement_code}
    if co_id:
        filters["assigned_co"] = co_id

    scope_streets = _get_scope_streets(implementing_org, intervention_unit, street)
    if scope_streets is not None:
        if not scope_streets:
            return {"level": "co_list", "bucket": bucket, "items": [], "total": 0}
        filters["street"] = ["in", scope_streets]

    beneficiaries = frappe.get_all(
        "Generic Beneficiary",
        filters=filters,
        fields=[
            "name", "beneficiary_name", "container", "street", "assigned_co",
            "doc1_status", "doc2_status", "doc3_status", "doc4_status",
            "final_status", "visit_count", "last_visited_at",
            "source_docname",
        ],
    )
    beneficiaries = _filter_active_beneficiaries(beneficiaries)

    container_finals = {}
    if config["final_status_at"] == "Household":
        cids = list({b.container for b in beneficiaries if b.container})
        if cids:
            rows = frappe.get_all(
                "Generic Container",
                filters={"name": ["in", cids]},
                fields=["name", "final_status"],
            )
            container_finals = {r.name: r.final_status or "" for r in rows}

    in_bucket = []
    for b in beneficiaries:
        cf = container_finals.get(b.container, "") if b.container else ""
        if _bucket(config, frappe._dict(b), cf) == bucket:
            in_bucket.append(b)

    if co_id:
        items = [
            {
                "name":             b.name,
                "beneficiary_name": b.beneficiary_name or b.name,
                "street":           b.street or "",
                "visit_count":      int(b.visit_count or 0),
                "last_visited_at":  str(b.last_visited_at) if b.last_visited_at else "",
            }
            for b in in_bucket[:200]
        ]
        return {"level": "beneficiaries", "bucket": bucket, "co_id": co_id, "items": items, "total": len(in_bucket)}

    # Level 1: group by CO
    by_co = defaultdict(int)
    for b in in_bucket:
        by_co[b.assigned_co or "unassigned"] += 1

    co_ids = [c for c in by_co if c != "unassigned"]
    co_names = {}
    if co_ids:
        rows = frappe.get_all(
            "Staff details - WRP",
            filters={"name": ["in", co_ids]},
            fields=["name", "full_name"],
        )
        co_names = {r.name: r.full_name or r.name for r in rows}

    items = [
        {"co_id": co, "co_name": co_names.get(co, co), "count": cnt}
        for co, cnt in sorted(by_co.items(), key=lambda x: -x[1])
    ]
    return {"level": "co_list", "bucket": bucket, "items": items, "total": len(in_bucket)}
