app_name = "changemakers"
app_title = "Frappe Changemakers"
app_publisher = "Arunodhaya"
app_description = "Empowering the people that do good."
app_email = "co5cwrparunodhaya@gmail.com"
app_license = "AGPL"
app_version = "0.0.1"  # Hardcoded for Frappe Cloud compatibility
required_frappe_version = ">=15.0.0 <16.0.0"

# Runs after every bench migrate — ensures WRP report roles survive module sync resets
after_migrate = ["changemakers.patches.set_wrp_report_roles_v2.execute"]

fixtures = [
    "Custom HTML Block",
    "Case Type",
    "State",
    "Payment Type",
    {"dt": "Client Script", "filters": {"name": "Action: Create User Profile"}},
    {
        "dt": "Role",
        "filters": {
            "role_name": (
                "in",
                [
                    "Social Worker",
                    "Shelter Team Member",
                    "Healthcare Team Member",
                    "Food Team Member",
                    "SMT(NGO)-Field Co-ordinator",
                    "Medical Co-ordinator",
                    "Program Manager",
                    "Partner SMT",
                    "Data MIS/Documentation (Admin)",
                ],
            )
        },
    },
    {
        "dt": "Report",
        "filters": {
            "name": (
                "in",
                [
                    "CO CMCHIS Performance",
                    "CMCHIS Pipeline Dashboard",
                    "CO Daily Coverage",
                    "CMCHIS Delay Analysis",
                ],
            )
        },
    },
]

# Includes in <head>
# ------------------
app_include_js = "/assets/changemakers/js/changemakers.js"

website_route_rules = [
    {"from_route": "/c/<path:app_path>", "to_route": "c"},
]

# Installation
# ------------
after_install = "changemakers.install.after_install"

# Document Events
# ---------------
doc_events = {
    "User": {
        "after_insert": "changemakers.frappe_changemakers.doctype.changemakers_user_profile.changemakers_user_profile.create_user_profile",
        "on_trash": [
            "changemakers.frappe_changemakers.doctype.changemakers_user_profile.changemakers_user_profile.delete_user_profile",
        ],
    }
}