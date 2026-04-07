import frappe


def execute():
    reports = [
        "CO CMCHIS Performance",
        "CMCHIS Pipeline Dashboard",
        "CO Daily Coverage",
        "CMCHIS Delay Analysis",
    ]
    roles = [
        "System Manager",
        "Admin (Partner)",
        "Program Manager",
        "Partner SMT",
        "WRP-PM",
        "WRP-AC",
        "WRP-MIS",
    ]

    for report_name in reports:
        if not frappe.db.exists("Report", report_name):
            continue

        # Fetch roles already in the DB for this report
        existing = {
            r[0] for r in frappe.db.sql(
                "SELECT role FROM `tabHas Role` WHERE parent=%s AND parenttype='Report'",
                report_name
            )
        }

        for role in roles:
            if role in existing:
                continue
            frappe.db.sql("""
                INSERT INTO `tabHas Role`
                    (name, creation, modified, modified_by, owner,
                     parent, parentfield, parenttype, role)
                VALUES
                    (%s, NOW(), NOW(), 'Administrator', 'Administrator',
                     %s, 'roles', 'Report', %s)
            """, (frappe.generate_hash(length=10), report_name, role))

    frappe.db.commit()
