import frappe


def _user_org_filter():
    """
    Returns (cond, vals) to restrict data to the current user's implementing org
    when they hold a WRP-PM / WRP-AC / WRP-MIS role.
    Returns ("", {}) for unrestricted roles.
    Returns None when a WRP user has no staff record (no data should be shown).
    """
    wrp_roles = {"WRP-PM", "WRP-AC", "WRP-MIS"}
    if not wrp_roles.intersection(set(frappe.get_roles(frappe.session.user))):
        return "", {}
    org = frappe.db.get_value("Staff details - WRP", {"mail_id": frappe.session.user}, "organisation")
    if not org:
        return None
    return " AND sl.implementing_org = %(user_org)s", {"user_org": org}


def execute(filters=None):
    filters = filters or {}
    columns = get_columns()
    data = get_data(filters)
    return columns, data


def get_columns():
    return [
        {"fieldname": "co_name", "label": "CO Name", "fieldtype": "Data", "width": 180},
        {"fieldname": "intervention_unit", "label": "Intervention Unit", "fieldtype": "Link",
         "options": "Intervention Units-WRP", "width": 160},
        {"fieldname": "street", "label": "Street", "fieldtype": "Data", "width": 140},
        {"fieldname": "total_hh", "label": "Total HH", "fieldtype": "Int", "width": 90},
        {"fieldname": "unvisited", "label": "Unvisited", "fieldtype": "Int", "width": 90},
        {"fieldname": "pending_docs", "label": "Pending Docs", "fieldtype": "Int", "width": 110},
        {"fieldname": "docs_ready", "label": "Docs Ready", "fieldtype": "Int", "width": 100},
        {"fieldname": "applied", "label": "Applied", "fieldtype": "Int", "width": 80},
        {"fieldname": "rejected", "label": "Rejected", "fieldtype": "Int", "width": 80},
        {"fieldname": "active", "label": "Active", "fieldtype": "Int", "width": 80},
        {"fieldname": "pct_active", "label": "% CMCHIS Active", "fieldtype": "Percent", "width": 130},
    ]


def get_data(filters):
    # Build Street filter conditions
    street_conditions = ""
    street_values = {}

    if filters.get("street"):
        street_conditions += " AND sl.name = %(street)s"
        street_values["street"] = filters["street"]

    if filters.get("intervention_unit"):
        street_conditions += " AND sl.intervention_units = %(intervention_unit)s"
        street_values["intervention_unit"] = filters["intervention_unit"]

    org_filter = _user_org_filter()
    if org_filter is None:
        return []
    org_cond, org_vals = org_filter
    street_conditions += org_cond
    street_values.update(org_vals)

    # Fetch all matching streets with their CO (added_by_co) and IU
    streets = frappe.db.sql(
        """
        SELECT
            sl.name        AS street_name,
            sl.street_name AS street_label,
            sl.intervention_units AS intervention_unit,
            sl.added_by_co AS co_staff_id
        FROM `tabStreet List  - WRP` sl
        WHERE sl.added_by_co IS NOT NULL
              AND sl.added_by_co != ''
              {conditions}
        ORDER BY sl.added_by_co, sl.intervention_units, sl.name
        """.format(conditions=street_conditions),
        street_values,
        as_dict=True,
    )

    if not streets:
        return []

    # Get all CO staff names in one query
    co_ids = list({s["co_staff_id"] for s in streets if s.get("co_staff_id")})
    staff_rows = frappe.get_all(
        "Staff details - WRP",
        filters={"name": ["in", co_ids]},
        fields=["name", "full_name"],
    )
    staff_name_map = {r["name"]: r["full_name"] for r in staff_rows}

    # Aggregate HH counts per street
    street_names = [s["street_name"] for s in streets]

    hh_rows = frappe.db.sql(
        """
        SELECT
            hh.street_name,
            hh.cmchis_status,
            hh.survay_status,
            COUNT(*) AS cnt
        FROM `tabHousehold Profile-WRP` hh
        WHERE hh.street_name IN %(streets)s
        GROUP BY hh.street_name, hh.cmchis_status, hh.survay_status
        """,
        {"streets": street_names},
        as_dict=True,
    )

    # Build per-street counter dict
    # cmchis_status values observed: 'CMCHIS Active', 'Applied', 'Rejected',
    #   'Documents Ready', 'Pending Documents', None/''
    # survay_status: 'Visited', 'Not Visited' (used for unvisited count)
    street_stats = {}
    for row in hh_rows:
        sn = row["street_name"]
        if sn not in street_stats:
            street_stats[sn] = {
                "total_hh": 0,
                "unvisited": 0,
                "pending_docs": 0,
                "docs_ready": 0,
                "applied": 0,
                "rejected": 0,
                "active": 0,
            }
        s = street_stats[sn]
        cnt = row["cnt"] or 0
        s["total_hh"] += cnt

        status = (row["cmchis_status"] or "").strip()
        survey = (row["survay_status"] or "").strip().lower()

        if survey in ("not visited", "not_visited", "unvisited"):
            s["unvisited"] += cnt
        elif status == "CMCHIS Active":
            s["active"] += cnt
        elif status == "Applied":
            s["applied"] += cnt
        elif status == "Rejected":
            s["rejected"] += cnt
        elif status == "Documents Ready":
            s["docs_ready"] += cnt
        else:
            # Pending Documents or blank — count as pending if visited
            s["pending_docs"] += cnt

    data = []
    for st in streets:
        sn = st["street_name"]
        stats = street_stats.get(sn, {
            "total_hh": 0, "unvisited": 0, "pending_docs": 0,
            "docs_ready": 0, "applied": 0, "rejected": 0, "active": 0,
        })
        total = stats["total_hh"] or 0
        active = stats["active"] or 0
        pct = round((active / total) * 100, 1) if total else 0.0

        data.append({
            "co_name": staff_name_map.get(st["co_staff_id"], st["co_staff_id"]),
            "intervention_unit": st["intervention_unit"],
            "street": st["street_label"] or sn,
            "total_hh": total,
            "unvisited": stats["unvisited"],
            "pending_docs": stats["pending_docs"],
            "docs_ready": stats["docs_ready"],
            "applied": stats["applied"],
            "rejected": stats["rejected"],
            "active": active,
            "pct_active": pct,
        })

    # Sort by % Active descending, then CO name
    data.sort(key=lambda r: (-r["pct_active"], r["co_name"] or ""))
    return data
