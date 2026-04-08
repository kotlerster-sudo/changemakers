import frappe
from frappe import _


def _get_staff_member():
    """Returns the Staff details name for the current session user."""
    current_user = frappe.session.user
    staff_member = frappe.db.get_value("Staff details - WRP", {"mail_id": current_user}, "name")
    if current_user == "Administrator" and not staff_member:
        staff_member = frappe.db.get_value("Staff details - WRP", {}, "name")
    return staff_member


@frappe.whitelist()
def get_daily_workplan(force_refresh=0):
    payload = {
        "error_caught": None,
        "overall_metrics": {"total_individuals": 0, "total_households": 0, "visited_households": 0, "active_households": 0},
        "daily_plan": [],
        "workplan": {"unvisited": [], "pending_docs": [], "ready_to_apply": [], "applied": [], "active": [], "rejected": []}
    }
    try:
        staff_member = _get_staff_member()
        if not staff_member:
            payload["error_caught"] = f"Staff profile not found for {frappe.session.user}"
            return payload

        assigned_streets = frappe.get_all("Street List  - WRP", filters={"added_by_co": staff_member}, pluck="name")
        if not assigned_streets:
            return payload

        households = frappe.get_all(
            "Household Profile-WRP",
            filters={
                "street_name": ["in", assigned_streets],
                "survay_status": "Occupied/உள்ளனர்",
                "availability_for": "Going Ahead/துவங்கலாம்"
            },
            fields=["name", "street_name", "cmchis_status", "respondent"]
        )
        hh_map = {str(h.name): h for h in households}
        if not hh_map:
            return payload

        individuals = frappe.get_all(
            "Individual Profile-WRP",
            filters={
                "hhid": ["in", list(hh_map.keys())],
                "status": "Active- ஆக்டிவ்"
            },
            fields=["name", "name_of_the_individual", "hhid", "aadhaar_status", "income_status",
                    "visit_count", "last_visited_at", "contact_number", "phone",
                    "esm_username", "can_id", "notes"]
        )

        today_date = frappe.utils.getdate(frappe.utils.nowdate())
        today_str = str(frappe.utils.nowdate())

        hh_groups = {}
        for hid in hh_map:
            h_data = hh_map[hid]
            c_raw = str(h_data.get("cmchis_status") or "Start – CMCHIS not applied")
            hh_groups[hid] = {
                "hhid": hid,
                "street_name": str(h_data.get("street_name") or "Unknown"),
                "respondent": str(h_data.get("respondent") or "Unknown"),
                "cmchis_status": c_raw,
                "members": [],
                "max_visits": 0,
                "max_days_overdue": 0,       # largest overdue gap across members
                "min_days_since_visit": None, # most recent visit across members (for followup sort)
                "has_closer": False,
                "has_sla_due": False,
                "has_aadhaar": False,
                "has_income": False,
                "is_active": "active" in c_raw.lower(),
                "is_applied": "applied" in c_raw.lower() and "not" not in c_raw.lower(),
                "is_rejected": "rejected" in c_raw.lower(),
                "visited_today": False
            }

        for ind in individuals:
            hid = str(ind.get("hhid"))
            if hid not in hh_groups:
                continue
            vc = int(ind.get("visit_count") or 0)
            a_stat = str(ind.get("aadhaar_status") or "")
            i_stat = str(ind.get("income_status") or "")
            lv_raw = ind.get("last_visited_at")

            current_hh = hh_groups[hid]
            is_due = False
            days_since = None

            if vc > 0 and lv_raw:
                lv_str = str(lv_raw)[:10]
                lv_date = frappe.utils.getdate(lv_str)
                days_since = frappe.utils.date_diff(today_date, lv_date)
                if lv_str == today_str:
                    current_hh["visited_today"] = True
                # NOTE: SLA detection matches substrings in status option labels.
                # If status labels change (e.g. "ETA 15d" → "ETA 15 days"), update here.
                if '15d' in a_stat and days_since >= 15:
                    is_due = True
                    current_hh["max_days_overdue"] = max(current_hh["max_days_overdue"], days_since)
                elif '4d' in i_stat and days_since >= 4:
                    is_due = True
                    current_hh["max_days_overdue"] = max(current_hh["max_days_overdue"], days_since)
                elif '5d' in current_hh["cmchis_status"] and days_since >= 5:
                    is_due = True
                    current_hh["max_days_overdue"] = max(current_hh["max_days_overdue"], days_since)

            current_hh["members"].append({
                "id": str(ind.get("name")),
                "head_name": str(ind.get("name_of_the_individual") or "Unknown"),
                "hhid": hid,
                "aadhaar_status": a_stat,
                "income_status": i_stat,
                "cmchis_status": current_hh["cmchis_status"],
                "visit_count": vc,
                "contact_number": str(ind.get("contact_number") or ""),
                "phone": str(ind.get("phone") or ""),
                "esm_login_id": str(ind.get("esm_username") or ""),
                "can_id": str(ind.get("can_id") or ""),
                "notes": str(ind.get("notes") or "")
            })

            if vc > current_hh["max_visits"]:
                current_hh["max_visits"] = vc
            if days_since is not None:
                if current_hh["min_days_since_visit"] is None or days_since < current_hh["min_days_since_visit"]:
                    current_hh["min_days_since_visit"] = days_since
            if is_due:
                current_hh["has_sla_due"] = True
            if "Received" in a_stat:
                current_hh["has_aadhaar"] = True
            if "Received" in i_stat:
                current_hh["has_income"] = True

        # has_closer is a household-level flag: any member has Aadhaar received AND
        # any member has Income received (can be different members of same household).
        for hid in hh_groups:
            data = hh_groups[hid]
            if data["has_aadhaar"] and data["has_income"] and not data["is_active"] and not data["is_applied"]:
                data["has_closer"] = True

        # Build full workplan buckets (all households, all statuses)
        for hid in hh_groups:
            data = hh_groups[hid]
            if not data["members"]:
                continue
            if data["is_rejected"]:
                payload["workplan"]["rejected"].append(data)
            elif data["is_active"]:
                payload["workplan"]["active"].append(data)
            elif data["is_applied"]:
                payload["workplan"]["applied"].append(data)
            elif data["has_closer"]:
                payload["workplan"]["ready_to_apply"].append(data)
            elif data["max_visits"] == 0:
                payload["workplan"]["unvisited"].append(data)
            else:
                payload["workplan"]["pending_docs"].append(data)

        # Pool 1 — Unvisited: never visited, ALL statuses (active/rejected included
        #           because Aadhaar + income docs matter for other govt schemes too)
        unvisited_pool = []
        # Pool 2 — Docs ready: both docs received and ready to push CMCHIS application,
        #           OR active/rejected households still missing a doc for other schemes
        docs_ready_pool = []
        # Pool 3a — SLA overdue: at least one member has blown past their follow-up window
        sla_pool = []
        # Pool 3b — General follow-up: visited but no SLA alarm yet; longest-idle first
        other_followup_pool = []

        for hid, data in hh_groups.items():
            if not data["members"]:
                continue

            # Fully done: CMCHIS active AND both docs collected — nothing left to do, skip daily plan
            if data["is_active"] and data["has_aadhaar"] and data["has_income"]:
                continue

            if data["max_visits"] == 0:
                unvisited_pool.append(data)
            elif (data["has_closer"] and not data["is_applied"]) or (
                (data["is_active"] or data["is_rejected"])
                and not (data["has_aadhaar"] and data["has_income"])
            ):
                docs_ready_pool.append(data)
            elif data["has_sla_due"]:
                sla_pool.append(data)
            else:
                other_followup_pool.append(data)




        # Within each pool sort by street so CO walks one street at a time
        def by_street(d):
            return (d["street_name"], d["max_visits"])

        unvisited_pool.sort(key=by_street)
        docs_ready_pool.sort(key=by_street)
        # SLA pool: most overdue first, then street
        sla_pool.sort(key=lambda d: (-d["max_days_overdue"], d["street_name"]))
        # General followup: longest idle first, then street
        other_followup_pool.sort(key=lambda d: (-(d["min_days_since_visit"] or 0), d["street_name"]))

        followup_combined = sla_pool + other_followup_pool

        selected = unvisited_pool[:10] + docs_ready_pool[:10] + followup_combined[:10]

        # If any pool had fewer than 10, fill the gap from overflow of other pools
        # so the daily list always reaches 30 (or total available if < 30).
        if len(selected) < 30:
            used = {d["hhid"] for d in selected}
            overflow = [d for d in (
                unvisited_pool[10:] + docs_ready_pool[10:] + followup_combined[10:]
            ) if d["hhid"] not in used]
            selected += overflow[:30 - len(selected)]

        # Final sort: group the whole list by street so the CO finishes
        # one street before moving to the next. Within a street, preserve
        # the pool priority order (unvisited → docs-ready → follow-up).
        pool_rank = {d["hhid"]: i for i, d in enumerate(selected)}
        selected.sort(key=lambda d: (d["street_name"], pool_rank[d["hhid"]]))

        payload["daily_plan"] = selected

        payload["overall_metrics"]["total_individuals"] = len(individuals)
        payload["overall_metrics"]["total_households"] = len([x for x in hh_groups if hh_groups[x]["members"]])
        payload["overall_metrics"]["active_households"] = len(payload["workplan"]["active"])
        payload["overall_metrics"]["visited_households"] = (
            payload["overall_metrics"]["total_households"] - len(payload["workplan"]["unvisited"])
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Daily Workplan API Error")
        payload["error_caught"] = f"PYTHON CRASH: {str(e)}"

    return payload


@frappe.whitelist()
def get_co_performance():
    payload = {
        "error_caught": None,
        "mission": {"reach_gap": 0, "first_visit_count": 0, "stagnant_count": 0, "total_assigned": 0, "active_percent": 0.0},
        "pipeline": {"screened": 0, "no_update": 0, "documented": 0, "applied": 0, "active": 0, "rejected": 0},
        "drilldown": {
            "reach_gap": [], "first_visit": [], "stagnant": [], "screened": [], "no_update": [],
            "documented": [], "applied": [], "active": [], "rejected": [],
            "needs_both": [], "needs_only_income": [], "needs_only_aadhaar": [], "cmchis_action_required": []
        }
    }
    try:
        staff_member = _get_staff_member()
        if not staff_member:
            payload["error_caught"] = f"Staff profile not found for {frappe.session.user}"
            return payload

        assigned_streets = frappe.get_all("Street List  - WRP", filters={"added_by_co": staff_member}, pluck="name")
        if not assigned_streets:
            return payload

        all_households = frappe.get_all(
            "Household Profile-WRP",
            fields=["name", "street_name", "cmchis_status"],
            filters={
                "street_name": ["in", assigned_streets],
                "survay_status": "Occupied/உள்ளனர்",
                "availability_for": "Going Ahead/துவங்கலாம்"
            }
        )
        hh_map = {h.name: h for h in all_households}
        if not hh_map:
            return payload

        individuals = frappe.get_all(
            "Individual Profile-WRP",
            filters={
                "hhid": ["in", list(hh_map.keys())],
                "status": "Active- ஆக்டிவ்"
            },
            fields=["name", "name_of_the_individual", "visit_count", "hhid", "aadhaar_status",
                    "income_status", "last_visited_at", "last_update_summary"]
        )

        today = frappe.utils.getdate(frappe.utils.nowdate())
        active_count = 0

        for ind in individuals:
            hh_data = hh_map.get(ind.hhid)
            if not hh_data:
                continue

            vc = int(ind.get("visit_count") or 0)
            a_stat = str(ind.get("aadhaar_status") or "")
            i_stat = str(ind.get("income_status") or "")
            c_stat = str(hh_data.get("cmchis_status") or "").lower()

            person_obj = {
                "id": ind.name,
                "name": ind.get("name_of_the_individual"),
                "street_name": hh_data.get("street_name"),
                "hhid": ind.get("hhid"),
                "aadhaar_status": ind.get("aadhaar_status"),
                "income_status": ind.get("income_status"),
                "cmchis_status": hh_data.get("cmchis_status"),
                "visit_count": vc
            }

            is_rejected = "rejected" in c_stat
            is_active = "active" in c_stat
            is_applied = "applied" in c_stat and "not" not in c_stat
            has_aadhaar = "Received" in a_stat
            has_income = "Received" in i_stat

            if vc == 0:
                payload["mission"]["reach_gap"] += 1
                payload["drilldown"]["reach_gap"].append(person_obj)
                continue

            payload["pipeline"]["screened"] += 1
            payload["drilldown"]["screened"].append(person_obj)

            if is_rejected:
                payload["pipeline"]["rejected"] += 1
                payload["drilldown"]["rejected"].append(person_obj)
            elif is_active:
                active_count += 1
                payload["pipeline"]["active"] += 1
                payload["drilldown"]["active"].append(person_obj)
            elif has_aadhaar and has_income and is_applied:
                payload["pipeline"]["applied"] += 1
                payload["drilldown"]["applied"].append(person_obj)
            elif has_aadhaar and has_income:
                payload["pipeline"]["documented"] += 1
                payload["drilldown"]["documented"].append(person_obj)
            else:
                payload["pipeline"]["no_update"] += 1
                payload["drilldown"]["no_update"].append(person_obj)

            if not is_active and not is_rejected:
                lv_raw = ind.get("last_visited_at")
                # Use last_visited_at for staleness, not modified — admin edits must not reset the timer
                if lv_raw:
                    days_since_visit = frappe.utils.date_diff(today, frappe.utils.getdate(str(lv_raw)[:10]))
                    if vc >= 2 or days_since_visit >= 14:
                        payload["mission"]["stagnant_count"] += 1
                        payload["drilldown"]["stagnant"].append(person_obj)
                    elif vc == 1:
                        payload["mission"]["first_visit_count"] += 1
                        payload["drilldown"]["first_visit"].append(person_obj)
                else:
                    if vc >= 2:
                        payload["mission"]["stagnant_count"] += 1
                        payload["drilldown"]["stagnant"].append(person_obj)
                    elif vc == 1:
                        payload["mission"]["first_visit_count"] += 1
                        payload["drilldown"]["first_visit"].append(person_obj)

                if not has_aadhaar and not has_income:
                    payload["drilldown"]["needs_both"].append(person_obj)
                elif has_aadhaar and not has_income:
                    payload["drilldown"]["needs_only_income"].append(person_obj)
                elif not has_aadhaar and has_income:
                    payload["drilldown"]["needs_only_aadhaar"].append(person_obj)
                elif has_aadhaar and has_income:
                    payload["drilldown"]["cmchis_action_required"].append(person_obj)

        payload["mission"]["total_assigned"] = len(individuals)
        payload["mission"]["active_percent"] = (
            round((active_count / len(individuals) * 100), 1) if individuals else 0.0
        )

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "CO Performance API Error")
        payload["error_caught"] = f"CRASH: {str(e)}"

    return payload


@frappe.whitelist()
def get_co_household_list():
    """
    Returns bucketed individual data for the Individual Directory screen:
      - visit_buckets: grouped by visit depth (unvisited / v1 / v2 / v3_plus)
      - funnel_buckets: grouped by process stage (aadhaar / income / cmchis / stuck / active)
      - history_feed: flat list of all individuals, used by the Activity History screen
    """
    try:
        staff_member = _get_staff_member()
        if not staff_member:
            return {"visit_buckets": {}, "funnel_buckets": {}, "history_feed": []}

        assigned_streets = frappe.get_all("Street List  - WRP", filters={"added_by_co": staff_member}, pluck="name")
        if not assigned_streets:
            return {"visit_buckets": {}, "funnel_buckets": {}, "history_feed": []}

        households = frappe.get_all(
            "Household Profile-WRP",
            filters={
                "street_name": ["in", assigned_streets],
                "survay_status": "Occupied/உள்ளனர்",
                "availability_for": "Going Ahead/துவங்கலாம்"
            },
            fields=["name", "street_name", "cmchis_status"]
        )
        hh_map = {h.name: h for h in households}
        if not hh_map:
            return {"visit_buckets": {}, "funnel_buckets": {}, "history_feed": []}

        individuals = frappe.get_all(
            "Individual Profile-WRP",
            filters=[
                ["hhid", "in", list(hh_map.keys())],
                ["status", "=", "Active- ஆக்டிவ்"]
            ],
            fields=["name", "name_of_the_individual", "hhid", "aadhaar_status", "income_status",
                    "last_visited_at", "phone", "contact_number", "last_update_summary", "visit_count",
                    "esm_username", "can_id", "notes"],
            order_by="modified desc",
            limit=200
        )

        # Fetch all document vaults in a single bulk query
        ind_names = [ind.name for ind in individuals]
        doc_map = {}
        if ind_names:
            vault_items = frappe.get_all(
                "Document Vault Item",
                filters={"parent": ["in", ind_names]},
                fields=["parent", "category", "file_name", "file_path"]
            )
            for item in vault_items:
                doc_map.setdefault(item.parent, []).append(item)

        visit_buckets = {"unvisited": [], "v1": [], "v2": [], "v3_plus": []}
        funnel_buckets = {"aadhaar": [], "income": [], "cmchis": [], "stuck": [], "active": []}
        history_feed = []

        for ind in individuals:
            hh_data = hh_map.get(ind.hhid) or {}
            vc = int(ind.get("visit_count") or 0)
            a_stat = str(ind.get("aadhaar_status") or "")
            i_stat = str(ind.get("income_status") or "")
            c_stat = str(hh_data.get("cmchis_status") or "").lower()

            has_aadhaar = "Received" in a_stat
            has_income = "Received" in i_stat
            is_active = "active" in c_stat
            is_rejected = "rejected" in c_stat

            ind_obj = {
                "id": str(ind.get("name")),
                "head_name": str(ind.get("name_of_the_individual") or "Unknown"),
                "hhid": str(ind.get("hhid") or ""),
                "street_name": str(hh_data.get("street_name") or ""),
                "cmchis_status": str(hh_data.get("cmchis_status") or "Start – CMCHIS not applied"),
                "aadhaar_status": a_stat,
                "income_status": i_stat,
                "visit_count": vc,
                "last_visited_at": ind.get("last_visited_at"),
                "last_update_summary": str(ind.get("last_update_summary") or "Routine Follow-up"),
                "contact_number": str(ind.get("contact_number") or ""),
                "phone": str(ind.get("phone") or ""),
                "esm_login_id": str(ind.get("esm_username") or ""),
                "can_id": str(ind.get("can_id") or ""),
                "notes": str(ind.get("notes") or ""),
                "document_vault": doc_map.get(ind.name, [])
            }

            history_feed.append(ind_obj)

            # Visit depth buckets (all individuals, including unvisited)
            if vc == 0:
                visit_buckets["unvisited"].append(ind_obj)
            elif vc == 1:
                visit_buckets["v1"].append(ind_obj)
            elif vc == 2:
                visit_buckets["v2"].append(ind_obj)
            else:
                visit_buckets["v3_plus"].append(ind_obj)

            # Process funnel buckets (visited individuals only, excluding rejected)
            if is_active:
                funnel_buckets["active"].append(ind_obj)
            elif vc > 0 and not is_rejected:
                if has_aadhaar and has_income:
                    funnel_buckets["cmchis"].append(ind_obj)
                elif has_aadhaar and not has_income:
                    funnel_buckets["income"].append(ind_obj)
                elif not has_aadhaar:
                    funnel_buckets["aadhaar"].append(ind_obj)
                else:
                    funnel_buckets["stuck"].append(ind_obj)

        return {
            "visit_buckets": visit_buckets,
            "funnel_buckets": funnel_buckets,
            "history_feed": history_feed
        }

    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "CO Household List API Error")
        return {"error_caught": str(e), "visit_buckets": {}, "funnel_buckets": {}, "history_feed": []}


# ── CMCHIS status valid options (must match the Select field on Household Profile-WRP) ──
_VALID_CMCHIS = [
    "Start \u2013 CMCHIS not applied",
    "CMCHIS Applied \u2013 ETA 5d",
    "CMCHIS Active",
    "Rejected",
]

# Aliases so the Flutter app can send natural-language values
_CMCHIS_ALIASES = {
    "rejected":                         "Rejected",
    "reject":                           "Rejected",
    "application rejected":             "Rejected",
    "cmchis active":                    "CMCHIS Active",
    "active":                           "CMCHIS Active",
    "cmchis applied":                   "CMCHIS Applied \u2013 ETA 5d",
    "applied":                          "CMCHIS Applied \u2013 ETA 5d",
    "cmchis applied \u2013 eta 5d":     "CMCHIS Applied \u2013 ETA 5d",
    "not applied":                      "Start \u2013 CMCHIS not applied",
    "start":                            "Start \u2013 CMCHIS not applied",
    "start \u2013 cmchis not applied":  "Start \u2013 CMCHIS not applied",
}


@frappe.whitelist()
def save_cmchis_status(hhid, status):
    """
    Save cmchis_status on a Household Profile-WRP record.
    Accepts exact option values or common aliases (case-insensitive).
    """
    normalised = _CMCHIS_ALIASES.get((status or "").strip().lower())
    if not normalised:
        if status in _VALID_CMCHIS:
            normalised = status
        else:
            return {
                "error": f"Invalid CMCHIS status: {status!r}",
                "valid_values": _VALID_CMCHIS,
            }

    frappe.db.set_value("Household Profile-WRP", hhid, "cmchis_status", normalised)
    frappe.db.commit()
    return {"status": "ok", "saved": normalised}
