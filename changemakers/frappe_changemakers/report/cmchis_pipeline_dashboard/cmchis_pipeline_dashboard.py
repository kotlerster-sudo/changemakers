import frappe


def _user_org_filter():
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if not wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        return "", {}
    org = frappe.db.get_value("Staff details - WRP", {"mail_id": frappe.session.user}, "organisation")
    if not org:
        return None
    return " AND sl.implementing_org = %(user_org)s", {"user_org": org}


# ── Household-level classification ───────────────────────────────────────────

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


def _hh_doc_gap(members):
    """
    For a visited household that is NOT a closer, return the doc gap:
    - If any member has Aadhaar Received → that member needs income cert → 'no_income'
    - Elif any member has income ready → that member needs aadhaar → 'no_aadhaar'
    - Else → 'both_missing'

    Edge case: Member A has aadhaar, Member B has income (different people, neither has both)
    → 'no_income' (actionable: get income for the aadhaar-holder)
    """
    any_aadhaar = any((m.get("aadhaar_status") or "") == AADHAAR_RECEIVED for m in members)
    any_income = any((m.get("income_status") or "") in INCOME_READY for m in members)
    if any_aadhaar:
        return "no_income"
    if any_income:
        return "no_aadhaar"
    return "both_missing"


def _hh_bucket(hh_cmchis, max_visits, members):
    c = (hh_cmchis or "").lower()
    if "active" in c:
        return "active"
    if "rejected" in c:
        return "rejected"
    if "applied" in c and "not" not in c:
        return "applied"
    if int(max_visits or 0) == 0:
        return "reach_gap"
    if _hh_closer(members):
        return "documented"
    return "no_update"


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
        {"fieldname": "label",        "label": "Group / Household",  "fieldtype": "Data",    "width": 230},
        {"fieldname": "total",        "label": "Total HH",           "fieldtype": "Int",     "width": 80},
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
        {"fieldname": "sub_label",    "label": "HHID",               "fieldtype": "Data",    "width": 160},
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
            ind.visit_count,
            ind.aadhaar_status,
            ind.income_status,
            hh.name                     AS hh_name,
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

    # ── Step 1: group individuals by HHID ─────────────────────────────────────
    hh_map = {}   # hhid → household dict with members list
    hh_order = [] # preserve first-seen order

    for r in rows:
        hhid = r.get("hh_name") or r.get("ind_id")
        if hhid not in hh_map:
            hh_map[hhid] = {
                "hhid":       r.get("hh_hhid") or hhid,
                "respondent": r.get("hh_respondent") or "",
                "street":     r.get("street_label") or "",
                "hh_cmchis":  r.get("hh_cmchis") or "",
                "co_id":      r.get("co_id"),
                "co_name":    r.get("co_name"),
                "ac_name":    r.get("ac_name"),
                "pm_name":    r.get("pm_name"),
                "iu_id":      r.get("iu_id"),
                "iu_label":   r.get("iu_label"),
                "iu_org":     r.get("iu_org"),
                "street_org": r.get("street_org"),
                "members":    [],
            }
            hh_order.append(hhid)
        hh_map[hhid]["members"].append({
            "aadhaar_status": r.get("aadhaar_status"),
            "income_status":  r.get("income_status"),
            "visit_count":    r.get("visit_count"),
        })

    # ── Step 2: classify each household ───────────────────────────────────────
    for hhid in hh_order:
        hh = hh_map[hhid]
        members = hh["members"]
        max_visits = max(int(m.get("visit_count") or 0) for m in members)
        bucket = _hh_bucket(hh["hh_cmchis"], max_visits, members)
        gap = _hh_doc_gap(members) if bucket == "no_update" else None
        hh["bucket"] = bucket
        hh["gap"] = gap

    # ── Step 3: group households by the requested dimension ───────────────────
    def _group_key(hh):
        if group_by == "CO":
            return hh.get("co_id") or "Unassigned", hh.get("co_name") or "Unassigned"
        if group_by == "AC":
            v = hh.get("ac_name") or "Unassigned"
            return v, v
        if group_by == "Project Manager":
            v = hh.get("pm_name") or "Unassigned"
            return v, v
        if group_by == "Intervention Unit":
            return hh.get("iu_id") or "Unknown", hh.get("iu_label") or hh.get("iu_id") or "Unknown"
        if group_by == "Street":
            v = hh.get("street") or "Unknown"
            return v, v
        v = hh.get("iu_org") or hh.get("street_org") or "Unknown"
        return v, v

    groups = {}
    group_order = []

    for hhid in hh_order:
        hh = hh_map[hhid]
        gkey, glabel = _group_key(hh)
        bucket = hh["bucket"]
        gap = hh["gap"]

        if gkey not in groups:
            groups[gkey] = {
                "label":       glabel,
                "total":       0,
                "reach_gap":   0, "no_update":  0, "documented": 0,
                "applied":     0, "active":     0, "rejected":   0,
                "both_missing":0, "no_aadhaar": 0, "no_income":  0,
                "households":  [],
            }
            group_order.append(gkey)

        g = groups[gkey]
        g["total"] += 1
        g[bucket] += 1
        if gap:
            g[gap] += 1

        g["households"].append({
            "hhid":   hhid,
            "name":   hh.get("respondent") or hhid,
            "street": hh.get("street") or "",
            "bucket": bucket,
            "gap":    gap,
        })

    group_order.sort(key=lambda k: -(groups[k]["active"] / max(groups[k]["total"], 1)))

    # ── Step 4: build output rows ──────────────────────────────────────────────
    BUCKET_ORDER = ["reach_gap", "no_update", "documented", "applied", "active", "rejected"]
    EMPTY_NUMS = {
        "total": "", "reach_gap": "", "no_update": "", "both_missing": "",
        "no_aadhaar": "", "no_income": "", "documented": "", "applied": "",
        "active": "", "rejected": "", "pct_active": "",
    }

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

        sorted_hhs = sorted(g["households"], key=lambda x: BUCKET_ORDER.index(x["bucket"]))

        for hh in sorted_hhs:
            if hh["bucket"] == "no_update" and hh["gap"]:
                stage_str = {
                    "both_missing": "Both Docs Missing",
                    "no_aadhaar":   "Aadhaar Missing",
                    "no_income":    "Income Cert Missing",
                }.get(hh["gap"], _bucket_label(hh["bucket"]))
            else:
                stage_str = _bucket_label(hh["bucket"])

            row = dict(EMPTY_NUMS)
            row.update({
                "label":     hh["name"],
                "sub_label": hh["hhid"] or "",
                "stage":     stage_str,
                "indent":    1,
                "bold":      0,
            })
            data.append(row)

    return data
