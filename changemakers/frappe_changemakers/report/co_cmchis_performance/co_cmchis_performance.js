frappe.query_reports["CO CMCHIS Performance"] = {
    filters: [
        {
            fieldname: "intervention_unit",
            label: __("Intervention Unit"),
            fieldtype: "Link",
            options: "Intervention Units-WRP",
            on_change: function () {
                // Clear street when IU changes so the dependent query re-runs
                frappe.query_report.set_filter_value("street", "");
            },
        },
        {
            fieldname: "street",
            label: __("Street"),
            fieldtype: "Link",
            options: "Street List  - WRP",
            get_query: function () {
                var iu = frappe.query_report.get_filter_value("intervention_unit");
                if (iu) {
                    return {
                        filters: { intervention_units: iu },
                    };
                }
                return {};
            },
        },
    ],
};
