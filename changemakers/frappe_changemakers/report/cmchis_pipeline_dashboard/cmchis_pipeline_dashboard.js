frappe.query_reports["CMCHIS Pipeline Dashboard"] = {
    filters: [
        {
            fieldname: "group_by",
            label: __("Group By"),
            fieldtype: "Select",
            options: "CO\nAC\nProject Manager\nIntervention Unit\nStreet\nImplementing Org",
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

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // Bold group rows
        if (data.bold && column.fieldname === "label") {
            value = "<strong>" + value + "</strong>";
        }

        // Colour % Active
        if (column.fieldname === "pct_active" && data.indent === 0 && data.pct_active !== "") {
            var pct = parseFloat(data.pct_active) || 0;
            var color = pct >= 30 ? "green" : pct >= 15 ? "#cc6600" : "red";
            value = "<span style='color:" + color + ";font-weight:bold'>" + value + "</span>";
        }

        // Colour stage badges on detail rows
        if (column.fieldname === "stage" && data.indent === 1 && data.stage) {
            var colors = {
                "Reach Gap (Unvisited)":       "#999",
                "No Update (Pending Docs)":    "#cc6600",
                "Documented (Ready to Apply)": "#0070c0",
                "Applied":                     "#7030a0",
                "CMCHIS Active":               "green",
                "Rejected":                    "red",
            };
            var bg = colors[data.stage] || "#555";
            value = "<span style='color:" + bg + ";font-weight:600'>" + (data.stage || "") + "</span>";
        }

        // Dim individual rows
        if (data.indent === 1 && column.fieldname === "label") {
            value = "<span style='color:#444'>" + value + "</span>";
        }

        return value;
    },

    initial_depth: 1,
};
