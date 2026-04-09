import frappe
from frappe.utils import getdate, date_diff, nowdate


def _user_org_filter():
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if not wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        return "", {}
    org = frappe.db.get_value("Staff details - WRP", {"mail_id": frappe.session.user}, "organisation")
    if not org:
        return None
    return " AND sl.implementing_org = %(user_org)s", {"user_org": org}


# ── Household closer check (same rule as pipeline dashboard) ─────────────────

AADHAAR_RECEIVED = "Aadhaar Received"
INCOME_READY = {"Income Cert Received", "Income Cert Expired"}


def _hh_closer(members):
    """True if any ONE member has both aadhaar received AND income ready."""
    for m in members:
        has_a = (m.get("aadhaar_status") or "") == AADHAAR_RECEIVED
        has_i = (m.get("income_status") or "") in INCOME_READY
        if has_a and has_i:
            return True
    return False


# ── Stage classification ──────────────────────────────────────────────────────

STAGE_UNVISITED  = "unvisited"
STAGE_PENDING    = "pending_docs"
STAGE_DOCS_READY = "docs_ready"
STAGE_APPLIED    = "applied"
STAGE_ACTIVE     = "active"
STAGE_REJECTED   = "rejected"


def _classify_hh(members, hh_cmchis):
    """Return (stage, days_at_stage) for a household."""
    today  = getdate(nowdate())
    c_stat = (hh_cmchis or "").lower()

    if "active" in c_stat:
        stage = STAGE_ACTIVE
    elif "rejected" in c_stat:
        stage = STAGE_REJECTED
    elif "applied" in c_stat and "not" not in c_stat:
        stage = STAGE_APPLIED
    else:
        max_visits = max(int(m.get("visit_count") or 0) for m in members)
        if max_visits == 0:
            stage = STAGE_UNVISITED
        elif _hh_closer(members):
            stage = STAGE_DOCS_READY
        else:
            stage = STAGE_PENDING

    # Days at stage
    if stage == STAGE_UNVISITED:
        # How long since the earliest member record was created
        creations = [m.get("creation") for m in members if m.get("creation")]
        ref = min(getdate(str(c)[:10]) for c in creations) if creations else today
    else:
        # How long since the most recent CO visit to any household member
        visits = [m.get("last_visited_at") for m in members if m.get("last_visited_at")]
        if visits:
            ref = max(getdate(str(v)[:10]) for v in visits)
        else:
            creations = [m.get("creation") for m in members if m.get("creation")]
            ref = min(getdate(str(c)[:10]) for c in creations) if creations else today

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
        {"fieldname": "group_label", "label": group_label, "fieldtype": "Data", "width": 200},
    ]
    if parent_label:
        cols.append({"fieldname": "parent_group", "label": parent_label, "fieldtype": "Data", "width": 150})
    cols += [
        {"fieldname": "total",              "label": "Total HH",            "fieldtype": "Int",   "width": 80},
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
    cond = ""
    vals = {}

    if filters.get("street"):
        cond += " AND hh.street_name = %(street)s"
        vals["street"] = filters["street"]

    if filters.get("intervention_unit"):
        cond += " AND sl.intervention_units = %(intervention_unit)s"
        vals["intervention_unit"] = filters["intervention_unit"]

    org_filter = _user_org_filter()
    if org_filter is None:
        return []
    org_cond, org_vals = org_filter
    cond += org_cond
    vals.update(org_vals)

    rows = frappe.db.sql(
        """
        SELECT
            ind.name              AS ind_name,
            ind.visit_count,
            ind.aadhaar_status,
            ind.income_status,
            ind.last_visited_at,
            ind.creation,
            hh.name               AS hh_name,
            hh.cmchis_status      AS hh_cmchis,
            hh.street_name        AS hh_street,
            sl.added_by_co        AS street_co_id,
            sl.implementing_org   AS street_org,
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

    # ── Step 1: group individuals by household (hh.name) ──────────────────────
    hh_map   = {}
    hh_order = []

    for r in rows:
        hh_key = r.get("hh_name") or r.get("ind_name")
        if hh_key not in hh_map:
            hh_map[hh_key] = {
                "hh_cmchis":   r.get("hh_cmchis") or "",
                "hh_street":   r.get("hh_street") or "",
                "street_co_id":r.get("street_co_id"),
                "street_org":  r.get("street_org"),
                "iu_name":     r.get("iu_name"),
                "iu_label":    r.get("iu_label"),
                "iu_org":      r.get("iu_org"),
                "street_label":r.get("street_label"),
                "co_name":     r.get("co_name"),
                "staff_org":   r.get("staff_org"),
                "members":     [],
            }
            hh_order.append(hh_key)
        hh_map[hh_key]["members"].append({
            "visit_count":    r.get("visit_count"),
            "aadhaar_status": r.get("aadhaar_status"),
            "income_status":  r.get("income_status"),
            "last_visited_at":r.get("last_visited_at"),
            "creation":       r.get("creation"),
        })

    # ── Step 2: classify each household and aggregate by group ────────────────
    def _key_label_parent(hh):
        if group_by == "CO":
            key    = hh.get("street_co_id") or "Unknown"
            label  = hh.get("co_name") or key
            parent = hh.get("iu_label") or hh.get("iu_name") or ""
        elif group_by == "Street":
            key    = hh.get("hh_street") or "Unknown"
            label  = hh.get("street_label") or key
            parent = hh.get("iu_label") or hh.get("iu_name") or ""
        elif group_by == "Intervention Unit":
            key    = hh.get("iu_name") or "Unknown"
            label  = hh.get("iu_label") or key
            parent = hh.get("iu_org") or hh.get("street_org") or hh.get("staff_org") or ""
        else:  # Implementing Org
            key    = hh.get("iu_org") or hh.get("street_org") or hh.get("staff_org") or "Unknown"
            label  = key
            parent = ""
        return key, label, parent

    groups = {}

    for hh_key in hh_order:
        hh = hh_map[hh_key]
        stage, days = _classify_hh(hh["members"], hh["hh_cmchis"])
        key, label, parent = _key_label_parent(hh)

        if key not in groups:
            groups[key] = {
                "group_label":  label,
                "parent_group": parent,
                "total":        0,
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
        g[stage]["n"] += 1
        if stage not in (STAGE_ACTIVE, STAGE_REJECTED):
            g[stage]["days"] += days
            if days > g["max_days_stuck"]:
                g["max_days_stuck"] = days

    def _avg(bucket):
        n = bucket["n"]
        return round(bucket["days"] / n, 1) if n else 0.0

    data = []
    for g in groups.values():
        data.append({
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
        })

    data.sort(key=lambda r: (-r["max_days_stuck"], r["group_label"] or ""))
    return data
