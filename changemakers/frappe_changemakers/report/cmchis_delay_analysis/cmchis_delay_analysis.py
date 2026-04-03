import frappe
from frappe.utils import getdate, date_diff, nowdate


# ── Stage classification ──────────────────────────────────────────────────────

STAGE_UNVISITED   = "unvisited"
STAGE_PENDING     = "pending_docs"
STAGE_DOCS_READY  = "docs_ready"
STAGE_APPLIED     = "applied"
STAGE_ACTIVE      = "active"
STAGE_REJECTED    = "rejected"


def _classify(ind, hh_cmchis):
    """Return (stage, days_at_stage) for a single individual row."""
    today        = getdate(nowdate())
    c_stat       = (hh_cmchis or "").lower()
    vc           = int(ind.get("visit_count") or 0)
    a_stat       = ind.get("aadhaar_status") or ""
    i_stat       = ind.get("income_status") or ""
    lv_raw       = ind.get("last_visited_at")
    created      = ind.get("creation")

    # Stage
    if "active" in c_stat:
        stage = STAGE_ACTIVE
    elif "rejected" in c_stat:
        stage = STAGE_REJECTED
    elif "applied" in c_stat and "not" not in c_stat:
        stage = STAGE_APPLIED
    elif vc == 0:
        stage = STAGE_UNVISITED
    elif "Received" in a_stat and "Received" in i_stat:
        stage = STAGE_DOCS_READY
    else:
        stage = STAGE_PENDING

    # Days at stage
    if stage == STAGE_UNVISITED:
        # Time since the record was created — how long this person has been waiting
        ref = getdate(str(created)[:10]) if created else today
    else:
        # Time since last CO visit — how long since the stage last moved
        if lv_raw:
            ref = getdate(str(lv_raw)[:10])
        elif created:
            ref = getdate(str(created)[:10])
        else:
            ref = today

    days = max(0, date_diff(today, ref))
    return stage, days


# ── Main query ────────────────────────────────────────────────────────────────

def execute(filters=None):
    filters  = filters or {}
    group_by = filters.get("group_by") or "CO"
    columns  = get_columns(group_by)
    data     = get_data(filters, group_by)
    return columns, data


def get_columns(group_by):
    group_label = {
        "CO":                "CO Name",
        "Street":            "Street",
        "Intervention Unit": "Intervention Unit",
        "Implementing Org":  "Implementing Org",
    }.get(group_by, "Group")

    parent_label = {
        "CO":                "Intervention Unit",
        "Street":            "Intervention Unit",
        "Intervention Unit": "Implementing Org",
        "Implementing Org":  "",
    }.get(group_by, "")

    cols = [
        {"fieldname": "group_label",        "label": group_label,   "fieldtype": "Data",  "width": 200},
    ]
    if parent_label:
        cols.append({"fieldname": "parent_group", "label": parent_label, "fieldtype": "Data", "width": 150})
    cols += [
        {"fieldname": "total",              "label": "Total",               "fieldtype": "Int",   "width": 70},
        {"fieldname": "unvisited",          "label": "Unvisited",           "fieldtype": "Int",   "width": 85},
        {"fieldname": "avg_days_unvisited", "label": "Avg Days (Unvisited)","fieldtype": "Float", "width": 150},
        {"fieldname": "pending_docs",       "label": "Pending Docs",        "fieldtype": "Int",   "width": 105},
        {"fieldname": "avg_days_pending",   "label": "Avg Days (Pending)",  "fieldtype": "Float", "width": 145},
        {"fieldname": "docs_ready",         "label": "Docs Ready",          "fieldtype": "Int",   "width": 95},
        {"fieldname": "avg_days_ready",     "label": "Avg Days (Ready)",    "fieldtype": "Float", "width": 135},
        {"fieldname": "applied",            "label": "Applied",             "fieldtype": "Int",   "width": 75},
        {"fieldname": "avg_days_applied",   "label": "Avg Days (Applied)",  "fieldtype": "Float", "width": 145},
        {"fieldname": "active",             "label": "Active",              "fieldtype": "Int",   "width": 70},
        {"fieldname": "rejected",           "label": "Rejected",            "fieldtype": "Int",   "width": 80},
        {"fieldname": "max_days_stuck",     "label": "Max Days Stuck",      "fieldtype": "Float", "width": 125},
    ]
    return cols


def get_data(filters, group_by):
    cond  = ""
    vals  = {}

    if filters.get("street"):
        cond += " AND hh.street_name = %(street)s"
        vals["street"] = filters["street"]

    if filters.get("intervention_unit"):
        cond += " AND sl.intervention_units = %(intervention_unit)s"
        vals["intervention_unit"] = filters["intervention_unit"]

    rows = frappe.db.sql(
        """
        SELECT
            ind.name              AS ind_name,
            ind.name_of_the_individual AS ind_display,
            ind.visit_count,
            ind.aadhaar_status,
            ind.income_status,
            ind.last_visited_at,
            ind.creation,
            sl.added_by_co        AS street_co_id,
            sl.implementing_org   AS street_org,
            hh.cmchis_status      AS hh_cmchis,
            hh.street_name        AS hh_street,
            sl.intervention_units AS iu_name,
            sl.street_name        AS street_label,
            iu.name_of_iu         AS iu_label,
            iu.implementing_org   AS iu_org,
            staff.full_name       AS co_name,
            staff.organisation    AS staff_org
        FROM `tabIndividual Profile-WRP` ind
        INNER JOIN `tabHousehold Profile-WRP` hh
            ON hh.name = ind.hhid
           AND hh.survay_status    = 'Occupied/உள்ளனர்'
           AND hh.availability_for = 'Going Ahead/துவங்கலாம்'
        LEFT JOIN `tabStreet List  - WRP` sl
            ON sl.name = hh.street_name
        LEFT JOIN `tabIntervention Units-WRP` iu
            ON iu.name = sl.intervention_units
        LEFT JOIN `tabStaff details - WRP` staff
            ON staff.name = sl.added_by_co
        WHERE ind.status = 'Active- ஆக்டிவ்'
              {cond}
        """.format(cond=cond),
        vals,
        as_dict=True,
    )

    if not rows:
        return []

    # Aggregate
    groups = {}   # key → { counters }

    def _key_parent(r):
        """Return (group_key, group_display, parent_display) for a row."""
        if group_by == "CO":
            key    = r.get("street_co_id") or "Unknown"
            label  = r.get("co_name") or key
            parent = r.get("iu_label") or r.get("iu_name") or ""
        elif group_by == "Street":
            key    = r.get("hh_street") or "Unknown"
            label  = r.get("street_label") or key
            parent = r.get("iu_label") or r.get("iu_name") or ""
        elif group_by == "Intervention Unit":
            key    = r.get("iu_name") or "Unknown"
            label  = r.get("iu_label") or key
            parent = r.get("iu_org") or r.get("street_org") or r.get("staff_org") or ""
        else:  # Implementing Org
            key    = (r.get("iu_org") or r.get("street_org") or r.get("staff_org") or "Unknown")
            label  = key
            parent = ""
        return key, label, parent

    for r in rows:
        key, label, parent = _key_parent(r)
        stage, days = _classify(r, r.get("hh_cmchis"))

        if key not in groups:
            groups[key] = {
                "group_label":  label,
                "parent_group": parent,
                "total":        0,
                # per-stage counters and day sums
                STAGE_UNVISITED:  {"n": 0, "days": 0},
                STAGE_PENDING:    {"n": 0, "days": 0},
                STAGE_DOCS_READY: {"n": 0, "days": 0},
                STAGE_APPLIED:    {"n": 0, "days": 0},
                STAGE_ACTIVE:     {"n": 0},
                STAGE_REJECTED:   {"n": 0},
                "max_days_stuck": 0,
            }

        g = groups[key]
        g["total"] += 1

        if stage in (STAGE_ACTIVE, STAGE_REJECTED):
            g[stage]["n"] += 1
        else:
            g[stage]["n"]    += 1
            g[stage]["days"] += days
            if days > g["max_days_stuck"]:
                g["max_days_stuck"] = days

    def _avg(bucket):
        n = bucket["n"]
        return round(bucket["days"] / n, 1) if n else 0.0

    data = []
    for g in groups.values():
        row = {
            "group_label":        g["group_label"],
            "parent_group":       g["parent_group"],
            "total":              g["total"],
            "unvisited":          g[STAGE_UNVISITED]["n"],
            "avg_days_unvisited": _avg(g[STAGE_UNVISITED]),
            "pending_docs":       g[STAGE_PENDING]["n"],
            "avg_days_pending":   _avg(g[STAGE_PENDING]),
            "docs_ready":         g[STAGE_DOCS_READY]["n"],
            "avg_days_ready":     _avg(g[STAGE_DOCS_READY]),
            "applied":            g[STAGE_APPLIED]["n"],
            "avg_days_applied":   _avg(g[STAGE_APPLIED]),
            "active":             g[STAGE_ACTIVE]["n"],
            "rejected":           g[STAGE_REJECTED]["n"],
            "max_days_stuck":     g["max_days_stuck"],
        }
        data.append(row)

    # Sort: most stuck first (max_days_stuck desc), then alphabetically
    data.sort(key=lambda r: (-r["max_days_stuck"], r["group_label"] or ""))
    return data
