"""
WRP Status Transitions
----------------------
Time-series view of how households move between pipeline buckets each day.

Pipeline buckets:
  unvisited → missing_both → missing_aadhaar / missing_income → docs_ready
  → applied → active  (or rejected at any stage)

Transition categories tracked:
  docs_completed  – any bucket → docs_ready          (both docs achieved)
  aadhaar_step    – missing_both → missing_income     (aadhaar done, income pending)
  income_step     – missing_both → missing_aadhaar    (income done, aadhaar pending)
  cmchis_applied  – docs_ready → applied
  cmchis_active   – applied → active
  rejected        – any → rejected
  no_change       – field changed but bucket unchanged
"""

import frappe
from frappe.utils import getdate, nowdate, add_days, add_months


def _date_range(filters):
    today  = getdate(nowdate())
    period = filters.get("period") or "Last Month"
    if period == "Last Week":
        return str(add_days(today, -7)), str(today)
    if period == "Last Quarter":
        return str(add_months(today, -3)), str(today)
    if period == "Custom":
        return (
            str(getdate(filters.get("from_date") or add_months(today, -1))),
            str(getdate(filters.get("to_date")   or today)),
        )
    return str(add_months(today, -1)), str(today)


def _classify(old_b, new_b):
    if not old_b or not new_b:
        return None   # pre-migration record without bucket data
    if new_b == "docs_ready" and old_b != "docs_ready":
        return "docs_completed"
    if new_b == "applied":
        return "cmchis_applied"
    if new_b == "active":
        return "cmchis_active"
    if new_b == "rejected":
        return "rejected"
    if new_b == "missing_income" and old_b in ("missing_both", "unvisited"):
        return "aadhaar_step"
    if new_b == "missing_aadhaar" and old_b in ("missing_both", "unvisited"):
        return "income_step"
    if old_b == new_b:
        return "no_change"
    return None   # other lateral moves — not shown


BUCKET_LABELS = {
    "unvisited":      "Unvisited",
    "missing_both":   "Missing Both",
    "missing_aadhaar":"Missing Aadhaar",
    "missing_income": "Missing Income",
    "docs_ready":     "Docs Ready",
    "applied":        "Applied",
    "active":         "Active",
    "rejected":       "Rejected",
}


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data, chart = get_data_and_chart(filters)
    return columns, data, None, chart


def get_columns():
    return [
        {"fieldname": "label",          "label": "Date / Household",    "fieldtype": "Data",  "width": 200},
        {"fieldname": "docs_completed", "label": "→ Docs Ready",        "fieldtype": "Int",   "width": 110},
        {"fieldname": "aadhaar_step",   "label": "Aadhaar Done (partial)","fieldtype": "Int", "width": 150},
        {"fieldname": "income_step",    "label": "Income Done (partial)","fieldtype": "Int",   "width": 150},
        {"fieldname": "cmchis_applied", "label": "→ Applied",           "fieldtype": "Int",   "width": 95},
        {"fieldname": "cmchis_active",  "label": "→ Active",            "fieldtype": "Int",   "width": 90},
        {"fieldname": "rejected",       "label": "→ Rejected",          "fieldtype": "Int",   "width": 95},
        {"fieldname": "no_change",      "label": "Field Changed (No Move)","fieldtype": "Int","width": 170},
        {"fieldname": "transition",     "label": "Transition",          "fieldtype": "Data",  "width": 260},
    ]


def get_data_and_chart(filters):
    from_date, to_date = _date_range(filters)

    cond = ""
    vals = {"from_date": from_date, "to_date": to_date}

    if filters.get("intervention_unit"):
        cond += " AND log.intervention_unit = %(intervention_unit)s"
        vals["intervention_unit"] = filters["intervention_unit"]
    if filters.get("street"):
        cond += " AND log.street_name = %(street)s"
        vals["street"] = filters["street"]
    if filters.get("co"):
        cond += " AND log.co_id = %(co)s"
        vals["co"] = filters["co"]

    # Org-level access control
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        org = frappe.db.get_value(
            "Staff details - WRP", {"mail_id": frappe.session.user}, "organisation"
        )
        if not org:
            return [], None
        cond += " AND log.implementing_org = %(user_org)s"
        vals["user_org"] = org

    rows = frappe.db.sql(
        """
        SELECT
            log.hh_name,
            log.hhid,
            log.field_changed,
            log.old_value,
            log.new_value,
            log.old_bucket,
            log.new_bucket,
            DATE(log.changed_at) AS changed_date,
            log.co_name,
            log.street_name,
            log.intervention_unit
        FROM `tabWRP Status Log` log
        WHERE log.old_bucket IS NOT NULL
          AND log.old_bucket != ''
          AND DATE(log.changed_at) BETWEEN %(from_date)s AND %(to_date)s
          {cond}
        ORDER BY log.changed_at DESC
        """.format(cond=cond),
        vals,
        as_dict=True,
    )

    if not rows:
        return [], None

    # ── Aggregate by date ─────────────────────────────────────────────────────
    CATS = ["docs_completed", "aadhaar_step", "income_step",
            "cmchis_applied", "cmchis_active", "rejected", "no_change"]

    def _empty():
        return {c: 0 for c in CATS}

    dates      = {}   # date_str → counter + sub-rows
    date_order = []

    for r in rows:
        cat = _classify(r.get("old_bucket"), r.get("new_bucket"))
        if cat is None:
            continue

        d = str(r.get("changed_date") or "")
        if d not in dates:
            dates[d]     = {"counts": _empty(), "hhs": []}
            date_order.append(d)

        dates[d]["counts"][cat] += 1

        old_label = BUCKET_LABELS.get(r.get("old_bucket"), r.get("old_bucket") or "—")
        new_label = BUCKET_LABELS.get(r.get("new_bucket"), r.get("new_bucket") or "—")
        field_label = {
            "aadhaar_status": "Aadhaar",
            "income_status":  "Income",
            "cmchis_status":  "CMCHIS",
        }.get(r.get("field_changed"), r.get("field_changed") or "")

        dates[d]["hhs"].append({
            "hh_name":   r.get("hh_name") or "",
            "hhid":      r.get("hhid") or "",
            "cat":       cat,
            "transition": f"{old_label} → {new_label}  [{field_label}: {r.get('old_value') or '—'} → {r.get('new_value') or '—'}]",
        })

    if not dates:
        return [], None

    # ── Build output rows ─────────────────────────────────────────────────────
    EMPTY_ROW = {c: "" for c in CATS}
    EMPTY_ROW["transition"] = ""

    data = []
    for d in date_order:
        cnt = dates[d]["counts"]
        data.append({
            "label":          d,
            "docs_completed": cnt["docs_completed"] or "",
            "aadhaar_step":   cnt["aadhaar_step"]   or "",
            "income_step":    cnt["income_step"]     or "",
            "cmchis_applied": cnt["cmchis_applied"]  or "",
            "cmchis_active":  cnt["cmchis_active"]   or "",
            "rejected":       cnt["rejected"]        or "",
            "no_change":      cnt["no_change"]       or "",
            "transition":     "",
            "indent":         0,
            "bold":           1,
        })

        for hh in dates[d]["hhs"]:
            row = dict(EMPTY_ROW)
            row.update({
                "label":      hh["hh_name"],
                "transition": hh["transition"],
                hh["cat"]:    1,
                "indent":     1,
                "bold":       0,
            })
            data.append(row)

    # ── Chart: daily bar chart of forward moves ───────────────────────────────
    chart = _build_chart(date_order, dates)
    return data, chart


def _build_chart(date_order, dates):
    # Show dates oldest→newest on x-axis
    labels = list(reversed(date_order))

    series = [
        ("docs_completed", "→ Docs Ready",         "#22C55E"),
        ("aadhaar_step",   "Aadhaar Done (partial)","#36AE7C"),
        ("income_step",    "Income Done (partial)", "#FFA500"),
        ("cmchis_applied", "→ Applied",             "#4169E1"),
        ("cmchis_active",  "→ Active",              "#7C3AED"),
        ("rejected",       "→ Rejected",            "#EF4444"),
    ]

    datasets = [
        {
            "name":   label,
            "values": [dates[d]["counts"].get(key, 0) for d in labels],
        }
        for key, label, _ in series
    ]

    return {
        "data": {"labels": labels, "datasets": datasets},
        "type":        "bar",
        "fieldtype":   "Int",
        "colors":      [c for _, _, c in series],
        "title":       "Daily Pipeline Movement",
        "axisOptions": {"xIsSeries": 1},
        "barOptions":  {"stacked": 0},
    }
