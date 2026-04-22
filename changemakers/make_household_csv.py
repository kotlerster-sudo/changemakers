import frappe
import csv
import os

def export_household_data():
    doctype_name = "Household Profile-WRP" 
    
    print(f"Fetching local records for {doctype_name}...")
    
    local_records = frappe.get_all(
        doctype_name,
        fields=["name", "cmchis_status", "has_multiple_ration_cards"]
    )

    if not local_records:
        print("No household records found.")
        return

    # --- DATA CLEANING FILTER ---
    for doc in local_records:
        if doc.get("cmchis_status"):
            status = str(doc["cmchis_status"]).strip()
            
            # 1. Fix the hyphen and capitalization mismatch
            if status == "Start - CMCHIS Not Applied":
                status = "Start – CMCHIS not applied"
            
            # 2. Handle the rogue "Rejected" status by clearing it
            elif status == "Rejected":
                status = "" 
                
            doc["cmchis_status"] = status
    # --------------------------------

    desktop_path = os.path.expanduser("~/Desktop/fast_household_update.csv")
    
    with open(desktop_path, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=local_records[0].keys())
        writer.writeheader()
        writer.writerows(local_records)
        
    print(f"✅ Success! Saved {len(local_records)} household records to your Desktop: {desktop_path}")