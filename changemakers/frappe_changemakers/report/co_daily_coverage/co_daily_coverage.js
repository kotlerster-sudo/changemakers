frappe.query_reports["CO Daily Coverage"] = {
    filters: [
        {
            fieldname: "date",
            label: __("Date"),
            fieldtype: "Date",
            default: frappe.datetime.get_today(),
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

        // Bold CO rows
        if (data.bold && column.fieldname === "label") {
            value = "<strong>" + value + "</strong>";
        }

        // Colour coverage % — red below 50%, amber 50–79%, green 80%+
        if (column.fieldname === "coverage_pct" && data.indent === 0) {
            var pct = data.coverage_pct || 0;
            var color = pct >= 80 ? "green" : pct >= 50 ? "#cc6600" : "red";
            value = "<span style='color:" + color + ";font-weight:bold'>" + value + "</span>";
        }

        // Dim household rows slightly
        if (data.indent === 1) {
            value = "<span style='color:#555'>" + value + "</span>";
        }

        return value;
    },

    // Start with all rows visible; managers can scroll through
    initial_depth: 1,
};
