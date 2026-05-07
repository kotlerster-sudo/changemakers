"""
Generic Entitlement API
-----------------------
All config-driven. Flutter reads get_entitlement_config once per session
and renders everything dynamically. No hardcoded field names in the app.

Endpoints:
  get_entitlement_config      - full schema for all enabled entitlements
  get_daily_workplan_v2       - generic 9/9/9/3 pool plan
  save_beneficiary_status     - generic status save + status log
  get_co_performance_v2       - generic performance metrics
"""

import frappe
from frappe.utils import getdate, nowdate, now_datetime
import json
from collections import defaultdict

# ── Config loader ─────────────────────────────────────────────────────────────

def _load_config(entitlement_code):
    """Load and return a parsed entitlement config dict."""
    doc = frappe.get_doc("Entitlement Config", entitlement_code)

    slots = []
    for slot in sorted(doc.doc_slots, key=lambda s: s.slot_number):
        # Frappe does not load nested child tables automatically — fetch explicitly
        slot_status_rows = frappe.get_all(
            "Doc Slot Status",
            filters={"parent": slot.name, "parenttype": "Entitlement Doc Slot"},
            fields=["status_value", "label", "is_terminal", "starts_sla", "color", "sort_order"],
            order_by="sort_order asc",
        )
        statuses = [
            {
                "value":       s.status_value,
                "label":       s.label,
                "terminal":    bool(s.is_terminal),
                "starts_sla":  bool(s.starts_sla),
                "color":       s.color or "grey",
                "sort_order":  s.sort_order or 0,
            }
            for s in slot_status_rows
        ]
        slots.append({
            "slot_number":       slot.slot_number,
            "slot_key":          slot.slot_key or f"doc{slot.slot_number}",
            "label":             slot.label,
            "sla_days":          slot.sla_days or 0,
            "required_for_unlock": bool(slot.required_for_unlock),
            "statuses":          statuses,
            "terminal_values":   {s["value"] for s in statuses if s["terminal"]},
            "sla_start_values":  {s["value"] for s in statuses if s["starts_sla"]},
        })

    final_status_rows = frappe.get_all(
        "Entitlement Final Status",
        filters={"parent": doc.name, "parenttype": "Entitlement Config"},
        fields=["status_value", "label", "is_goal", "is_negative", "requires_unlock", "color", "sort_order"],
        order_by="sort_order asc",
    )
    final_statuses = [
        {
            "value":           s.status_value,
            "label":           s.label,
            "is_goal":         bool(s.is_goal),
            "is_negative":     bool(s.is_negative),
            "requires_unlock": bool(s.requires_unlock),
            "color":           s.color or "grey",
            "sort_order":      s.sort_order or 0,
        }
        for s in final_status_rows
    ]

    return {
        "code":               doc.entitlement_code,
        "name":               doc.entitlement_name,
        "enabled":            bool(doc.enabled),
        "geography":          doc.geography or "",
        "beneficiary_unit":   doc.beneficiary_unit,
        "doc_tracking_level": doc.doc_tracking_level,
        "final_status_at":    doc.final_status_at,
        "max_doc_slots":      doc.max_doc_slots,
        "final_status_label": doc.final_status_label or "Status",
        "unlock_rule":        doc.unlock_rule,
        "goal_status_value":  doc.goal_status_value or "",
        "slots":              slots,
        "final_statuses":     final_statuses,
        "goal_values":        {s["value"] for s in final_statuses if s["is_goal"]},
        "negative_values":    {s["value"] for s in final_statuses if s["is_negative"]},
    }


def _is_unlocked(config, beneficiary_doc):
    """Return True if all required-for-unlock docs are terminal."""
    rule = config["unlock_rule"]
    if rule == "NONE":
        return True
    slots = [s for s in config["slots"] if s["required_for_unlock"]]
    if not slots:
        return True

    vals = [
        getattr(beneficiary_doc, s["slot_key"], "") or ""
        for s in slots
    ]
    terminals = [s["terminal_values"] for s in slots]

    if rule == "ALL_REQUIRED_TERMINAL":
        return all(v in t for v, t in zip(vals, terminals))
    if rule == "ANY_TERMINAL":
        return any(v in t for v, t in zip(vals, terminals))
    return False


def _bucket(config, beneficiary_doc, container_final=None):
    """
    Classify a beneficiary into a pipeline bucket.
    Returns one of: unvisited, docs_in_progress, docs_ready,
                    applied_pending, goal, negative
    """
    # final status is tracked at container or individual level
    final = container_final if config["final_status_at"] == "Household" \
            else (beneficiary_doc.final_status or "")

    if final in config["goal_values"]:
        return "goal"
    if final in config["negative_values"]:
        return "negative"
    # check if a "requires_unlock" final status is set (e.g. applied)
    applied_values = {
        s["value"] for s in config["final_statuses"]
        if not s["is_goal"] and not s["is_negative"] and s["requires_unlock"]
    }
    if final in applied_values:
        return "applied_pending"

    if int(beneficiary_doc.visit_count or 0) == 0:
        return "unvisited"
    if _is_unlocked(config, beneficiary_doc):
        return "docs_ready"
    return "docs_in_progress"


# ── Public API ────────────────────────────────────────────────────────────────

@frappe.whitelist()
def get_entitlement_config(geography=None):
    """
    Returns all enabled entitlement configs for a geography.
    Flutter calls this once per session and caches.

    Response:
      { "entitlements": [ { ...full schema per entitlement... } ] }
    """
    filters = {"enabled": 1}
    if geography:
        filters["geography"] = geography

    codes = frappe.get_all(
        "Entitlement Config",
        filters=filters,
        pluck="entitlement_code",
    )

    result = []
    for code in codes:
        try:
            cfg = _load_config(code)
            # Convert sets to lists for JSON serialisation
            cfg["goal_values"]     = list(cfg["goal_values"])
            cfg["negative_values"] = list(cfg["negative_values"])
            for s in cfg["slots"]:
                s["terminal_values"] = list(s["terminal_values"])
                s["sla_start_values"] = list(s["sla_start_values"])
            result.append(cfg)
        except Exception:
            frappe.log_error(frappe.get_traceback(), f"get_entitlement_config: {code}")

    return {"entitlements": result}


@frappe.whitelist()
def get_daily_workplan_v2(entitlement_code, co_id=None, date=None, force_refresh=0):
    """
    Generic 9/9/9/3 daily plan for any entitlement.

    Pool 1 (max 9): unvisited
    Pool 2 (max 9): docs_ready
    Pool 3 (max 9): SLA overdue | longest idle (docs_in_progress)
    Pool 4 (max 3): goal/negative never visited (pool 4 overflow)

    Cached per co+date in Redis. force_refresh=1 busts the cache.
    """
    if not co_id:
        co_id = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "name"
        )
    if not co_id:
        return {"error": "CO not found for current user"}

    today = getdate(date or nowdate())
    cache_key = f"generic_workplan:{entitlement_code}:{co_id}:{today}"

    if not int(force_refresh):
        cached = frappe.cache().get_value(cache_key)
        if cached:
            return cached

    config = _load_config(entitlement_code)

    # Get CO's streets
    streets = frappe.get_all(
        "Street List  - WRP",
        filters={"added_by_co": co_id},
        pluck="name",
    )
    if not streets:
        return {"daily_plan": [], "total": 0}

    # Get all beneficiaries in scope
    beneficiaries = frappe.get_all(
        "Generic Beneficiary",
        filters={"entitlement": entitlement_code, "street": ["in", streets]},
        fields=["name", "beneficiary_name", "container", "street",
                "doc1_status", "doc2_status", "doc3_status", "doc4_status",
                "final_status", "visit_count", "last_visited_at"],
    )

    # Get container final statuses if needed
    container_finals = {}
    if config["final_status_at"] == "Household":
        container_ids = list({b.container for b in beneficiaries if b.container})
        if container_ids:
            rows = frappe.get_all(
                "Generic Container",
                filters={"name": ["in", container_ids]},
                fields=["name", "final_status"],
            )
            container_finals = {r.name: r.final_status or "" for r in rows}

    # Classify into buckets
    pool1, pool2, pool3_sla, pool3_idle, pool4 = [], [], [], [], []

    today_dt = getdate(today)
    for b in beneficiaries:
        b_dict = b  # already a dict from get_all
        cf = container_finals.get(b.container, "") if b.container else ""
        bucket = _bucket(config, frappe._dict(b), cf)

        entry = dict(b)
        entry["bucket"] = bucket
        entry["visited_today"] = (
            getdate(b.last_visited_at) == today_dt if b.last_visited_at else False
        )

        if bucket == "unvisited":
            pool1.append(entry)
        elif bucket == "docs_ready":
            pool2.append(entry)
        elif bucket in ("goal", "negative"):
            if int(b.visit_count or 0) == 0:
                pool4.append(entry)
        elif bucket in ("docs_in_progress", "applied_pending"):
            # Check SLA overdue
            overdue_days = _sla_overdue_days(config, b)
            if overdue_days > 0:
                entry["overdue_days"] = overdue_days
                pool3_sla.append(entry)
            else:
                pool3_idle.append(entry)

    # Sort pools
    pool1.sort(key=lambda x: x.get("street", ""))
    pool2.sort(key=lambda x: x.get("street", ""))
    pool3_sla.sort(key=lambda x: -x.get("overdue_days", 0))
    pool3_idle.sort(key=lambda x: x.get("last_visited_at") or "")
    pool3 = pool3_sla + pool3_idle
    pool4.sort(key=lambda x: x.get("street", ""))

    # Assemble 30
    plan = pool1[:9] + pool2[:9] + pool3[:9]
    used = {b["name"] for b in plan}

    # Overflow from tails
    for overflow in [pool1[9:], pool2[9:], pool3[9:]]:
        for b in overflow:
            if len(plan) >= 30:
                break
            if b["name"] not in used:
                plan.append(b)
                used.add(b["name"])

    # Pool 4 top-up
    for b in pool4:
        if len(plan) >= 30:
            break
        if b["name"] not in used:
            plan.append(b)
            used.add(b["name"])

    # Final sort by street
    plan.sort(key=lambda x: (x.get("street", ""), x.get("bucket", "")))

    # Resolve labels for Flutter
    slot_label_map = {s["slot_key"]: s["label"] for s in config["slots"]}
    status_label_map = {}
    for slot in config["slots"]:
        for st in slot["statuses"]:
            status_label_map[st["value"]] = st["label"]
    final_label_map = {s["value"]: s["label"] for s in config["final_statuses"]}

    for entry in plan:
        entry["doc_labels"]    = slot_label_map
        entry["status_labels"] = status_label_map
        entry["final_labels"]  = final_label_map

    result = {
        "entitlement":      entitlement_code,
        "entitlement_name": config["name"],
        "date":             str(today),
        "co_id":            co_id,
        "daily_plan":       plan,
        "total":            len(plan),
        "pool_sizes": {
            "unvisited":      len(pool1),
            "docs_ready":     len(pool2),
            "follow_up":      len(pool3),
            "pool4_overflow": len(pool4),
        },
    }

    frappe.cache().set_value(cache_key, result, expires_in_sec=86400)
    return result


def _sla_overdue_days(config, b):
    """Return the max overdue days across all SLA-tracked slots. 0 = not overdue."""
    from frappe.utils import date_diff
    today = getdate(nowdate())
    max_overdue = 0

    for slot in config["slots"]:
        if not slot["sla_days"]:
            continue
        val = getattr(frappe._dict(b), slot["slot_key"], "") or ""
        if val in slot["sla_start_values"]:
            last = b.get("last_visited_at") if isinstance(b, dict) else b.last_visited_at
            if last:
                days_since = date_diff(today, getdate(last))
                overdue = days_since - slot["sla_days"]
                if overdue > max_overdue:
                    max_overdue = overdue
    return max_overdue


@frappe.whitelist()
def save_beneficiary_status(
    entitlement_code,
    beneficiary_id,
    doc_slot=None,
    new_status=None,
    final_status=None,
    container_id=None,
    notes=None,
):
    """
    Generic status save for any entitlement.

    doc_slot:     "doc1" | "doc2" | "doc3" | "doc4" (update a document status)
    final_status: update the final status (at container or individual level)
    Both can be passed in one call.
    """
    config = _load_config(entitlement_code)

    beneficiary = frappe.get_doc("Generic Beneficiary", beneficiary_id)
    changed = False

    if doc_slot and new_status is not None:
        valid_slots = {s["slot_key"] for s in config["slots"]}
        if doc_slot not in valid_slots:
            frappe.throw(f"Invalid doc_slot '{doc_slot}' for entitlement {entitlement_code}")
        old_val = getattr(beneficiary, doc_slot, "") or ""
        if old_val != new_status:
            setattr(beneficiary, doc_slot, new_status)
            changed = True
            _log_status(
                entitlement_code, beneficiary_id,
                container_id or beneficiary.container,
                doc_slot, old_val, new_status, config
            )

    if final_status is not None:
        if config["final_status_at"] == "Household" and (container_id or beneficiary.container):
            cid = container_id or beneficiary.container
            container = frappe.get_doc("Generic Container", cid)
            old_final = container.final_status or ""
            if old_final != final_status:
                container.final_status = final_status
                container.save(ignore_permissions=True)
                _log_status(
                    entitlement_code, beneficiary_id, cid,
                    "final_status", old_final, final_status, config
                )
        else:
            old_final = beneficiary.final_status or ""
            if old_final != final_status:
                beneficiary.final_status = final_status
                changed = True
                _log_status(
                    entitlement_code, beneficiary_id,
                    container_id or beneficiary.container,
                    "final_status", old_final, final_status, config
                )

    if notes is not None:
        beneficiary.notes = notes
        changed = True

    # Update visit tracking
    beneficiary.visit_count = int(beneficiary.visit_count or 0) + 1
    beneficiary.last_visited_at = now_datetime()

    beneficiary.save(ignore_permissions=True)

    # Bust cache
    co_id = beneficiary.assigned_co
    if co_id:
        today = getdate(nowdate())
        frappe.cache().delete_value(
            f"generic_workplan:{entitlement_code}:{co_id}:{today}"
        )

    return {"status": "ok", "beneficiary": beneficiary_id}


def _resolve_label(config, doc_slot, status_value):
    """Resolve a raw status_value to its human label from config."""
    if doc_slot == "final_status":
        for s in config["final_statuses"]:
            if s["value"] == status_value:
                return s["label"]
        return status_value or ""
    for slot in config["slots"]:
        if slot["slot_key"] == doc_slot:
            for s in slot["statuses"]:
                if s["value"] == status_value:
                    return s["label"]
            return status_value or ""
    return status_value or ""


def _resolve_doc_label(config, doc_slot):
    """Resolve a slot key to its document label, e.g. doc1 → 'Aadhaar Card'."""
    if doc_slot == "final_status":
        return config.get("final_status_label", "Final Status")
    for slot in config["slots"]:
        if slot["slot_key"] == doc_slot:
            return slot["label"]
    return doc_slot


def _container_bucket(config, container_id, beneficiary_id=None):
    """
    Compute the current pipeline bucket for a container (household-equivalent).
    Derives from the container's final_status and the worst-case doc slot status
    across all beneficiaries in that container.
    """
    if not container_id:
        if beneficiary_id:
            b = frappe.db.get_value(
                "Generic Beneficiary", beneficiary_id,
                ["doc1_status", "doc2_status", "doc3_status", "doc4_status",
                 "final_status", "visit_count"],
                as_dict=True,
            ) or {}
            return _bucket(config, frappe._dict(b), "")
        return "unvisited"

    container = frappe.db.get_value(
        "Generic Container", container_id, ["final_status"], as_dict=True
    ) or {}
    container_final = container.get("final_status") or ""

    # Get all beneficiaries in this container
    members = frappe.get_all(
        "Generic Beneficiary",
        filters={"container": container_id, "entitlement": config["code"]},
        fields=["name", "doc1_status", "doc2_status", "doc3_status",
                "doc4_status", "final_status", "visit_count"],
    )
    if not members:
        return "unvisited"

    # Container bucket = most advanced bucket among members
    # Priority: goal > applied_pending > docs_ready > docs_in_progress > unvisited
    PRIORITY = {
        "goal": 5, "negative": 4, "applied_pending": 3,
        "docs_ready": 2, "docs_in_progress": 1, "unvisited": 0,
    }
    best = "unvisited"
    for m in members:
        bkt = _bucket(config, frappe._dict(m), container_final)
        if PRIORITY.get(bkt, 0) > PRIORITY.get(best, 0):
            best = bkt
    return best


def _log_status(entitlement_code, beneficiary_id, container_id,
                doc_slot, old_val, new_val, config):
    """
    Write a row to Entitlement Status Log.

    Computes old_bucket from the pre-change state (passed in as old_val),
    and new_bucket from the container's current state after the change has
    been saved.
    """
    try:
        # old_bucket: container state before this change
        # We approximate by temporarily reversing the change to re-classify.
        # The caller saves the beneficiary AFTER calling _log_status, so the
        # DB still has the old value at this point — we just read it directly.
        old_bucket = _container_bucket(config, container_id, beneficiary_id)

        # new_bucket: container state after this change
        # Since beneficiary.save() hasn't been called yet when we're logging a
        # doc_slot change, we compute it by patching the in-memory values.
        if container_id:
            members = frappe.get_all(
                "Generic Beneficiary",
                filters={"container": container_id, "entitlement": entitlement_code},
                fields=["name", "doc1_status", "doc2_status", "doc3_status",
                        "doc4_status", "final_status", "visit_count"],
            )
            # Apply the change in-memory to the matching beneficiary
            container_final = frappe.db.get_value(
                "Generic Container", container_id, "final_status"
            ) or ""
            if doc_slot == "final_status":
                container_final = new_val

            PRIORITY = {
                "goal": 5, "negative": 4, "applied_pending": 3,
                "docs_ready": 2, "docs_in_progress": 1, "unvisited": 0,
            }
            new_bucket = "unvisited"
            for m in members:
                m_dict = dict(m)
                if m["name"] == beneficiary_id and doc_slot != "final_status":
                    m_dict[doc_slot] = new_val
                bkt = _bucket(config, frappe._dict(m_dict), container_final)
                if PRIORITY.get(bkt, 0) > PRIORITY.get(new_bucket, 0):
                    new_bucket = bkt
        else:
            new_bucket = old_bucket  # single-member, recompute after save

        # Resolve CO from session
        co = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "name"
        ) or ""

        # Resolve street from beneficiary
        street = frappe.db.get_value("Generic Beneficiary", beneficiary_id, "street") or ""

        frappe.get_doc({
            "doctype":       "Entitlement Status Log",
            "naming_series": "ESL-.YYYY.-.#####",
            "entitlement":   entitlement_code,
            "beneficiary":   beneficiary_id,
            "container":     container_id or "",
            "street":        street,
            "co":            co,
            "doc_slot":      doc_slot,
            "doc_label":     _resolve_doc_label(config, doc_slot),
            "old_value":     old_val or "",
            "old_label":     _resolve_label(config, doc_slot, old_val),
            "old_bucket":    old_bucket,
            "new_value":     new_val or "",
            "new_label":     _resolve_label(config, doc_slot, new_val),
            "new_bucket":    new_bucket,
            "changed_at":    now_datetime(),
        }).insert(ignore_permissions=True)

    except Exception:
        frappe.log_error(frappe.get_traceback(), "entitlement_api._log_status")


@frappe.whitelist()
def get_co_schemes():
    """
    Returns the list of schemes the current CO has beneficiaries for.
    CMCHIS (E1) is included if the CO owns any streets.
    Generic schemes (E2+) are included if the CO has assigned beneficiaries.
    Flutter uses `type` to route: "legacy" → old CMCHIS flow, "generic" → new flow.
    """
    co = frappe.db.get_value(
        "Staff details - WRP", {"mail_id": frappe.session.user}, "name"
    )
    if not co:
        return {"schemes": []}

    # Street ownership is the single source of truth for all scheme assignments.
    streets = frappe.get_all(
        "Street List  - WRP", filters={"added_by_co": co}, pluck="name"
    )
    if not streets:
        return {"schemes": []}

    schemes = []

    # CMCHIS — old system; any CO with streets has CMCHIS households
    schemes.append({
        "code":        "E1",
        "name":        "CMCHIS",
        "type":        "legacy",
        "description": "Chief Minister's Comprehensive Health Insurance Scheme",
    })

    # Generic entitlements — show if CO's streets have beneficiaries for that scheme
    active = frappe.get_all(
        "Entitlement Config",
        filters={"enabled": 1, "entitlement_code": ["!=", "E1"]},
        fields=["entitlement_code", "entitlement_name"],
    )
    for e in active:
        count = frappe.db.count(
            "Generic Beneficiary",
            {"entitlement": e.entitlement_code, "street": ["in", streets]},
        )
        if count:
            schemes.append({
                "code":  e.entitlement_code,
                "name":  e.entitlement_name,
                "type":  "generic",
                "total": count,
            })

    return {"schemes": schemes}


@frappe.whitelist()
def get_co_performance_v2(entitlement_code, co_id=None):
    """
    Generic CO performance metrics for any entitlement.
    Returns bucket counts, saturation %, coverage %, and drilldown lists.
    """
    if not co_id:
        co_id = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "name"
        )
    if not co_id:
        return {"error": "CO not found"}

    config = _load_config(entitlement_code)

    streets = frappe.get_all(
        "Street List  - WRP",
        filters={"added_by_co": co_id},
        pluck="name",
    )
    if not streets:
        return {"buckets": {}, "total": 0, "saturation_pct": 0}

    beneficiaries = frappe.get_all(
        "Generic Beneficiary",
        filters={"entitlement": entitlement_code, "street": ["in", streets]},
        fields=["name", "beneficiary_name", "container", "street",
                "doc1_status", "doc2_status", "doc3_status", "doc4_status",
                "final_status", "visit_count", "last_visited_at"],
    )

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

    buckets = defaultdict(list)
    for b in beneficiaries:
        cf = container_finals.get(b.container, "") if b.container else ""
        bkt = _bucket(config, frappe._dict(b), cf)
        buckets[bkt].append({
            "id":   b.name,
            "name": b.beneficiary_name,
            "street": b.street,
        })

    total = len(beneficiaries)
    goal_count     = len(buckets.get("goal", []))
    visited_count  = sum(1 for b in beneficiaries if int(b.visit_count or 0) > 0)
    saturation_pct = round(goal_count  / total * 100, 1) if total else 0
    coverage_pct   = round(visited_count / total * 100, 1) if total else 0

    # Resolve bucket names to labels
    bucket_counts = {k: len(v) for k, v in buckets.items()}

    return {
        "entitlement":       entitlement_code,
        "entitlement_name":  config["name"],
        "co_id":             co_id,
        "total":             total,
        "visited":           visited_count,
        "goal_count":        goal_count,
        "saturation_pct":    saturation_pct,
        "coverage_pct":      coverage_pct,
        "bucket_counts":     bucket_counts,
        "drilldown":         dict(buckets),
        "goal_label":        config["final_status_label"],
    }
