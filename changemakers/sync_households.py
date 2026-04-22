import frappe
import requests
import json

def patch_household_data():
    doctype_name = "Household Profile-WRP"
    
    # Replace these with your live API credentials
    api_key = "YOUR_LIVE_API_KEY"
    api_secret = "YOUR_LIVE_API_SECRET"
    
    headers = {
        "Authorization": f"token {api_key}:{api_secret}",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    # 1. Fetch ONLY the locally updated households
    local_households = frappe.get_all(
        doctype_name,
        filters={"modified": [">=", "2026-04-01"]},
        fields=["name", "cmchis_status"] # We only pull the name and the one field we need
    )

    print(f"Found {len(local_households)} households updated locally since yesterday.")

    updated_count = 0
    
    for hh in local_households:
        hh_name = hh.pop("name") 
        live_record_url = f"https://apf-changemakers-chennai.frappe.cloud/api/resource/{doctype_name}/{hh_name}"
        
        # 2. Check the live server to protect today's field work
        get_response = requests.get(live_record_url, headers=headers)
        
        if get_response.status_code == 200:
            live_modified = get_response.json().get("data", {}).get("modified", "")
            
            # If modified today (April 2), skip it
            if live_modified.startswith("2026-04-02"):
                print(f"⏭️ Skipping Household {hh_name} - Already modified by staff today.")
                continue
        else:
            print(f"⚠️ Household {hh_name} not found on live server. Skipping.")
            continue
            
        # 3. Patch the live record with the CMCHIS status
        put_response = requests.put(live_record_url, headers=headers, data=json.dumps(hh, default=str))
        
        if put_response.status_code == 200:
            updated_count += 1
            print(f"✅ Updated CMCHIS for {hh_name}")
        else:
            print(f"❌ Failed to update {hh_name}: {put_response.text}")
            
    print(f"\nFinished. Successfully updated {updated_count} households.")