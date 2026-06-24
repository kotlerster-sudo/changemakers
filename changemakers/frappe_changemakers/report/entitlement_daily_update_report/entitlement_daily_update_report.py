"""
Entitlement Daily Update Report
--------------------------------
Per-CO daily count of beneficiaries updated, plus a drill row per beneficiary.
Generic across all entitlements (filter by entitlement_code).

Source of truth: Entitlement Status Log — each row is one productive status
change. Distinct beneficiary count per day gives the real "records updated"
metric MIS coordinators want.

Visit type:
  first     — visit_count == 1 (first ever visit to this beneficiary)
  follow_up — visit_count > 1

Transition columns show the highest-priority bucket move per beneficiary that day.
"""

import frappe
from frappe.utils import nowdate

DAILY_TARGET = 30

TRANS_PRIORITY = {
    "to_goal": 5, "to_applied": 4, "to_docs_ready": 3,
    "to_in_progress": 2, "to_closed": 1,
}
TRANS_COLS = ["to_in_progress", "to_docs_ready", "to_applied", "to_goal", "to_closed"]


def _classify_transition(old_b, new_b):
    if not old_b or not new_b or old_b == new_b:
        return None
    if new_b == "goal":
        return "to_goal"
    if new_b == "applied_pending":
        return "to_applied"
    if new_b == "docs_ready":
        return "to_docs_ready"
    if new_b == "docs_in_progress":
        return "to_in_progress"
    if new_b == "negative":
        return "to_closed"
    return None


def _user_org_scope():
    """If user is a WRP-PM/AC/MIS, restrict to their org. Returns None if no access."""
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if not wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        return "", {}
    org = frappe.db.get_value(
        "Staff details - WRP", {"mail_id": frappe.session.user}, "organisation"
    )
    if not org:
        return None
    return " AND sl.implementing_org = %(user_org)s", {"user_org": org}


def execute(filters=None):
    filters = filters or {}
    if not filters.get("date"):
        filters["date"] = nowdate()
    if not filters.get("entitlement_code"):
        frappe.throw("Entitlement is required")
    return get_columns(filters), get_data(filters)


def get_columns(filters=None):
    goal_label = "→ Goal"
    if filters and filters.get("entitlement_code"):
        lbl = frappe.db.get_value(
            "Entitlement Config", filters["entitlement_code"], "final_status_label"
        )
        if lbl:
            goal_label = "→ " + lbl

    return [
        {"fieldname": "label",          "label": "CO / Beneficiary",      "fieldtype": "Data",    "width": 240},
        {"fieldname": "street",         "label": "Street",                "fieldtype": "Data",    "width": 160},
        {"fieldname": "updated",        "label": "Beneficiaries Updated", "fieldtype": "Int",     "width": 170},
        {"fieldname": "target",         "label": "Target",                "fieldtype": "Int",     "width": 80},
        {"fieldname": "coverage_pct",   "label": "Coverage %",            "fieldtype": "Percent", "width": 110},
        {"fieldname": "first_visits",   "label": "First Visits",          "fieldtype": "Int",     "width": 110},
        {"fieldname": "follow_ups",     "label": "Follow-ups",            "fieldtype": "Int",     "width": 110},
        {"fieldname": "status_changes", "label": "Status Changes",        "fieldtype": "Int",     "width": 130},
        {"fieldname": "to_in_progress", "label": "→ In Progress",         "fieldtype": "Int",     "width": 110},
        {"fieldname": "to_docs_ready",  "label": "→ Docs Ready",          "fieldtype": "Int",     "width": 110},
        {"fieldname": "to_applied",     "label": "→ Applied",             "fieldtype": "Int",     "width": 90},
        {"fieldname": "to_goal",        "label": goal_label,              "fieldtype": "Int",     "width": 110},
        {"fieldname": "to_closed",      "label": "→ Closed",              "fieldtype": "Int",     "width": 90},
        {"fieldname": "bucket",         "label": "Current Bucket",        "fieldtype": "Data",    "width": 150},
        {"fieldname": "final_status",   "label": "Final Status",          "fieldtype": "Data",    "width": 160},
    ]


def get_data(filters):
    entitlement_code = filters["entitlement_code"]
    date_filter      = str(filters["date"])

    org_filter = _user_org_scope()
    if org_filter is None:
        return []
    org_cond, org_vals = org_filter

    co_cond = ""
    co_vals = {}
    if filters.get("co"):
        co_cond = " AND gb.assigned_co = %(co)s"
        co_vals["co"] = filters["co"]

    iu_cond = ""
    iu_vals = {}
    if filters.get("intervention_unit"):
        iu_cond = " AND sl.intervention_units = %(iu)s"
        iu_vals["iu"] = filters["intervention_unit"]

    street_cond = ""
    street_vals = {}
    if filters.get("street"):
        street_cond = " AND gb.street = %(street)s"
        street_vals["street"] = filters["street"]

    rows = frappe.db.sql(
        f"""
        SELECT
            gb.name              AS beneficiary,
            gb.beneficiary_name  AS beneficiary_name,
            gb.assigned_co       AS co_id,
            gb.street            AS street,
            gb.visit_count       AS visit_count,
            gb.final_status      AS final_status,
            staff.full_name      AS co_name,
            log.change_count     AS status_changes
        FROM `tabGeneric Beneficiary` gb
        INNER JOIN (
            SELECT beneficiary, COUNT(*) AS change_count
            FROM `tabEntitlement Status Log`
            WHERE entitlement = %(entitlement_code)s
              AND DATE(changed_at) = %(date)s
            GROUP BY beneficiary
        ) log ON log.beneficiary = gb.name
        LEFT JOIN `tabStreet List  - WRP` sl ON sl.name = gb.street
        LEFT JOIN `tabStaff details - WRP` staff ON staff.name = gb.assigned_co
        LEFT JOIN `tabIndividual Profile-WRP` ip ON ip.name = gb.source_docname
        WHERE gb.entitlement = %(entitlement_code)s
          AND (gb.source_docname IS NULL OR gb.source_docname = ''
               OR ip.status = 'Active- ஆக்டிவ்')
          {co_cond}
          {org_cond}
          {iu_cond}
          {street_cond}
        ORDER BY staff.full_name, gb.street, gb.beneficiary_name
        """,
        {
            "entitlement_code": entitlement_code,
            "date":             date_filter,
            **co_vals,
            **org_vals,
            **iu_vals,
            **street_vals,
        },
        as_dict=True,
    )

    if not rows:
        return []

    # Bucket label map
    BUCKET_LABELS = {
        "unvisited":        "Unvisited",
        "docs_in_progress": "In Progress",
        "docs_ready":       "Docs Ready",
        "applied_pending":  "Applied",
        "goal":             "Goal",
        "negative":         "Closed",
    }

    # Load config for bucket computation and final_status labels
    try:
        from changemakers.entitlement_api import _load_config, _bucket
        config = _load_config(entitlement_code)
    except Exception:
        config = None

    final_status_label_map = {}
    if config:
        for fs in config.get("final_statuses", []):
            final_status_label_map[fs["value"]] = fs["label"]

    # Fetch bucket transitions for today from Entitlement Status Log
    gb_ids = [r.beneficiary for r in rows]
    gb_transition = {}
    if gb_ids:
        trans_rows = frappe.get_all(
            "Entitlement Status Log",
            filters={
                "entitlement": entitlement_code,
                "beneficiary": ["in", gb_ids],
                "doc_slot":    "final_status",
                "changed_at":  ["between", [date_filter + " 00:00:00", date_filter + " 23:59:59"]],
            },
            fields=["beneficiary", "old_bucket", "new_bucket"],
        )
        for tr in trans_rows:
            if not tr.old_bucket:
                continue
            cat = _classify_transition(tr.old_bucket, tr.new_bucket)
            if not cat:
                continue
            gid = tr.beneficiary
            if gid not in gb_transition or \
                    TRANS_PRIORITY.get(cat, 0) > TRANS_PRIORITY.get(gb_transition[gid], 0):
                gb_transition[gid] = cat

    # Group by CO
    co_groups = {}
    co_order = []
    for r in rows:
        co_id = r.get("co_id") or "Unassigned"
        if co_id not in co_groups:
            co_groups[co_id] = {"co_name": r.get("co_name") or co_id, "records": []}
            co_order.append(co_id)

        is_first = int(r.get("visit_count") or 0) == 1
        bucket_key = ""
        if config:
            try:
                bucket_key = _bucket(config, frappe._dict(r), "")
            except Exception:
                bucket_key = ""

        co_groups[co_id]["records"].append({
            "name":           r.get("beneficiary"),
            "beneficiary":    r.get("beneficiary_name") or r.get("beneficiary"),
            "street":         r.get("street") or "",
            "status_changes": int(r.get("status_changes") or 0),
            "is_first":       is_first,
            "transition":     gb_transition.get(r.get("beneficiary")),
            "bucket":         BUCKET_LABELS.get(bucket_key, bucket_key),
            "final_status":   final_status_label_map.get(
                r.get("final_status") or "", r.get("final_status") or ""),
        })

    # Build output rows
    data = []
    for co_id in co_order:
        co     = co_groups[co_id]
        recs   = co["records"]
        total  = len(recs)
        first  = sum(1 for r in recs if r["is_first"])
        follow = total - first
        changes_total = sum(r["status_changes"] for r in recs)
        trans_counts = {c: sum(1 for r in recs if r["transition"] == c) for c in TRANS_COLS}

        data.append({
            "label":          co["co_name"],
            "street":         "",
            "updated":        total,
            "target":         DAILY_TARGET,
            "coverage_pct":   round(total / DAILY_TARGET * 100, 1),
            "first_visits":   first,
            "follow_ups":     follow,
            "status_changes": changes_total,
            "to_in_progress": trans_counts.get("to_in_progress") or "",
            "to_docs_ready":  trans_counts.get("to_docs_ready")  or "",
            "to_applied":     trans_counts.get("to_applied")     or "",
            "to_goal":        trans_counts.get("to_goal")        or "",
            "to_closed":      trans_counts.get("to_closed")      or "",
            "bucket":         "",
            "final_status":   "",
            "indent":         0,
            "bold":           1,
        })

        for r in recs:
            t = r["transition"]
            data.append({
                "label":          r["beneficiary"],
                "street":         r["street"],
                "updated":        "",
                "target":         "",
                "coverage_pct":   "",
                "first_visits":   1 if r["is_first"]     else "",
                "follow_ups":     1 if not r["is_first"] else "",
                "status_changes": r["status_changes"],
                "to_in_progress": 1 if t == "to_in_progress" else "",
                "to_docs_ready":  1 if t == "to_docs_ready"  else "",
                "to_applied":     1 if t == "to_applied"     else "",
                "to_goal":        1 if t == "to_goal"        else "",
                "to_closed":      1 if t == "to_closed"      else "",
                "bucket":         r["bucket"],
                "final_status":   r["final_status"],
                "indent":         1,
                "bold":           0,
            })

    return data
