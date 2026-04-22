import frappe
import csv
import os

def export_clean_data():
    doctype_name = "Individual Profile-WRP" 
    
    print(f"Fetching local records for {doctype_name}...")
    
    local_records = frappe.get_all(
        doctype_name,
        fields=[
            "name", 
            "aadhaar_status", 
            "income_status",  
            "last_visited_at",  # Updated to match your error message
            "visit_count", 
            "can_id", 
            "esm_login_id", 
            "password", 
            "phone"
        ]
    )

    if not local_records:
        print("No records found.")
        return

    # --- DATA CLEANING FILTER ---
    for doc in local_records:
        
        # 1. Clean Date Formats
        if doc.get("last_visited_at"):
            val = str(doc["last_visited_at"]).strip()
            
            # Remove the corrupted junk dates
            if "00/01/00" in val or val == "None":
                doc["last_visited_at"] = "" 
            else:
                # Chop off the microseconds. 
                # Changes "2026-04-02 14:30:00.123456" -> "2026-04-02 14:30:00"
                doc["last_visited_at"] = val.split('.')[0]

        # 2. Fix Aadhaar spelling and dash discrepancies
        if doc.get("aadhaar_status"):
            status = str(doc["aadhaar_status"]).strip()
            status = status.replace("Aadhar ", "Aadhaar ")
            status = status.replace("Aadhar", "Aadhaar")
            status = status.replace(" - ", " – ")
            doc["aadhaar_status"] = status
    # --------------------------------

    desktop_path = os.path.expanduser("~/Desktop/fast_cloud_update.csv")
    
    with open(desktop_path, mode='w', newline='') as file:
        writer = csv.DictWriter(file, fieldnames=local_records[0].keys())
        writer.writeheader()
        writer.writerows(local_records)
        
    print(f"✅ Success! Saved {len(local_records)} cleaned records to your Desktop: {desktop_path}")