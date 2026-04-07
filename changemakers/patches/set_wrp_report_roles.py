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
        report = frappe.get_doc("Report", report_name)
        existing_roles = {r.role for r in report.roles}
        changed = False
        for role in roles:
            if role not in existing_roles:
                report.append("roles", {"role": role})
                changed = True
        if changed:
            report.save(ignore_permissions=True)

    frappe.db.commit()
