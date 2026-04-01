import frappe
import csv
import os

def run(dry_run='True'):
    # Convert string argument from bench to Boolean
    is_dry_run = str(dry_run).lower() == 'true'
    
    # Locate the CSV file (Assuming it's in your frappe-bench folder)
    # If it's in a different folder, use the full path here
    file_path = 'updates.csv' 
    
    if not os.path.exists(file_path):
        print(f"❌ Error: File not found at {file_path}")
        return

    print(f"🚀 Starting Bulk Update (Dry Run: {is_dry_run})")

    with open(file_path, mode='r', encoding='utf-8-sig') as f:
        reader = csv.DictReader(f)
        
        success_count = 0
        for row in reader:
            # Mapping columns from your specific CSV
            ind_id = row.get('Individual ID', '').strip()
            hhid = row.get('HHID', '').strip()
            aadhaar_status = row.get('Aadhaar Status', '').strip()
            income_status = row.get('Income Certificate Status', '').strip()
            cmchis_status = row.get('CMCHIS Status', '').strip()

            if not ind_id or not hhid:
                continue

            if is_dry_run:
                print(f"[DRY RUN] Would update IND: {ind_id} ({aadhaar_status}) and HH: {hhid} ({cmchis_status})")
            else:
                try:
                    # 1. Update the Individual
                    frappe.db.set_value('Individual Profile-WRP', ind_id, {
                        'aadhaar_status': aadhaar_status,
                        'income_status': income_status
                    })
                    
                    # 2. Update the Household
                    frappe.db.set_value('Household Profile-WRP', hhid, {
                        'cmchis_status': cmchis_status
                    })
                    
                    success_count += 1
                    if success_count % 50 == 0:
                        print(f"Processed {success_count} records...")
                        
                except Exception as e:
                    print(f"❌ Error updating {ind_id}: {e}")

    if not is_dry_run:
        frappe.db.commit()
        print(f"✅ Successfully updated {success_count} records in the database.")
    else:
        print("💡 Dry run complete. No changes were saved to the database.")