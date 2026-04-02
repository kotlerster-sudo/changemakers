import frappe
from frappe import _

@frappe.whitelist()
def get_daily_workplan():
    payload = {
        "error_caught": None,
        "overall_metrics": {"total_individuals": 0, "total_households": 0, "visited_households": 0, "active_households": 0},
        "daily_plan": [],
        "workplan": {"unvisited": [], "pending_docs": [], "ready_to_apply": [], "applied": [], "active": [], "rejected": []}
    }
    try:
        current_user = frappe.session.user
        staff_member = frappe.db.get_value("Staff details - WRP", {"mail_id": current_user}, "name")
        if current_user == "Administrator" and not staff_member:
            staff_member = frappe.db.get_value("Staff details - WRP", {}, "name") 
        if not staff_member:
            payload["error_caught"] = f"Staff profile not found for {current_user}"
            return payload
            
        assigned_streets = frappe.get_all("Street List  - WRP", filters={"added_by_co": staff_member}, pluck="name")
        if assigned_streets:
            households = frappe.get_all("Household Profile-WRP", filters={"street_name": ["in", assigned_streets]}, fields=["name", "street_name", "cmchis_status", "respondent"])
            hh_map = {str(h.name): h for h in households}
            
            # UPDATED: Fetching contact_number AND notes for the Household Summary Screen
            individuals = frappe.get_all("Individual Profile-WRP", filters={"hhid": ["in", list(hh_map.keys())]}, fields=["name", "name_of_the_individual", "hhid", "aadhaar_status", "income_status", "visit_count", "last_visited_at", "contact_number", "notes"])
            today_date = frappe.utils.getdate(frappe.utils.nowdate())
            today_str = str(frappe.utils.nowdate())
            
            hh_groups = {}
            for hid in hh_map:
                h_data = hh_map[hid]
                c_raw = str(h_data.get("cmchis_status") or "Start – CMCHIS not applied")
                hh_groups[hid] = {
                    "hhid": hid, "street_name": str(h_data.get("street_name") or "Unknown"), "respondent": str(h_data.get("respondent") or "Unknown"),
                    "cmchis_status": c_raw, "members": [], "max_visits": 0, "has_closer": False, "has_sla_due": False,
                    "is_active": "active" in c_raw.lower(), "is_applied": "applied" in c_raw.lower() and "not" not in c_raw.lower(), 
                    "is_rejected": "rejected" in c_raw.lower(), "visited_today": False
                }

            for ind in individuals:
                hid = str(ind.get("hhid"))
                if hid not in hh_groups: continue
                vc = int(ind.get("visit_count") or 0)
                a_stat = str(ind.get("aadhaar_status") or "")
                i_stat = str(ind.get("income_status") or "")
                lv_raw = ind.get("last_visited_at")
                
                current_hh = hh_groups[hid]
                is_due = False
                if vc > 0 and lv_raw:
                    lv_str = str(lv_raw)[:10]
                    lv_date = frappe.utils.getdate(lv_str)
                    if lv_str == today_str: current_hh["visited_today"] = True
                    if '15d' in a_stat and frappe.utils.date_diff(today_date, lv_date) >= 15: is_due = True
                    elif '4d' in i_stat and frappe.utils.date_diff(today_date, lv_date) >= 4: is_due = True
                    elif '5d' in current_hh["cmchis_status"] and frappe.utils.date_diff(today_date, lv_date) >= 5: is_due = True

                # UPDATED: Added notes to the dictionary sent to Flutter
                current_hh["members"].append({
                    "id": str(ind.get("name")), 
                    "head_name": str(ind.get("name_of_the_individual") or "Unknown"), 
                    "hhid": hid, "aadhaar_status": a_stat, "income_status": i_stat, 
                    "cmchis_status": current_hh["cmchis_status"], "visit_count": vc,
                    "contact_number": str(ind.get("contact_number") or ""),
                    "notes": str(ind.get("notes") or "")
                })
                if vc > current_hh["max_visits"]: current_hh["max_visits"] = vc
                if is_due: current_hh["has_sla_due"] = True
                if "Received" in a_stat and "Received" in i_stat and not current_hh["is_active"]: current_hh["has_closer"] = True

            for hid in hh_groups:
                data = hh_groups[hid]
                if not data["members"]: continue
                
                if data["is_rejected"]: payload["workplan"]["rejected"].append(data)
                elif data["is_active"]: payload["workplan"]["active"].append(data)
                elif data["is_applied"]: payload["workplan"]["applied"].append(data)
                elif data["has_closer"]: payload["workplan"]["ready_to_apply"].append(data)
                elif data["max_visits"] == 0: payload["workplan"]["unvisited"].append(data)
                else: payload["workplan"]["pending_docs"].append(data)

                if not data["is_active"] and not data["visited_today"]:
                    if data["has_closer"] and not data["is_applied"] and not data["is_rejected"]: payload["daily_plan"].append(data)
                    elif data["has_sla_due"] or data["is_rejected"]: payload["daily_plan"].append(data)
                    elif data["max_visits"] == 0: payload["daily_plan"].append(data)

            payload["daily_plan"] = payload["daily_plan"][:30]
            payload["overall_metrics"]["total_individuals"] = len(individuals)
            payload["overall_metrics"]["total_households"] = len([x for x in hh_groups if hh_groups[x]["members"]])
            payload["overall_metrics"]["active_households"] = len(payload["workplan"]["active"])
            payload["overall_metrics"]["visited_households"] = payload["overall_metrics"]["total_households"] - len(payload["workplan"]["unvisited"])
    except Exception as e:
        frappe.log_error(frappe.get_traceback(), "Daily Workplan API Error")
        payload["error_caught"] = f"PYTHON CRASH: {str(e)}"
    return payload

@frappe.whitelist()
def get_co_performance():
    current_user = frappe.session.user
    staff_member = frappe.db.get_value("Staff details - WRP", {"mail_id": current_user}, "name")
    if current_user == "Administrator" and not staff_member:
        staff_member = frappe.db.get_value("Staff details - WRP", {}, "name") 

    payload = {
        "error_caught": None, "mission": {"reach_gap": 0, "first_visit_count": 0, "stagnant_count": 0, "total_assigned": 0, "active_percent": 0.0},
        "pipeline": {"screened": 0, "no_update": 0, "documented": 0, "applied": 0, "active": 0, "rejected": 0},
        "drilldown": {"reach_gap": [], "first_visit": [], "stagnant": [], "screened": [], "no_update": [], "documented": [], "applied": [], "active": [], "rejected": [], "needs_both": [], "needs_only_income": [], "needs_only_aadhaar": [], "cmchis_action_required": []}
    }

    try:
        assigned_streets = frappe.get_all("Street List  - WRP", filters={"added_by_co": staff_member}, pluck="name")
        if assigned_streets:
            all_households = frappe.get_all("Household Profile-WRP", fields=["name", "street_name", "cmchis_status"], filters={"street_name": ["in", assigned_streets]})
            hh_map = {h.name: h for h in all_households}
            if hh_map:
                individuals = frappe.get_all("Individual Profile-WRP", filters={"hhid": ["in", list(hh_map.keys())]}, fields=["name", "name_of_the_individual", "visit_count", "hhid", "aadhaar_status", "income_status", "last_visited_at", "last_update_summary", "modified"])
                today = frappe.utils.getdate(frappe.utils.nowdate())
                active_count = 0

                for ind in individuals:
                    hh_data = hh_map.get(ind.hhid)
                    vc, a_stat, i_stat, c_stat = int(ind.get("visit_count") or 0), str(ind.get("aadhaar_status") or ""), str(ind.get("income_status") or ""), str(hh_data.get("cmchis_status") or "").lower()
                    person_obj = {"id": ind.name, "name": ind.get("name_of_the_individual"), "street_name": hh_data.get("street_name"), "hhid": ind.get("hhid"), "aadhaar_status": ind.get("aadhaar_status"), "income_status": ind.get("income_status"), "cmchis_status": hh_data.get("cmchis_status"), "visit_count": vc}
                    
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
                        if vc >= 2 or frappe.utils.date_diff(today, frappe.utils.getdate(ind.modified)) >= 14:
                            payload["mission"]["stagnant_count"] += 1
                            payload["drilldown"]["stagnant"].append(person_obj)
                        elif vc == 1:
                            payload["mission"]["first_visit_count"] += 1
                            payload["drilldown"]["first_visit"].append(person_obj)

                        if not has_aadhaar and not has_income: payload["drilldown"]["needs_both"].append(person_obj)
                        elif has_aadhaar and not has_income: payload["drilldown"]["needs_only_income"].append(person_obj)
                        elif not has_aadhaar and has_income: payload["drilldown"]["needs_only_aadhaar"].append(person_obj)
                        elif has_aadhaar and has_income: payload["drilldown"]["cmchis_action_required"].append(person_obj)

                payload["mission"]["total_assigned"] = len(individuals)
                payload["mission"]["active_percent"] = round((active_count / len(individuals) * 100), 1) if len(individuals) > 0 else 0.0
    except Exception as e:
        payload["error_caught"] = f"CRASH: {str(e)}"
    return payload

@frappe.whitelist()
def get_co_household_list():
    current_user = frappe.session.user
    staff_member = frappe.db.get_value("Staff details - WRP", {"mail_id": current_user}, "name")
    if current_user == "Administrator" and not staff_member:
        staff_member = frappe.db.get_value("Staff details - WRP", {}, "name") 
    
    assigned_streets = frappe.get_all("Street List  - WRP", filters={"added_by_co": staff_member}, pluck="name")
    households = frappe.get_all("Household Profile-WRP", filters={"street_name": ["in", assigned_streets]}, fields=["name", "street_name", "cmchis_status"])
    hh_map = {h.name: h for h in households}
    
    # UPDATED: Added notes to fields list
    individuals = frappe.get_all(
        "Individual Profile-WRP",
        filters=[["hhid", "in", list(hh_map.keys())], ["visit_count", ">", 0]],
        fields=["name", "name_of_the_individual", "hhid", "aadhaar_status", "income_status", "last_visited_at", "phone", "last_update_summary", "visit_count", "esm_username", "contact_number", "notes"],
        order_by="modified desc", limit=50
    )
    
    ind_names = [ind.name for ind in individuals]
    doc_map = {}
    if ind_names:
        vault_items = frappe.get_all("Document Vault Item", filters={"parent": ["in", ind_names]}, fields=["parent", "category", "file_name", "file_path"])
        for item in vault_items:
            if item.parent not in doc_map: doc_map[item.parent] = []
            doc_map[item.parent].append(item)

    history_feed = []
    for ind in individuals:
        hh_data = hh_map.get(ind.hhid) or {}
        history_feed.append({
            "name": ind.get("name"), "full_name": ind.get("name_of_the_individual"), "hhid": ind.get("hhid"),
            "street_name": hh_data.get("street_name"), "cmchis_status": hh_data.get("cmchis_status"),
            "aadhaar_status": ind.get("aadhaar_status"), "income_status": ind.get("income_status"),
            "last_visited_at": ind.get("last_visited_at"), "contact_number": ind.get("contact_number"),
            "last_update_summary": ind.get("last_update_summary"), "visit_count": ind.get("visit_count"),
            "notes": str(ind.get("notes") or ""), # UPDATED: Added notes to mapping
            "document_vault": doc_map.get(ind.name, [])
        })
    return history_feed