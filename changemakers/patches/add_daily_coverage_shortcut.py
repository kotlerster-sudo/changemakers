import frappe


def execute():
    """Add CO Daily Coverage shortcut to WRP Performance workspace."""
    if not frappe.db.exists("Workspace", "WRP Performance"):
        return

    already_exists = frappe.db.sql(
        "SELECT name FROM `tabWorkspace Shortcut` WHERE parent=%s AND link_to=%s LIMIT 1",
        ("WRP Performance", "CO Daily Coverage"),
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
            "CO Daily Coverage", "CO Daily Coverage", "Report", "Green",
        ),
    )

    # Also update the content JSON to include the new shortcut block
    frappe.db.sql(
        """UPDATE tabWorkspace SET content = %s WHERE name = %s""",
        (
            '[{"id":"wrp_h1","type":"header","data":{"text":"<span class=\\"h4\\">WRP Performance</span>","col":12}},'
            '{"id":"wrp_p1","type":"paragraph","data":{"text":"CMCHIS progress and pipeline bottleneck tracking.","col":12}},'
            '{"id":"wrp_p2","type":"paragraph","data":{"text":"Performance","col":12}},'
            '{"id":"wrp_s1","type":"shortcut","data":{"shortcut_name":"CO CMCHIS Performance","col":4}},'
            '{"id":"wrp_p3","type":"paragraph","data":{"text":"Delay & Bottleneck Analysis","col":12}},'
            '{"id":"wrp_s2","type":"shortcut","data":{"shortcut_name":"CMCHIS Delay Analysis","col":4}},'
            '{"id":"wrp_p4","type":"paragraph","data":{"text":"Daily Coverage","col":12}},'
            '{"id":"wrp_s3","type":"shortcut","data":{"shortcut_name":"CO Daily Coverage","col":4}}]',
            "WRP Performance",
        ),
    )

    frappe.db.commit()
