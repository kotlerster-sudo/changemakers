import frappe
from frappe.utils import getdate, nowdate, add_days, add_months, date_diff


# ── Positive transition targets ───────────────────────────────────────────────

AADHAAR_POSITIVE  = {"Aadhaar Received"}
INCOME_POSITIVE   = {"Income Cert Received", "Income Cert Expired"}
CMCHIS_APPLIED    = {"CMCHIS Applied – ETA 5d"}
CMCHIS_ACTIVE     = {"CMCHIS Active"}
CMCHIS_REJECTED   = {"Rejected"}


def _user_org_filter():
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if not wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        return "", {}
    org = frappe.db.get_value(
        "Staff details - WRP", {"mail_id": frappe.session.user}, "organisation"
    )
    if not org:
        return None
    return " AND log.implementing_org = %(user_org)s", {"user_org": org}


def _date_range(filters):
    today = getdate(nowdate())
    period = filters.get("period") or "Last Month"
    if period == "Last Week":
        return str(add_days(today, -7)), str(today)
    if period == "Last Quarter":
        return str(add_months(today, -3)), str(today)
    if period == "Custom":
        return (
            str(getdate(filters.get("from_date") or add_months(today, -1))),
            str(getdate(filters.get("to_date") or today)),
        )
    # Last Month (default)
    return str(add_months(today, -1)), str(today)


# ── Columns ───────────────────────────────────────────────────────────────────

def execute(filters=None):
    filters = filters or {}
    group_by = filters.get("group_by") or "CO"
    columns = get_columns()
    data, chart = get_data_and_chart(filters, group_by)
    return columns, data, None, chart


def get_columns():
    return [
        {"fieldname": "label",           "label": "Group / Household",    "fieldtype": "Data",  "width": 230},
        {"fieldname": "eligible_hh",     "label": "Total HH",             "fieldtype": "Int",   "width": 90},
        {"fieldname": "total_hh",        "label": "HH Changed",           "fieldtype": "Int",   "width": 100},
        {"fieldname": "aadhaar_received","label": "Aadhaar Received",      "fieldtype": "Int",   "width": 130},
        {"fieldname": "income_received", "label": "Income Cert Ready",     "fieldtype": "Int",   "width": 130},
        {"fieldname": "cmchis_applied",  "label": "CMCHIS Applied",        "fieldtype": "Int",   "width": 120},
        {"fieldname": "cmchis_active",   "label": "CMCHIS Active",         "fieldtype": "Int",   "width": 110},
        {"fieldname": "rejected",        "label": "Rejected",              "fieldtype": "Int",   "width": 90},
        {"fieldname": "other_changes",   "label": "Other Changes",         "fieldtype": "Int",   "width": 110},
        {"fieldname": "sub_label",       "label": "HHID",                  "fieldtype": "Data",  "width": 150},
        {"fieldname": "detail",          "label": "Transition",            "fieldtype": "Data",  "width": 260},
        {"fieldname": "changed_on",      "label": "Date",                  "fieldtype": "Date",  "width": 100},
    ]


# ── Total eligible HH per group (denominator) ─────────────────────────────────

def _get_eligible_hh_totals(group_by, filters):
    """Return {group_key: total_eligible_hh} from the actual HH table."""
    cond = ""
    vals = {}

    if filters.get("intervention_unit"):
        cond += " AND sl.intervention_units = %(intervention_unit)s"
        vals["intervention_unit"] = filters["intervention_unit"]
    if filters.get("street"):
        cond += " AND sl.name = %(street)s"
        vals["street"] = filters["street"]

    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        org = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "organisation"
        )
        if org:
            cond += " AND sl.implementing_org = %(user_org)s"
            vals["user_org"] = org

    group_field = {
        "CO":               "sl.added_by_co",
        "AC":               "co_staff.ac_name",
        "Project Manager":  "co_staff.pm_name",
        "Intervention Unit":"sl.intervention_units",
        "Street":           "sl.name",
    }.get(group_by, "sl.implementing_org")

    rows = frappe.db.sql(
        """
        SELECT {gf} AS gkey, COUNT(DISTINCT hh.name) AS total_hh
        FROM `tabHousehold Profile-WRP` hh
        INNER JOIN `tabIndividual Profile-WRP` ind
            ON ind.hhid = hh.name AND ind.status = 'Active- ஆக்டிவ்'
        LEFT JOIN `tabStreet List  - WRP` sl ON sl.name = hh.street_name
        LEFT JOIN `tabStaff details - WRP` co_staff ON co_staff.name = sl.added_by_co
        WHERE hh.survay_status    = 'Occupied/உள்ளனர்'
          AND hh.availability_for = 'Going Ahead/துவங்கலாம்'
          {cond}
        GROUP BY {gf}
        """.format(gf=group_field, cond=cond),
        vals,
        as_dict=True,
    )
    return {r["gkey"]: r["total_hh"] for r in rows if r.get("gkey")}


# ── Data ──────────────────────────────────────────────────────────────────────

def get_data_and_chart(filters, group_by):
    from_date, to_date = _date_range(filters)

    cond = " AND DATE(log.changed_at) BETWEEN %(from_date)s AND %(to_date)s"
    vals = {"from_date": from_date, "to_date": to_date}

    field_filter = filters.get("field_changed")
    if field_filter and field_filter != "All":
        cond += " AND log.field_changed = %(field_changed)s"
        vals["field_changed"] = field_filter

    if filters.get("intervention_unit"):
        cond += " AND log.intervention_unit = %(intervention_unit)s"
        vals["intervention_unit"] = filters["intervention_unit"]

    if filters.get("street"):
        cond += " AND log.street_name = %(street)s"
        vals["street"] = filters["street"]

    org_filter = _user_org_filter()
    if org_filter is None:
        return [], None
    org_cond, org_vals = org_filter
    cond += org_cond
    vals.update(org_vals)

    rows = frappe.db.sql(
        """
        SELECT
            log.hh_name,
            log.hhid,
            log.field_changed,
            log.old_value,
            log.new_value,
            DATE(log.changed_at)  AS changed_date,
            log.co_id,
            log.co_name,
            log.ac_name,
            log.pm_name,
            log.street_name,
            log.intervention_unit,
            log.implementing_org
        FROM `tabWRP Status Log` log
        WHERE 1=1 {cond}
        ORDER BY log.hh_name, log.changed_at
        """.format(cond=cond),
        vals,
        as_dict=True,
    )

    if not rows:
        return [], None

    eligible_totals = _get_eligible_hh_totals(group_by, filters)

    def _group_key(r):
        if group_by == "CO":
            return r.get("co_id") or "Unknown", r.get("co_name") or "Unknown"
        if group_by == "AC":
            v = r.get("ac_name") or "Unknown"
            return v, v
        if group_by == "Project Manager":
            v = r.get("pm_name") or "Unknown"
            return v, v
        if group_by == "Intervention Unit":
            v = r.get("intervention_unit") or "Unknown"
            return v, v
        if group_by == "Street":
            v = r.get("street_name") or "Unknown"
            return v, v
        v = r.get("implementing_org") or "Unknown"
        return v, v

    def _classify(r):
        field = r.get("field_changed")
        new   = r.get("new_value") or ""
        if field == "aadhaar_status" and new in AADHAAR_POSITIVE:
            return "aadhaar_received"
        if field == "income_status" and new in INCOME_POSITIVE:
            return "income_received"
        if field == "cmchis_status" and new in CMCHIS_APPLIED:
            return "cmchis_applied"
        if field == "cmchis_status" and new in CMCHIS_ACTIVE:
            return "cmchis_active"
        if field == "cmchis_status" and new in CMCHIS_REJECTED:
            return "rejected"
        return "other_changes"

    # ── Aggregate ─────────────────────────────────────────────────────────────
    groups      = {}
    group_order = []

    # For chart: weekly buckets → transition type → count
    chart_buckets = {}  # week_label → {transition: count}

    for r in rows:
        gkey, glabel = _group_key(r)
        cat = _classify(r)

        if gkey not in groups:
            groups[gkey] = {
                "label":           glabel,
                "hh_set":          set(),
                "aadhaar_received":0,
                "income_received": 0,
                "cmchis_applied":  0,
                "cmchis_active":   0,
                "rejected":        0,
                "other_changes":   0,
                "transitions":     [],
            }
            group_order.append(gkey)

        g = groups[gkey]
        g["hh_set"].add(r.get("hh_name"))
        g[cat] += 1

        old_v = r.get("old_value") or "—"
        new_v = r.get("new_value") or "—"
        field_label = {
            "aadhaar_status": "Aadhaar",
            "income_status":  "Income",
            "cmchis_status":  "CMCHIS",
        }.get(r.get("field_changed"), r.get("field_changed"))

        g["transitions"].append({
            "hh_name":    r.get("hh_name") or "",
            "hhid":       r.get("hhid") or "",
            "detail":     f"{field_label}: {old_v} → {new_v}",
            "changed_on": str(r.get("changed_date") or ""),
            "cat":        cat,
        })

        # Weekly bucket for chart
        cd = r.get("changed_date")
        if cd:
            d = getdate(str(cd))
            wlabel = f"{d.year}-W{d.isocalendar()[1]:02d}"
            if wlabel not in chart_buckets:
                chart_buckets[wlabel] = {
                    "aadhaar_received": 0,
                    "income_received":  0,
                    "cmchis_applied":   0,
                    "cmchis_active":    0,
                }
            if cat in chart_buckets[wlabel]:
                chart_buckets[wlabel][cat] += 1

    # ── Sort groups: most active first ────────────────────────────────────────
    group_order.sort(key=lambda k: -(
        groups[k]["aadhaar_received"] +
        groups[k]["income_received"] +
        groups[k]["cmchis_applied"] +
        groups[k]["cmchis_active"]
    ))

    CAT_ORDER = ["aadhaar_received", "income_received",
                 "cmchis_applied", "cmchis_active", "rejected", "other_changes"]
    EMPTY = {
        "eligible_hh": "", "total_hh": "", "aadhaar_received": "", "income_received": "",
        "cmchis_applied": "", "cmchis_active": "", "rejected": "",
        "other_changes": "",
    }

    data = []
    for gkey in group_order:
        g = groups[gkey]
        data.append({
            "label":           g["label"],
            "eligible_hh":     eligible_totals.get(gkey) or "",
            "total_hh":        len(g["hh_set"]),
            "aadhaar_received":g["aadhaar_received"],
            "income_received": g["income_received"],
            "cmchis_applied":  g["cmchis_applied"],
            "cmchis_active":   g["cmchis_active"],
            "rejected":        g["rejected"],
            "other_changes":   g["other_changes"],
            "sub_label":       "",
            "detail":          "",
            "changed_on":      "",
            "indent":          0,
            "bold":            1,
        })

        sorted_t = sorted(g["transitions"], key=lambda x: (CAT_ORDER.index(x["cat"]), x["changed_on"]))
        for t in sorted_t:
            row = dict(EMPTY)
            row.update({
                "label":      t["hh_name"],
                "sub_label":  t["hhid"],
                "detail":     t["detail"],
                "changed_on": t["changed_on"],
                "indent":     1,
                "bold":       0,
            })
            data.append(row)

    # ── Chart ─────────────────────────────────────────────────────────────────
    chart = _build_chart(chart_buckets) if chart_buckets else None
    return data, chart


def _build_chart(chart_buckets):
    weeks = sorted(chart_buckets.keys())
    series_keys = [
        ("aadhaar_received", "Aadhaar Received",     "#36AE7C"),
        ("income_received",  "Income Cert Ready",    "#FFA500"),
        ("cmchis_applied",   "CMCHIS Applied",       "#4169E1"),
        ("cmchis_active",    "CMCHIS Active",        "#22C55E"),
    ]
    datasets = [
        {
            "name":   label,
            "values": [chart_buckets[w].get(key, 0) for w in weeks],
            "chartType": "line",
        }
        for key, label, _ in series_keys
    ]
    return {
        "data": {
            "labels":   weeks,
            "datasets": datasets,
        },
        "type":      "line",
        "fieldtype": "Int",
        "colors":    [c for _, _, c in series_keys],
        "title":     "Weekly Status Transitions",
        "axisOptions": {"xIsSeries": 1},
    }
