app_name = "changemakers"
app_title = "Frappe Changemakers"
app_publisher = "Arunodhaya"
app_description = "Empowering the people that do good."
app_email = "co5cwrparunodhaya@gmail.com"
app_license = "AGPL"
app_version = "0.0.1"  # Hardcoded for Frappe Cloud compatibility
required_frappe_version = ">=15.0.0 <16.0.0"

# Runs after every bench migrate — ensures WRP report roles survive module sync resets
scheduler_events = {
    "daily": [
        "changemakers.scheduled_tasks.enrol_new_oap_eligibles",
    ],
}

after_migrate = [
    "changemakers.patches.set_wrp_report_roles_v2.execute",
    "changemakers.patches.seed_cmchis_entitlement.execute",
    "changemakers.patches.seed_oap_entitlement.execute",
]

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
                    "WRP Status Transitions",
                ],
            )
        },
    },
]

# Includes in <head>
# ------------------
app_include_js = "/assets/changemakers/js/changemakers.js"

# Generic Entitlement API — whitelisted for Flutter
override_whitelisted_methods = {
    "changemakers.entitlement_api.get_entitlement_config":   "changemakers.entitlement_api.get_entitlement_config",
    "changemakers.entitlement_api.get_daily_workplan_v2":    "changemakers.entitlement_api.get_daily_workplan_v2",
    "changemakers.entitlement_api.save_beneficiary_status":  "changemakers.entitlement_api.save_beneficiary_status",
    "changemakers.entitlement_api.get_co_performance_v2":    "changemakers.entitlement_api.get_co_performance_v2",
    "changemakers.dashboard_api.get_dashboard_overview":     "changemakers.dashboard_api.get_dashboard_overview",
    "changemakers.dashboard_api.get_drilldown":              "changemakers.dashboard_api.get_drilldown",
}

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
    },
    "Individual Profile-WRP": {
        "before_save": "changemakers.wrp_status_logger.log_individual_status_change",
    },
    "Household Profile-WRP": {
        "before_save": "changemakers.wrp_status_logger.log_hh_status_change",
    },
}