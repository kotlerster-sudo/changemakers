frappe.query_reports["Entitlement Daily Update Report"] = {
    filters: [
        {
            fieldname: "entitlement_code",
            label: __("Entitlement"),
            fieldtype: "Link",
            options: "Entitlement Config",
            reqd: 1,
            default: "E2",
        },
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
        {
            fieldname: "co",
            label: __("CO"),
            fieldtype: "Link",
            options: "Staff details - WRP",
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // CO summary rows
        if (data.indent === 0) {
            var pct = parseFloat(data.coverage_pct) || 0;

            if (column.fieldname === "label") {
                var icon = pct >= 80 ? "🟢 " : pct >= 50 ? "🟠 " : "🔴 ";
                return "<span style='color:#e040fb;font-weight:700'>" + icon + (data.label || "") + "</span>";
            }
            if (column.fieldname === "coverage_pct") {
                var color = pct >= 80 ? "#16a34a" : pct >= 50 ? "#f97316" : "#dc2626";
                return "<span style='color:" + color + ";font-weight:700'>" + value + "</span>";
            }
            if (column.fieldname === "updated" && parseInt(data.updated) > 0) {
                return "<span style='color:#22c55e;font-weight:700'>" + value + "</span>";
            }
            // Transition summary counts — highlight if non-zero
            var transCols = {
                to_in_progress: "#f59e0b",
                to_docs_ready:  "#8b5cf6",
                to_applied:     "#3b82f6",
                to_goal:        "#22c55e",
                to_closed:      "#ef4444",
            };
            if (transCols[column.fieldname] && parseInt(data[column.fieldname]) > 0) {
                return "<span style='color:" + transCols[column.fieldname] + ";font-weight:700'>" + value + "</span>";
            }
        }

        // Beneficiary detail rows
        if (data.indent === 1) {
            if (column.fieldname === "label") {
                return "<span style='color:#aaa'>" + (data.label || "") + "</span>";
            }

            var bucketColors = {
                "Unvisited":   "#6b7280",
                "In Progress": "#f59e0b",
                "Docs Ready":  "#8b5cf6",
                "Applied":     "#3b82f6",
                "Goal":        "#22c55e",
                "Closed":      "#ef4444",
            };
            if (column.fieldname === "bucket" && data.bucket) {
                var bc = bucketColors[data.bucket] || "#aaa";
                return "<span style='color:" + bc + ";font-weight:600'>" + (data.bucket || "") + "</span>";
            }

            // Highlight transition cell for this row
            var transColColors = {
                to_in_progress: "#f59e0b",
                to_docs_ready:  "#8b5cf6",
                to_applied:     "#3b82f6",
                to_goal:        "#22c55e",
                to_closed:      "#ef4444",
            };
            if (transColColors[column.fieldname] && parseInt(data[column.fieldname]) === 1) {
                return "<span style='color:" + transColColors[column.fieldname] + ";font-weight:700'>✓</span>";
            }
        }

        return value;
    },

    initial_depth: 1,
};
