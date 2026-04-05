import frappe


def _user_org_filter():
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if not wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        return "", {}
    org = frappe.db.get_value("Staff details - WRP", {"mail_id": frappe.session.user}, "organisation")
    if not org:
        return None
    return " AND sl.implementing_org = %(user_org)s", {"user_org": org}


# ── Pipeline bucket classification ───────────────────────────────────────────

def _bucket(visit_count, aadhaar_status, income_status, hh_cmchis):
    c = (hh_cmchis or "").lower()
    if "active" in c:
        return "active"
    if "rejected" in c:
        return "rejected"
    if "applied" in c and "not" not in c:
        return "applied"
    vc = int(visit_count or 0)
    if vc == 0:
        return "reach_gap"
    has_a = "Received" in (aadhaar_status or "")
    has_i = "Received" in (income_status or "")
    if has_a and has_i:
        return "documented"
    return "no_update"


def _doc_gap(visit_count, aadhaar_status, income_status, hh_cmchis):
    """Return doc-gap sub-bucket for visited individuals not yet in pipeline.
    Returns None for unvisited / applied / active / rejected."""
    c = (hh_cmchis or "").lower()
    if "active" in c or "rejected" in c:
        return None
    if "applied" in c and "not" not in c:
        return None
    if int(visit_count or 0) == 0:
        return None
    has_a = "Received" in (aadhaar_status or "")
    has_i = "Received" in (income_status or "")
    if has_a and has_i:
        return None          # documented / ready to apply — no gap
    if not has_a and not has_i:
        return "both_missing"
    if not has_a:
        return "no_aadhaar"  # has income, needs aadhaar
    return "no_income"       # has aadhaar, needs income cert


def _bucket_label(bucket):
    return {
        "reach_gap":  "Reach Gap (Unvisited)",
        "no_update":  "No Update (Pending Docs)",
        "documented": "Ready to Apply",
        "applied":    "Applied",
        "active":     "CMCHIS Active",
        "rejected":   "Rejected",
    }.get(bucket, bucket)


# ── Columns ───────────────────────────────────────────────────────────────────

def execute(filters=None):
    filters = filters or {}
    group_by = filters.get("group_by") or "CO"
    return get_columns(), get_data(filters, group_by)


def get_columns():
    return [
        {"fieldname": "label",        "label": "Group / Individual", "fieldtype": "Data",    "width": 230},
        {"fieldname": "total",        "label": "Total",              "fieldtype": "Int",     "width": 70},
        {"fieldname": "reach_gap",    "label": "Reach Gap",          "fieldtype": "Int",     "width": 95},
        {"fieldname": "no_update",    "label": "No Update",          "fieldtype": "Int",     "width": 90},
        {"fieldname": "both_missing", "label": "Both Docs Missing",  "fieldtype": "Int",     "width": 130},
        {"fieldname": "no_aadhaar",   "label": "Aadhaar Missing",    "fieldtype": "Int",     "width": 120},
        {"fieldname": "no_income",    "label": "Income Cert Missing","fieldtype": "Int",     "width": 135},
        {"fieldname": "documented",   "label": "Ready to Apply",     "fieldtype": "Int",     "width": 115},
        {"fieldname": "applied",      "label": "Applied",            "fieldtype": "Int",     "width": 80},
        {"fieldname": "active",       "label": "Active",             "fieldtype": "Int",     "width": 75},
        {"fieldname": "rejected",     "label": "Rejected",           "fieldtype": "Int",     "width": 80},
        {"fieldname": "pct_active",   "label": "% Active",           "fieldtype": "Percent", "width": 95},
        {"fieldname": "sub_label",    "label": "ID / Reference",     "fieldtype": "Data",    "width": 160},
        {"fieldname": "stage",        "label": "Stage",              "fieldtype": "Data",    "width": 190},
    ]


# ── Data ──────────────────────────────────────────────────────────────────────

def get_data(filters, group_by):
    cond = ""
    vals = {}

    if filters.get("street"):
        cond += " AND sl.name = %(street)s"
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
            ind.name                    AS ind_id,
            ind.ipid                    AS ind_ipid,
            ind.name_of_the_individual  AS ind_name,
            ind.visit_count,
            ind.aadhaar_status,
            ind.income_status,
            hh.hhid                     AS hh_hhid,
            hh.cmchis_status            AS hh_cmchis,
            hh.respondent               AS hh_respondent,
            sl.street_name              AS street_label,
            sl.added_by_co              AS co_id,
            sl.ac_alloted               AS ac_name,
            sl.implementing_org         AS street_org,
            sl.intervention_units       AS iu_id,
            iu.name_of_iu               AS iu_label,
            iu.implementing_org         AS iu_org,
            co_staff.full_name          AS co_name,
            pm_staff.full_name          AS pm_name
        FROM `tabIndividual Profile-WRP` ind
        INNER JOIN `tabHousehold Profile-WRP` hh
            ON hh.name = ind.hhid
           AND hh.survay_status    = 'Occupied/உள்ளனர்'
           AND hh.availability_for = 'Going Ahead/துவங்கலாம்'
        LEFT JOIN `tabStreet List  - WRP` sl
            ON sl.name = hh.street_name
        LEFT JOIN `tabIntervention Units-WRP` iu
            ON iu.name = sl.intervention_units
        LEFT JOIN `tabStaff details - WRP` co_staff
            ON co_staff.name = sl.added_by_co
        LEFT JOIN (
            SELECT organisation, MIN(full_name) AS full_name
            FROM `tabStaff details - WRP`
            WHERE desigination = 'Project Manager'
              AND current_employee_status != 'Inactive'
            GROUP BY organisation
        ) pm_staff ON pm_staff.organisation = iu.implementing_org
        WHERE ind.status = 'Active- ஆக்டிவ்'
              {cond}
        """.format(cond=cond),
        vals,
        as_dict=True,
    )

    if not rows:
        return []

    def _group_key(r):
        if group_by == "CO":
            return r.get("co_id") or "Unassigned", r.get("co_name") or "Unassigned"
        if group_by == "AC":
            v = r.get("ac_name") or "Unassigned"
            return v, v
        if group_by == "Project Manager":
            v = r.get("pm_name") or "Unassigned"
            return v, v
        if group_by == "Intervention Unit":
            return r.get("iu_id") or "Unknown", r.get("iu_label") or r.get("iu_id") or "Unknown"
        if group_by == "Street":
            return r.get("street_label") or "Unknown", r.get("street_label") or "Unknown"
        v = r.get("iu_org") or r.get("street_org") or "Unknown"
        return v, v

    groups = {}
    group_order = []

    for r in rows:
        gkey, glabel = _group_key(r)
        bucket = _bucket(r.visit_count, r.aadhaar_status, r.income_status, r.hh_cmchis)
        gap    = _doc_gap(r.visit_count, r.aadhaar_status, r.income_status, r.hh_cmchis)

        if gkey not in groups:
            groups[gkey] = {
                "label": glabel,
                "total": 0,
                "reach_gap": 0, "no_update": 0, "documented": 0,
                "applied": 0, "active": 0, "rejected": 0,
                "both_missing": 0, "no_aadhaar": 0, "no_income": 0,
                "individuals": [],
            }
            group_order.append(gkey)

        g = groups[gkey]
        g["total"] += 1
        g[bucket] += 1
        if gap:
            g[gap] += 1

        g["individuals"].append({
            "name":   r.get("ind_name") or r.get("hh_respondent") or str(r.get("ind_id")),
            "ipid":   r.get("ind_ipid") or str(r.get("ind_id")),
            "hhid":   r.get("hh_hhid") or "",
            "street": r.get("street_label") or "",
            "bucket": bucket,
            "gap":    gap,
        })

    group_order.sort(key=lambda k: -(groups[k]["active"] / max(groups[k]["total"], 1)))

    data = []
    for gkey in group_order:
        g = groups[gkey]
        total = g["total"] or 1
        pct = round(g["active"] / total * 100, 1)

        data.append({
            "label":        g["label"],
            "total":        g["total"],
            "reach_gap":    g["reach_gap"],
            "no_update":    g["no_update"],
            "both_missing": g["both_missing"],
            "no_aadhaar":   g["no_aadhaar"],
            "no_income":    g["no_income"],
            "documented":   g["documented"],
            "applied":      g["applied"],
            "active":       g["active"],
            "rejected":     g["rejected"],
            "pct_active":   pct,
            "sub_label":    "",
            "stage":        "",
            "indent":       0,
            "bold":         1,
        })

        bucket_order = ["reach_gap", "no_update", "documented", "applied", "active", "rejected"]
        sorted_inds = sorted(g["individuals"], key=lambda x: bucket_order.index(x["bucket"]))

        for ind in sorted_inds:
            # Stage label: for no_update rows show the doc gap detail
            if ind["bucket"] == "no_update" and ind["gap"]:
                stage_str = {
                    "both_missing": "Both Docs Missing",
                    "no_aadhaar":   "Aadhaar Missing",
                    "no_income":    "Income Cert Missing",
                }.get(ind["gap"], _bucket_label(ind["bucket"]))
            else:
                stage_str = _bucket_label(ind["bucket"])

            data.append({
                "label":        ind["name"],
                "total":        "",
                "reach_gap":    "",
                "no_update":    "",
                "both_missing": "",
                "no_aadhaar":   "",
                "no_income":    "",
                "documented":   "",
                "applied":      "",
                "active":       "",
                "rejected":     "",
                "pct_active":   "",
                "sub_label":    ind["ipid"] or ind["hhid"] or "",
                "stage":        stage_str,
                "indent":       1,
                "bold":         0,
            })

    return data
