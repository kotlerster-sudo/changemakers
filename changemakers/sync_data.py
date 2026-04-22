import frappe
import requests
import json

def patch_cloud_data():
    doctype_name = "Individual Profile-WRP"
    
    # Replace these with your live API credentials
    api_key = "eb1cf8ca241dbbf"
    api_secret = "9a486729a30b7ad"
    
    headers = {
        "Authorization": f"token {api_key}:{api_secret}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # 1. Fetch ONLY the local records you modified yesterday/recently
    # This filters 60,000 down to just your test data.
    local_records = frappe.get_all(
        doctype_name,
        filters={"modified": [">=", "2026-04-01"]},
        fields=[
            "name", 
            "aadhaar_status", 
            "income_status", 
            "cmchis_status", 
            "last_visited_at", 
            "visit_count", 
            "can_id", 
            "esm_login_id", 
            "password", 
            "phone", # VERIFY THESE EXACT FIELD NAMES
            "last_update_summary"
        ]
    )

    print(f"Found {len(local_records)} records updated locally since yesterday.")

    updated_count = 0
    
    for doc in local_records:
        doc_name = doc.pop("name") # Remove 'name' from the update payload, keep it for the URL
        live_record_url = f"https://apf-changemakers-chennai.frappe.cloud/api/resource/{doctype_name}/{doc_name}"
        
        # 2. Check the live server for today's activity
        get_response = requests.get(live_record_url, headers=headers)
        
        if get_response.status_code == 200:
            live_data = get_response.json().get("data", {})
            live_modified = live_data.get("modified", "")
            
            # If the live record was modified today (April 2, 2026), skip it
            if live_modified.startswith("2026-04-02"):
                print(f"⏭️ Skipping {doc_name} - Already modified by staff today.")
                continue
        else:
            print(f"⚠️ Record {doc_name} not found on live server. Skipping.")
            continue
            
        # 3. Update the live record with only your specific fields
        put_response = requests.put(live_record_url, headers=headers, data=json.dumps(doc, default=str))
        
        if put_response.status_code == 200:
            updated_count += 1
            print(f"✅ Updated fields for {doc_name}")
        else:
            print(f"❌ Failed to update {doc_name}: {put_response.text}")
            
    print(f"\nFinished. Successfully updated {updated_count} records.")