import frappe


def _user_org_filter():
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if not wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        return "", {}
    org = frappe.db.get_value("Staff details - WRP", {"mail_id": frappe.session.user}, "organisation")
    if not org:
        return None
    return " AND sl.implementing_org = %(user_org)s", {"user_org": org}


# ── HH-level helpers (same rule as pipeline dashboard) ────────────────────────

AADHAAR_RECEIVED = "Aadhaar Received"
INCOME_READY = {"Income Cert Received", "Income Cert Expired"}


def _hh_closer(members):
    for m in members:
        if (m.get("aadhaar_status") or "") == AADHAAR_RECEIVED and \
           (m.get("income_status") or "") in INCOME_READY:
            return True
    return False


def _hh_bucket(hh_cmchis, max_visits, members):
    c = (hh_cmchis or "").lower()
    if "active" in c:
        return "active"
    if "rejected" in c:
        return "rejected"
    if "applied" in c and "not" not in c:
        return "applied"
    if int(max_visits or 0) == 0:
        return "unvisited"
    if _hh_closer(members):
        return "docs_ready"
    return "pending_docs"


# ── Columns ───────────────────────────────────────────────────────────────────

def execute(filters=None):
    filters = filters or {}
    return get_columns(), get_data(filters)


def get_columns():
    return [
        {"fieldname": "label",        "label": "CO / Street",        "fieldtype": "Data",    "width": 220},
        {"fieldname": "iu",           "label": "Intervention Unit",  "fieldtype": "Data",    "width": 150},
        {"fieldname": "total_hh",     "label": "Total HH",           "fieldtype": "Int",     "width": 90},
        {"fieldname": "unvisited",    "label": "Unvisited",          "fieldtype": "Int",     "width": 90},
        {"fieldname": "pending_docs", "label": "Pending Docs",       "fieldtype": "Int",     "width": 110},
        {"fieldname": "docs_ready",   "label": "Docs Ready",         "fieldtype": "Int",     "width": 100},
        {"fieldname": "applied",      "label": "Applied",            "fieldtype": "Int",     "width": 80},
        {"fieldname": "active",       "label": "Active",             "fieldtype": "Int",     "width": 80},
        {"fieldname": "rejected",     "label": "Rejected",           "fieldtype": "Int",     "width": 80},
        {"fieldname": "pct_active",   "label": "% Active",           "fieldtype": "Percent", "width": 95},
    ]


# ── Data ──────────────────────────────────────────────────────────────────────

def get_data(filters):
    cond = ""
    vals = {}

    if filters.get("street"):
        cond += " AND sl.name = %(street)s"
        vals["street"] = filters["street"]
    if filters.get("intervention_unit"):
        cond += " AND sl.intervention_units = %(intervention_unit)s"
        vals["intervention_unit"] = filters["intervention_unit"]
    if filters.get("cluster"):
        cond += " AND sl.cluster = %(cluster)s"
        vals["cluster"] = filters["cluster"]
    if filters.get("organisation"):
        cond += " AND sl.implementing_org = %(organisation)s"
        vals["organisation"] = filters["organisation"]

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
            hh.cmchis_status            AS hh_cmchis,
            sl.street_name              AS street_label,
            sl.name                     AS street_id,
            sl.added_by_co              AS co_id,
            sl.intervention_units       AS iu_id,
            iu.name_of_iu               AS iu_label,
            co_staff.full_name          AS co_name
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
        WHERE ind.status = 'Active- ஆக்டிவ்'
              {cond}
        """.format(cond=cond),
        vals,
        as_dict=True,
    )

    if not rows:
        return []

    # ── Step 1: group individuals by household ────────────────────────────────
    hh_map   = {}
    hh_order = []

    for r in rows:
        hh_name = r.get("hh_name") or r.get("ind_id")
        if hh_name not in hh_map:
            hh_map[hh_name] = {
                "hh_cmchis":    r.get("hh_cmchis") or "",
                "street_id":    r.get("street_id") or "",
                "street_label": r.get("street_label") or "",
                "co_id":        r.get("co_id") or "Unassigned",
                "co_name":      r.get("co_name") or r.get("co_id") or "Unassigned",
                "iu_id":        r.get("iu_id") or "",
                "iu_label":     r.get("iu_label") or r.get("iu_id") or "",
                "members":      [],
            }
            hh_order.append(hh_name)
        hh_map[hh_name]["members"].append({
            "visit_count":    r.get("visit_count"),
            "aadhaar_status": r.get("aadhaar_status"),
            "income_status":  r.get("income_status"),
        })

    # ── Step 2: classify each household ──────────────────────────────────────
    for hh_name in hh_order:
        hh = hh_map[hh_name]
        members = hh["members"]
        max_visits = max(int(m.get("visit_count") or 0) for m in members)
        hh["bucket"] = _hh_bucket(hh["hh_cmchis"], max_visits, members)

    # ── Step 3: aggregate by CO → Street ─────────────────────────────────────
    def _empty_counter():
        return {"total_hh": 0, "unvisited": 0, "pending_docs": 0,
                "docs_ready": 0, "applied": 0, "active": 0, "rejected": 0}

    cos     = {}   # co_id → {meta, streets: {street_id → counter}}
    co_order = []

    for hh_name in hh_order:
        hh     = hh_map[hh_name]
        co_id  = hh["co_id"]
        st_id  = hh["street_id"] or "unknown"
        bucket = hh["bucket"]

        if co_id not in cos:
            cos[co_id] = {
                "co_name":  hh["co_name"],
                "iu_label": hh["iu_label"],
                "totals":   _empty_counter(),
                "streets":  {},
                "st_order": [],
            }
            co_order.append(co_id)

        co = cos[co_id]
        co["totals"]["total_hh"] += 1
        co["totals"][bucket]     += 1

        if st_id not in co["streets"]:
            co["streets"][st_id] = {
                "label": hh["street_label"] or st_id,
                **_empty_counter(),
            }
            co["st_order"].append(st_id)

        co["streets"][st_id]["total_hh"] += 1
        co["streets"][st_id][bucket]     += 1

    # Sort COs: highest % active first
    co_order.sort(key=lambda k: -(
        cos[k]["totals"]["active"] / max(cos[k]["totals"]["total_hh"], 1)
    ))

    # ── Step 4: build output rows ─────────────────────────────────────────────
    EMPTY_NUMS = {
        "total_hh": "", "unvisited": "", "pending_docs": "",
        "docs_ready": "", "applied": "", "active": "", "rejected": "",
        "pct_active": "",
    }

    def _pct(t):
        return round(t["active"] / t["total_hh"] * 100, 1) if t["total_hh"] else 0.0

    data = []
    for co_id in co_order:
        co = cos[co_id]
        t  = co["totals"]
        data.append({
            "label":        co["co_name"],
            "iu":           co["iu_label"],
            "total_hh":     t["total_hh"],
            "unvisited":    t["unvisited"],
            "pending_docs": t["pending_docs"],
            "docs_ready":   t["docs_ready"],
            "applied":      t["applied"],
            "active":       t["active"],
            "rejected":     t["rejected"],
            "pct_active":   _pct(t),
            "indent":       0,
            "bold":         1,
        })

        # Street sub-rows sorted by % active descending
        sorted_streets = sorted(
            co["st_order"],
            key=lambda sid: -(co["streets"][sid]["active"] / max(co["streets"][sid]["total_hh"], 1))
        )
        for st_id in sorted_streets:
            st = co["streets"][st_id]
            row = dict(EMPTY_NUMS)
            row.update({
                "label":        st["label"],
                "iu":           "",
                "total_hh":     st["total_hh"],
                "unvisited":    st["unvisited"],
                "pending_docs": st["pending_docs"],
                "docs_ready":   st["docs_ready"],
                "applied":      st["applied"],
                "active":       st["active"],
                "rejected":     st["rejected"],
                "pct_active":   _pct(st),
                "indent":       1,
                "bold":         0,
            })
            data.append(row)

    return data
