"""
Entitlement Daily Update Report
--------------------------------
Per-CO daily count of beneficiaries updated, plus a drill row per beneficiary.
Generic across all entitlements (filter by entitlement_code).

Source of truth: Entitlement Status Log — each row is one productive status
change. Distinct beneficiary count per day gives the real "records updated"
metric MIS coordinators want.

Visit type categorisation:
  first       — beneficiary's first-ever update was today (visit_count became 1)
  follow_up   — beneficiary already had prior visits before today
"""

import frappe
from frappe.utils import nowdate

DAILY_TARGET = 30


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
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"fieldname": "label",         "label": "CO / Beneficiary",  "fieldtype": "Data",    "width": 240},
        {"fieldname": "street",        "label": "Street",            "fieldtype": "Data",    "width": 160},
        {"fieldname": "updated",       "label": "Beneficiaries Updated", "fieldtype": "Int", "width": 170},
        {"fieldname": "target",        "label": "Target",            "fieldtype": "Int",     "width": 80},
        {"fieldname": "coverage_pct",  "label": "Coverage %",        "fieldtype": "Percent", "width": 110},
        {"fieldname": "first_visits",  "label": "First Visits",      "fieldtype": "Int",     "width": 110},
        {"fieldname": "follow_ups",    "label": "Follow-ups",        "fieldtype": "Int",     "width": 110},
        {"fieldname": "status_changes","label": "Status Changes",    "fieldtype": "Int",     "width": 130},
        {"fieldname": "bucket",        "label": "Current Bucket",    "fieldtype": "Data",    "width": 150},
        {"fieldname": "final_status",  "label": "Final Status",      "fieldtype": "Data",    "width": 160},
    ]


def get_data(filters):
    entitlement_code = filters["entitlement_code"]
    date_filter      = filters["date"]

    org_filter = _user_org_scope()
    if org_filter is None:
        return []
    org_cond, org_vals = org_filter

    # Find beneficiaries with at least one Entitlement Status Log entry on this date.
    # Group by beneficiary to count status changes per record.
    co_cond = ""
    co_vals = {}
    if filters.get("co"):
        co_cond = " AND gb.assigned_co = %(co)s"
        co_vals["co"] = filters["co"]

    rows = frappe.db.sql(
        f"""
        SELECT
            gb.name              AS beneficiary,
            gb.beneficiary_name  AS beneficiary_name,
            gb.assigned_co       AS co_id,
            gb.street            AS street,
            gb.visit_count       AS visit_count,
            gb.last_visited_at   AS last_visited_at,
            gb.final_status      AS final_status,
            staff.full_name      AS co_name,
            sl.implementing_org  AS implementing_org,
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
        ORDER BY staff.full_name, gb.street, gb.beneficiary_name
        """,
        {
            "entitlement_code": entitlement_code,
            "date": date_filter,
            **co_vals,
            **org_vals,
        },
        as_dict=True,
    )

    if not rows:
        return []

    # Load entitlement config once for bucket labelling
    try:
        from changemakers.entitlement_api import _load_config, _bucket
        config = _load_config(entitlement_code)
    except Exception:
        config = None

    BUCKET_LABELS = {
        "unvisited": "Unvisited",
        "docs_in_progress": "In Progress",
        "docs_ready": "Docs Ready",
        "applied_pending": "Applied",
        "goal": "Goal",
        "negative": "Closed",
    }

    final_status_label_map = {}
    if config:
        for fs in config.get("final_statuses", []):
            final_status_label_map[fs["value"]] = fs["label"]

    # Group by CO
    co_groups = {}
    co_order = []
    for r in rows:
        co_id = r.get("co_id") or "Unassigned"
        if co_id not in co_groups:
            co_groups[co_id] = {
                "co_name": r.get("co_name") or co_id,
                "records": [],
            }
            co_order.append(co_id)

        # First visit = the only visit so far is today (visit_count == 1).
        # Follow-up = had prior visits before today.
        is_first = int(r.get("visit_count") or 0) == 1
        bucket = ""
        if config:
            try:
                bucket = _bucket(config, frappe._dict(r), "")
            except Exception:
                bucket = ""

        co_groups[co_id]["records"].append({
            "name":           r.get("beneficiary"),
            "beneficiary":    r.get("beneficiary_name") or r.get("beneficiary"),
            "street":         r.get("street") or "",
            "status_changes": int(r.get("status_changes") or 0),
            "is_first":       is_first,
            "bucket":         BUCKET_LABELS.get(bucket, bucket),
            "final_status":   final_status_label_map.get(
                r.get("final_status") or "", r.get("final_status") or ""),
        })

    # Build output: CO summary row + drill-in beneficiary rows
    data = []
    for co_id in co_order:
        co     = co_groups[co_id]
        recs   = co["records"]
        total  = len(recs)
        first  = sum(1 for r in recs if r["is_first"])
        follow = total - first
        changes_total = sum(r["status_changes"] for r in recs)

        data.append({
            "label":          co["co_name"],
            "street":         "",
            "updated":        total,
            "target":         DAILY_TARGET,
            "coverage_pct":   round(total / DAILY_TARGET * 100, 1),
            "first_visits":   first,
            "follow_ups":     follow,
            "status_changes": changes_total,
            "bucket":         "",
            "final_status":   "",
            "indent":         0,
            "bold":           1,
        })

        for r in recs:
            data.append({
                "label":          r["beneficiary"],
                "street":         r["street"],
                "updated":        "",
                "target":         "",
                "coverage_pct":   "",
                "first_visits":   1 if r["is_first"]      else "",
                "follow_ups":     1 if not r["is_first"]  else "",
                "status_changes": r["status_changes"],
                "bucket":         r["bucket"],
                "final_status":   r["final_status"],
                "indent":         1,
                "bold":           0,
            })

    return data
