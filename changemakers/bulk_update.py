import frappe
import csv
import os

def run_update(dry_run='True'):
    is_dry_run = str(dry_run).lower() == 'true'
    # The Absolute Path guarantees it will find the file
    file_path = '/Users/vishnuharikumar/frappe-bench/updates.csv' 
    
    if not os.path.exists(file_path):
        print(f"❌ Error: File not found at {file_path}")
        return

    print(f"🚀 Starting Bulk Update (Dry Run: {is_dry_run})")

    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        success_count = 0
        for row in reader:
            ind_id = row.get('Individual ID', '').strip()
            hhid = row.get('HHID', '').strip()
            aadhaar_status = row.get('Aadhaar Status', '').strip()
            income_status = row.get('Income Certificate Status', '').strip()
            cmchis_status = row.get('CMCHIS Status', '').strip()

            if not ind_id or not hhid:
                continue

            if is_dry_run:
                print(f"[DRY RUN] IND: {ind_id} -> Aadhaar: {aadhaar_status} | HH: {hhid} -> CMCHIS: {cmchis_status}")
            else:
                try:
                    frappe.db.set_value('Individual Profile-WRP', ind_id, {
                        'aadhaar_status': aadhaar_status,
                        'income_status': income_status
                    })
                    frappe.db.set_value('Household Profile-WRP', hhid, {
                        'cmchis_status': cmchis_status
                    })
                    success_count += 1
                except Exception as e:
                    print(f"❌ Error on {ind_id}: {e}")

    if not is_dry_run:
        frappe.db.commit()
        print(f"✅ Successfully updated {success_count} records.")
