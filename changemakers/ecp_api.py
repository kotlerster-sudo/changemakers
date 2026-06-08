"""
ECP (Elderly Care Programme) Dashboard API
------------------------------------------
Data source: Individual Profile-WRP  (age >= 55, active)
             Household Profile-WRP   (linked via hhid)
             Street List - WRP       (eco_allotted, cluster, implementing_org, intervention_units)
"""
import json as _json
import frappe
from collections import defaultdict


@frappe.whitelist()
def get_ecp_filter_options(implementing_org=None, cluster=None):
    """Cascading filter options: Org → Cluster → IU from Street List - WRP."""
    filters = {}
    if implementing_org:
        filters["implementing_org"] = implementing_org
    if cluster:
        filters["cluster"] = cluster

    rows = frappe.get_all(
        "Street List  - WRP",
        filters=filters,
        fields=["implementing_org", "cluster", "intervention_units"],
    )

    all_orgs = sorted({r.implementing_org for r in rows if r.implementing_org})

    relevant = [r for r in rows if r.implementing_org == implementing_org] if implementing_org else rows
    clusters = sorted({r.cluster for r in relevant if r.cluster})

    if cluster:
        relevant = [r for r in relevant if r.cluster == cluster]
    ius = sorted({r.intervention_units for r in relevant if r.intervention_units})

    return {"orgs": all_orgs, "clusters": clusters, "ius": ius}


@frappe.whitelist()
def get_ecp_coverage(implementing_org=None, cluster=None, intervention_unit=None):
    """
    ECO-level elderly coverage: streets allocated, elderly count, HH with elderly.
    Sorted by elderly count descending.
    """
    street_filters = {}
    if implementing_org:
        street_filters["implementing_org"] = implementing_org
    if cluster:
        street_filters["cluster"] = cluster
    if intervention_unit:
        street_filters["intervention_units"] = intervention_unit

    streets = frappe.get_all(
        "Street List  - WRP",
        filters=street_filters,
        fields=["name", "eco_allotted"],
    )

    if not streets:
        return {"rows": [], "total_elderly": 0, "total_hh": 0}

    eco_streets = defaultdict(list)
    for s in streets:
        eco_streets[s.eco_allotted or "Unassigned"].append(s.name)

    result = []
    total_elderly = 0
    total_hh = 0

    for eco, street_list in eco_streets.items():
        row = frappe.db.sql("""
            SELECT COUNT(*) AS elderly_count, COUNT(DISTINCT hhid) AS hh_with_elderly
            FROM `tabIndividual Profile-WRP`
            WHERE age >= 55
              AND status LIKE 'Active%%'
              AND street IN %(streets)s
        """, {"streets": tuple(street_list)}, as_dict=True)

        elderly_count = int(row[0].elderly_count or 0) if row else 0
        hh_count = int(row[0].hh_with_elderly or 0) if row else 0
        total_elderly += elderly_count
        total_hh += hh_count

        result.append({
            "eco":           eco,
            "street_count":  len(street_list),
            "streets":       street_list,
            "elderly_count": elderly_count,
            "hh_with_elderly": hh_count,
        })

    result.sort(key=lambda x: (-x["elderly_count"], x["eco"]))
    return {"rows": result, "total_elderly": total_elderly, "total_hh": total_hh}


@frappe.whitelist()
def get_elderly_hh_ids(streets):
    """Returns distinct hhids for households with at least one elderly active member."""
    if isinstance(streets, str):
        streets = _json.loads(streets)
    if not streets:
        return {"hhids": []}

    rows = frappe.db.sql("""
        SELECT DISTINCT hhid
        FROM `tabIndividual Profile-WRP`
        WHERE age >= 55
          AND status LIKE 'Active%%'
          AND street IN %(streets)s
          AND hhid IS NOT NULL AND hhid != ''
    """, {"streets": tuple(streets)}, as_dict=True)

    return {"hhids": [r.hhid for r in rows]}
