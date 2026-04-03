frappe.query_reports["CMCHIS Delay Analysis"] = {
    filters: [
        {
            fieldname: "group_by",
            label: __("Group By"),
            fieldtype: "Select",
            options: "CO\nStreet\nIntervention Unit\nImplementing Org",
            default: "CO",
            reqd: 1,
        },
        {
            fieldname: "intervention_unit",
            label: __("Intervention Unit"),
            fieldtype: "Link",
            options: "Intervention Units-WRP",
            on_change: function () {
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
                return iu ? { filters: { intervention_units: iu } } : {};
            },
        },
    ],

    // Highlight rows where max_days_stuck is high
    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (column.fieldname === "max_days_stuck" && data && data.max_days_stuck > 30) {
            value = "<span style='color:red;font-weight:bold'>" + value + "</span>";
        }
        if (column.fieldname === "avg_days_pending" && data && data.avg_days_pending > 21) {
            value = "<span style='color:#cc6600'>" + value + "</span>";
        }
        if (column.fieldname === "avg_days_ready" && data && data.avg_days_ready > 14) {
            value = "<span style='color:#cc6600'>" + value + "</span>";
        }
        if (column.fieldname === "avg_days_applied" && data && data.avg_days_applied > 45) {
            value = "<span style='color:red;font-weight:bold'>" + value + "</span>";
        }
        return value;
    },
};
