import frappe


def execute():
    """Add CMCHIS Pipeline Dashboard as 4th shortcut in WRP Performance workspace."""
    if not frappe.db.exists("Workspace", "WRP Performance"):
        return

    already_exists = frappe.db.sql(
        "SELECT name FROM `tabWorkspace Shortcut` WHERE parent=%s AND link_to=%s LIMIT 1",
        ("WRP Performance", "CMCHIS Pipeline Dashboard"),
    )
    if already_exists:
        return

    frappe.db.sql(
        """INSERT INTO `tabWorkspace Shortcut`
           (name, parent, parenttype, parentfield, idx, label, link_to, type, color)
           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)""",
        (
            frappe.generate_hash(length=10),
            "WRP Performance", "Workspace", "shortcuts", 0,
            "CMCHIS Pipeline Dashboard", "CMCHIS Pipeline Dashboard", "Report", "Purple",
        ),
    )

    frappe.db.sql(
        """UPDATE tabWorkspace SET content = %s WHERE name = %s""",
        (
            '[{"id":"wrp_h1","type":"header","data":{"text":"<span class=\\"h4\\">WRP Performance</span>","col":12}},'
            '{"id":"wrp_p1","type":"paragraph","data":{"text":"CMCHIS progress and pipeline tracking.","col":12}},'
            '{"id":"wrp_p2","type":"paragraph","data":{"text":"Performance","col":12}},'
            '{"id":"wrp_s1","type":"shortcut","data":{"shortcut_name":"CO CMCHIS Performance","col":4}},'
            '{"id":"wrp_p3","type":"paragraph","data":{"text":"Delay & Bottleneck Analysis","col":12}},'
            '{"id":"wrp_s2","type":"shortcut","data":{"shortcut_name":"CMCHIS Delay Analysis","col":4}},'
            '{"id":"wrp_p4","type":"paragraph","data":{"text":"Daily Coverage","col":12}},'
            '{"id":"wrp_s3","type":"shortcut","data":{"shortcut_name":"CO Daily Coverage","col":4}},'
            '{"id":"wrp_p5","type":"paragraph","data":{"text":"Pipeline Dashboard","col":12}},'
            '{"id":"wrp_s4","type":"shortcut","data":{"shortcut_name":"CMCHIS Pipeline Dashboard","col":4}}]',
            "WRP Performance",
        ),
    )

    frappe.db.commit()
