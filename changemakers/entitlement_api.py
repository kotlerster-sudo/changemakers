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

# Individual Profile-WRP.status value indicating a person still resides at the address.
# Anything else (e.g. moved out) means the linked Generic Beneficiary must be excluded
# from OAP counts even though the record persists.
IND_ACTIVE_STATUS = "Active- ஆக்டிவ்"


def _get_active_individual_names():
    """Set of all currently-Active Individual Profile-WRP names, cast to str.

    Cached on frappe.local per request.

    **str() cast is load-bearing.** Individual Profile-WRP uses numeric
    autoincrement names, so frappe.get_all returns int values for `name`.
    But `Generic Beneficiary.source_docname` is stored as a string, and
    `"64175" in {546, 547, ...}` returns False. Without the cast every
    beneficiary gets dropped from the workplan.
    """
    if not hasattr(frappe.local, "_active_ind_names"):
        rows = frappe.get_all(
            "Individual Profile-WRP",
            filters={"status": IND_ACTIVE_STATUS},
            pluck="name",
        )
        frappe.local._active_ind_names = {str(r) for r in rows}
    return frappe.local._active_ind_names


def _filter_active_beneficiaries(beneficiaries):
    """Drop beneficiaries whose source Individual Profile-WRP is no longer Active.
    Records with no source_docname are kept (defensive: don't silently lose data).

    Fails OPEN if the active set is empty.
    """
    active = _get_active_individual_names()
    if not active:
        frappe.logger().warning(
            "_filter_active_beneficiaries: active set empty — filter disabled"
        )
        return list(beneficiaries)
    out = []
    for b in beneficiaries:
        src = b.get("source_docname") if isinstance(b, dict) else getattr(b, "source_docname", None)
        if not src or str(src) in active:
            out.append(b)
    return out


@frappe.whitelist()
def debug_active_individuals():
    """Diagnostic endpoint for the moved-out filter. Returns:
      - active_set_size: how many individuals the filter considers active
      - status_distribution: actual status values + counts in DB
      - sample_gb_source_docnames: 5 source_docnames from OAP beneficiaries
      - whether those samples are in the active set
      - the exact IND_ACTIVE_STATUS string the code is comparing against
    Hit at: /api/method/changemakers.entitlement_api.debug_active_individuals
    """
    active = _get_active_individual_names()
    statuses = frappe.db.sql(
        "SELECT status, COUNT(*) AS cnt FROM `tabIndividual Profile-WRP` "
        "GROUP BY status ORDER BY cnt DESC LIMIT 10",
        as_dict=True,
    )
    sample_gb = frappe.get_all(
        "Generic Beneficiary",
        filters={"entitlement": "E2"},
        fields=["name", "source_docname", "beneficiary_name"],
        limit=5,
    )
    sample_with_match = [
        {
            "gb_name":            b.name,
            "source_docname":     b.source_docname,
            "is_in_active_set":   (b.source_docname or "") in active,
            "individual_exists":  bool(frappe.db.exists("Individual Profile-WRP", b.source_docname)) if b.source_docname else False,
            "individual_status":  frappe.db.get_value("Individual Profile-WRP", b.source_docname, "status") if b.source_docname else None,
        }
        for b in sample_gb
    ]
    return {
        "IND_ACTIVE_STATUS":     IND_ACTIVE_STATUS,
        "IND_ACTIVE_STATUS_repr": repr(IND_ACTIVE_STATUS),
        "IND_ACTIVE_STATUS_hex":  IND_ACTIVE_STATUS.encode().hex(),
        "active_set_size":       len(active),
        "active_sample":         list(active)[:5],
        "status_distribution":   [dict(s) for s in statuses],
        "sample_oap_beneficiaries": sample_with_match,
    }


# Reusable SQL fragment for excluding moved-out individuals from raw SQL queries
# on Generic Beneficiary. Aliases: `gb` for Generic Beneficiary, `ip` for the join.
ACTIVE_IND_JOIN = (
    "LEFT JOIN `tabIndividual Profile-WRP` ip ON ip.name = gb.source_docname"
)
ACTIVE_IND_WHERE = (
    "(gb.source_docname IS NULL OR gb.source_docname = '' "
    "OR ip.status = %(_ind_active_status)s)"
)


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
                "final_status", "visit_count", "last_visited_at",
                "login_phone", "can_id", "source_docname"],
    )
    beneficiaries = _filter_active_beneficiaries(beneficiaries)

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

    # Beneficiaries blocked from Pool 3 by a pending AC review
    pending_ac_names = set(frappe.db.sql_list("""
        SELECT beneficiary FROM `tabGeneric AC Review`
        WHERE entitlement = %(e)s AND status = 'Pending AC Review'
    """, {"e": entitlement_code}))

    # Classify into buckets
    pool1, pool2, pool3_sla, pool3_idle, pool4 = [], [], [], [], []

    today_dt = getdate(today)
    for b in beneficiaries:
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
            # Skip Pool 3 if pending AC review — AC must clear/block first
            if b.name in pending_ac_names:
                continue
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
        "co_streets":       sorted(streets),
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
    doc_statuses_json=None,
):
    """
    Generic status save for any entitlement.

    doc_statuses_json: JSON dict {slot_key: value} for batch updates (preferred).
    doc_slot + new_status: legacy single-slot update (backward compat).
    final_status: update the final status (at container or individual level).
    """
    config = _load_config(entitlement_code)
    beneficiary = frappe.get_doc("Generic Beneficiary", beneficiary_id)
    valid_slots = {s["slot_key"] for s in config["slots"]}

    # Batch doc status update (preferred — one call per visit)
    if doc_statuses_json:
        ds = json.loads(doc_statuses_json) if isinstance(doc_statuses_json, str) else doc_statuses_json
        for slot_key, new_val in (ds or {}).items():
            if slot_key not in valid_slots:
                continue
            old_val = getattr(beneficiary, slot_key, "") or ""
            if old_val != new_val:
                setattr(beneficiary, slot_key, new_val)
                _log_status(
                    entitlement_code, beneficiary_id,
                    container_id or beneficiary.container,
                    slot_key, old_val, new_val, config,
                )

    # Single-slot update (legacy / backward compat)
    elif doc_slot and new_status is not None:
        if doc_slot not in valid_slots:
            frappe.throw(f"Invalid doc_slot '{doc_slot}' for {entitlement_code}")
        old_val = getattr(beneficiary, doc_slot, "") or ""
        if old_val != new_status:
            setattr(beneficiary, doc_slot, new_status)
            _log_status(
                entitlement_code, beneficiary_id,
                container_id or beneficiary.container,
                doc_slot, old_val, new_status, config,
            )

    if final_status is not None:
        # Enforce requires_unlock: block saving if docs aren't complete
        if final_status:
            fs_meta = next(
                (s for s in config["final_statuses"] if s["value"] == final_status),
                None,
            )
            if fs_meta and fs_meta.get("requires_unlock"):
                if not _is_unlocked(config, beneficiary):
                    missing = [
                        s["label"] for s in config["slots"]
                        if s["required_for_unlock"]
                        and (getattr(beneficiary, s["slot_key"], "") or "")
                        not in s["terminal_values"]
                    ]
                    frappe.throw(
                        f"Cannot set '{fs_meta['label']}' — complete these first: "
                        + ", ".join(missing)
                    )

        if config["final_status_at"] == "Household" and (container_id or beneficiary.container):
            cid = container_id or beneficiary.container
            container = frappe.get_doc("Generic Container", cid)
            old_final = container.final_status or ""
            if old_final != final_status:
                container.final_status = final_status
                container.save(ignore_permissions=True)
                _log_status(
                    entitlement_code, beneficiary_id, cid,
                    "final_status", old_final, final_status, config,
                )
        else:
            old_final = beneficiary.final_status or ""
            if old_final != final_status:
                beneficiary.final_status = final_status
                _log_status(
                    entitlement_code, beneficiary_id,
                    container_id or beneficiary.container,
                    "final_status", old_final, final_status, config,
                )

    if notes is not None:
        beneficiary.notes = notes

    # Same-day dedupe: only increment visit_count if this is the first visit today.
    # Multiple updates to the same beneficiary on the same day count as one visit.
    today = getdate(nowdate())
    last_visit_date = getdate(beneficiary.last_visited_at) if beneficiary.last_visited_at else None
    if last_visit_date != today:
        new_visit_count = int(beneficiary.visit_count or 0) + 1
        beneficiary.visit_count = new_visit_count
    else:
        new_visit_count = int(beneficiary.visit_count or 0)
    beneficiary.last_visited_at = now_datetime()
    beneficiary.save(ignore_permissions=True)

    co_id = beneficiary.assigned_co
    if co_id:
        frappe.cache().delete_value(
            f"generic_workplan:{entitlement_code}:{co_id}:{getdate(nowdate())}"
        )

    # Auto-escalate to AC review at 3 visits if still in docs_in_progress
    try:
        cf = ""
        if config["final_status_at"] == "Household" and beneficiary.container:
            cf = frappe.db.get_value("Generic Container", beneficiary.container, "final_status") or ""
        new_bucket = _bucket(config, beneficiary, cf)
        from changemakers.generic_dashboard_api import maybe_escalate_for_ac_review
        maybe_escalate_for_ac_review(entitlement_code, beneficiary_id, new_visit_count, new_bucket)
    except Exception:
        frappe.log_error(frappe.get_traceback(), "save_beneficiary_status: ac_review escalation")

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
    Returns bucket counts, saturation %, coverage %, drilldown lists,
    and pending_actions (slot-combination groups for actionable work).
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
        return {"buckets": {}, "total": 0, "saturation_pct": 0,
                "pending_actions": [], "slot_info": []}

    beneficiaries = frappe.get_all(
        "Generic Beneficiary",
        filters={"entitlement": entitlement_code, "street": ["in", streets]},
        fields=["name", "beneficiary_name", "container", "street",
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

    def _fmt(b):
        return {
            "name":             b.name,
            "beneficiary_name": b.beneficiary_name or "",
            "street":           b.street or "",
            "last_visited_at":  str(b.last_visited_at) if b.last_visited_at else "",
            "visit_count":      int(b.visit_count or 0),
            "final_status":     b.final_status or "",
        }

    # Single-pass bucket classification
    buckets = defaultdict(list)
    bene_bucket_map = {}
    for b in beneficiaries:
        cf = container_finals.get(b.container, "") if b.container else ""
        bkt = _bucket(config, frappe._dict(b), cf)
        bene_bucket_map[b.name] = bkt
        buckets[bkt].append(_fmt(b))

    total         = len(beneficiaries)
    goal_count    = len(buckets.get("goal", []))
    visited_count = sum(1 for b in beneficiaries if int(b.visit_count or 0) > 0)
    saturation_pct = round(goal_count   / total * 100, 1) if total else 0
    coverage_pct   = round(visited_count / total * 100, 1) if total else 0

    # ── Pending actions ────────────────────────────────────────────────────────
    required_slots = [s for s in config["slots"] if s["required_for_unlock"]]
    slot_label_lkp = {s["slot_key"]: s["label"] for s in required_slots}
    n_required     = len(required_slots)

    def _needs_attention(b, slot):
        val = getattr(b, slot["slot_key"], None) or "not_checked"
        return val not in slot["terminal_values"]

    pending_actions = []

    # 1. Reach gap — active but never visited
    reach_gap = [
        _fmt(b) for b in beneficiaries
        if int(b.visit_count or 0) == 0
        and bene_bucket_map.get(b.name) not in ("goal", "negative")
    ]
    if reach_gap:
        pending_actions.append({
            "key": "reach_gap", "label": "Never Visited",
            "color": "red", "count": len(reach_gap), "items": reach_gap,
        })

    # 2. SLA overdue — any slot past its SLA deadline
    sla_overdue = [_fmt(b) for b in beneficiaries if _sla_overdue_days(config, b) > 0]
    if sla_overdue:
        pending_actions.append({
            "key": "sla_overdue", "label": "SLA Overdue",
            "color": "orange", "count": len(sla_overdue), "items": sla_overdue,
        })

    # 3. Per-slot-combination groups (docs_in_progress only)
    combo_groups = defaultdict(list)
    for b in beneficiaries:
        if bene_bucket_map.get(b.name) == "docs_in_progress":
            combo = tuple(
                slot["slot_key"] for slot in required_slots
                if _needs_attention(b, slot)
            )
            if combo:
                combo_groups[combo].append(_fmt(b))

    # Sort: all-docs groups first, then pairs, then singles
    for combo, blist in sorted(combo_groups.items(), key=lambda x: -len(x[0])):
        labels = [slot_label_lkp.get(k, k) for k in combo]
        if len(labels) == n_required:
            label = "Needs All Documents"
        elif len(labels) == 1:
            label = f"Needs {labels[0]} Only"
        else:
            label = "Needs " + " + ".join(labels)
        color = "purple" if len(combo) > 1 else "blue"
        pending_actions.append({
            "key": "__".join(combo), "label": label,
            "color": color, "count": len(blist), "items": blist,
        })

    # 4. Docs ready — all docs done, not yet applied
    docs_ready_items = buckets.get("docs_ready", [])
    if docs_ready_items:
        pending_actions.append({
            "key": "docs_ready_apply", "label": "Docs Ready — Apply Now!",
            "color": "green", "count": len(docs_ready_items), "items": docs_ready_items,
        })

    slot_info = [{"key": s["slot_key"], "label": s["label"]} for s in config["slots"]]
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
        "pending_actions":   pending_actions,
        "slot_info":         slot_info,
        "goal_label":        config["final_status_label"],
    }


@frappe.whitelist()
def get_beneficiary_detail(beneficiary_id):
    """Full beneficiary profile for the detail screen (includes identity and address fields)."""
    b = frappe.get_doc("Generic Beneficiary", beneficiary_id)

    # Resolve address and registered phone via source_docname → Individual → Household
    address = ""
    individual_phone = ""
    hhid = ""
    if b.source_docname:
        try:
            ind = frappe.db.get_value(
                "Individual Profile-WRP",
                b.source_docname,
                ["hhid", "contact_number", "phone"],
                as_dict=True,
            )
            if ind:
                individual_phone = ind.contact_number or ind.phone or ""
                hhid = ind.hhid or ""
                if ind.hhid:
                    address = frappe.db.get_value(
                        "Household Profile-WRP", ind.hhid, "address"
                    ) or ""
        except Exception:
            pass

    return {
        "name":               b.name,
        "beneficiary_name":   b.beneficiary_name or "",
        "street":             b.street or "",
        "address":            address,
        "individual_phone":   individual_phone,
        "source_docname":     b.source_docname or "",
        "hhid":               hhid,
        "date_of_birth":      str(b.date_of_birth) if b.date_of_birth else "",
        "can_id":             b.can_id or "",
        "login_phone":        b.login_phone or "",
        "esm_login_id":       b.esm_login_id or "",
        "ration_card_number": b.ration_card_number or "",
        "notes":              b.notes or "",
        "visit_count":        int(b.visit_count or 0),
        "last_visited_at":    str(b.last_visited_at) if b.last_visited_at else "",
        "doc1_status":        b.doc1_status or "",
        "doc2_status":        b.doc2_status or "",
        "doc3_status":        b.doc3_status or "",
        "doc4_status":        b.doc4_status or "",
        "final_status":       b.final_status or "",
        "container":          b.container or "",
        "entitlement":        b.entitlement or "",
    }


@frappe.whitelist()
def get_entitlement_history(entitlement_code, co_id=None):
    """
    All visited beneficiaries for this entitlement/CO, sorted by last visit descending.
    Used by the history screen.
    """
    if not co_id:
        co_id = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "name"
        )
    if not co_id:
        return {"history": []}

    streets = frappe.get_all(
        "Street List  - WRP", filters={"added_by_co": co_id}, pluck="name"
    )
    if not streets:
        return {"history": []}

    config = _load_config(entitlement_code)
    final_label_map = {s["value"]: s["label"] for s in config["final_statuses"]}

    rows = frappe.get_all(
        "Generic Beneficiary",
        filters={
            "entitlement": entitlement_code,
            "street":      ["in", streets],
            "visit_count": [">", 0],
        },
        fields=["name", "beneficiary_name", "street", "last_visited_at",
                "visit_count", "final_status", "notes", "source_docname"],
        order_by="last_visited_at desc",
        limit=300,
    )
    rows = _filter_active_beneficiaries(rows)

    return {
        "history": [
            {
                "name":             b.name,
                "beneficiary_name": b.beneficiary_name or "",
                "street":           b.street or "",
                "last_visited_at":  str(b.last_visited_at) if b.last_visited_at else "",
                "visit_count":      int(b.visit_count or 0),
                "final_status":     b.final_status or "",
                "final_label":      final_label_map.get(b.final_status or "", ""),
                "notes":            b.notes or "",
            }
            for b in rows
        ]
    }


@frappe.whitelist()
def get_beneficiary_attachments(beneficiary_id):
    """Returns the unified document vault for this beneficiary's individual,
    plus any legacy attachments still pinned directly to the Generic Beneficiary.

    A single CO should never need to re-collect a document already gathered
    for another scheme — Aadhaar, ration card, bank statement, etc. all live
    on Individual Profile-WRP.document_vault and are shared across CMCHIS,
    OAP, and any future entitlements.
    """
    individual_id = frappe.db.get_value(
        "Generic Beneficiary", beneficiary_id, "source_docname"
    )

    out = []

    if individual_id and frappe.db.exists("Individual Profile-WRP", individual_id):
        vault_rows = frappe.get_all(
            "Document Vault Item",
            filters={
                "parent": individual_id,
                "parenttype": "Individual Profile-WRP",
            },
            fields=["name", "category", "file_name", "file_path", "creation"],
            order_by="creation desc",
        )
        for v in vault_rows:
            out.append({
                "name":      v.name,
                "file_name": v.file_name or "",
                "file_url":  v.file_path or "",
                "category":  v.category or "",
                "creation":  str(v.creation) if v.creation else "",
                "source":    "vault",
            })

    # Legacy attachments uploaded before the vault unification
    legacy = frappe.get_all(
        "File",
        filters={
            "attached_to_doctype": "Generic Beneficiary",
            "attached_to_name":    beneficiary_id,
        },
        fields=["name", "file_name", "file_url", "file_size", "creation"],
        order_by="creation desc",
    )
    for f in legacy:
        out.append({
            "name":      f.name,
            "file_name": f.file_name or "",
            "file_url":  f.file_url or "",
            "category":  "",
            "creation":  str(f.creation) if f.creation else "",
            "source":    "legacy",
        })

    return {
        "attachments": out,
        "individual":  individual_id or "",
    }


@frappe.whitelist()
def delete_beneficiary_attachment(file_doc_name, beneficiary_id=None, source="legacy"):
    """Delete an attachment.
    source='vault' removes the Document Vault Item from Individual Profile-WRP;
    source='legacy' (default for backward compat) deletes the File row directly.
    """
    if source == "vault" and beneficiary_id:
        individual_id = frappe.db.get_value(
            "Generic Beneficiary", beneficiary_id, "source_docname"
        )
        if not individual_id:
            frappe.throw("Cannot resolve individual for vault delete")
        ind = frappe.get_doc("Individual Profile-WRP", individual_id)
        before = len(ind.document_vault or [])
        ind.document_vault = [
            v for v in (ind.document_vault or []) if v.name != file_doc_name
        ]
        if len(ind.document_vault) == before:
            frappe.throw("Vault item not found")
        ind.save(ignore_permissions=True)
        return {"status": "ok", "source": "vault"}

    frappe.delete_doc("File", file_doc_name, ignore_permissions=True)
    return {"status": "ok", "source": "legacy"}


@frappe.whitelist()
def upload_beneficiary_file(beneficiary_id, file_name, file_data, doc_category=None):
    """Accepts a base64-encoded file and stores it in the unified document vault
    on Individual Profile-WRP (shared across CMCHIS, OAP, and future schemes).

    Falls back to attaching directly to the Generic Beneficiary if no source
    individual is set (legacy / orphan beneficiaries).

    doc_category: optional label (e.g. 'Aadhaar', 'Ration Card', 'Bank Statement').
    """
    import base64
    raw = base64.b64decode(file_data)

    individual_id = frappe.db.get_value(
        "Generic Beneficiary", beneficiary_id, "source_docname"
    )

    if individual_id and frappe.db.exists("Individual Profile-WRP", individual_id):
        # Unified path: file attaches to the individual, vault entry tags the category
        file_doc = frappe.get_doc({
            "doctype": "File",
            "file_name": file_name,
            "content": raw,
            "is_private": 1,
            "attached_to_doctype": "Individual Profile-WRP",
            "attached_to_name":    individual_id,
        })
        file_doc.save(ignore_permissions=True)

        ind = frappe.get_doc("Individual Profile-WRP", individual_id)
        ind.append("document_vault", {
            "category":  doc_category or "Uncategorized",
            "file_name": file_name,
            "file_path": file_doc.file_url,
        })
        ind.save(ignore_permissions=True)
        frappe.db.commit()
        return {
            "file_url":   file_doc.file_url,
            "file_name":  file_doc.file_name,
            "individual": individual_id,
            "source":     "vault",
        }

    # Legacy fallback: no source individual → keep on Generic Beneficiary
    file_doc = frappe.get_doc({
        "doctype": "File",
        "file_name": file_name,
        "content": raw,
        "is_private": 1,
        "attached_to_doctype": "Generic Beneficiary",
        "attached_to_name": beneficiary_id,
    })
    file_doc.save(ignore_permissions=True)
    frappe.db.commit()
    return {
        "file_url":  file_doc.file_url,
        "file_name": file_doc.file_name,
        "source":    "legacy",
    }


@frappe.whitelist()
def update_beneficiary_profile(
    beneficiary_id,
    login_phone=None,
    can_id=None,
    esm_login_id=None,
    ration_card_number=None,
):
    """Update identity fields without incrementing visit count."""
    b = frappe.get_doc("Generic Beneficiary", beneficiary_id)
    if login_phone is not None:
        b.login_phone = login_phone
    if can_id is not None:
        b.can_id = can_id
    if esm_login_id is not None:
        b.esm_login_id = esm_login_id
    if ration_card_number is not None:
        b.ration_card_number = ration_card_number
    b.save(ignore_permissions=True)
    return {"status": "ok"}
