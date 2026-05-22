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
            fieldname: "co",
            label: __("CO"),
            fieldtype: "Link",
            options: "Staff details - WRP",
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        if (data.indent === 0) {
            var pct = parseFloat(data.coverage_pct) || 0;
            if (column.fieldname === "label") {
                var icon = pct >= 80 ? "🟢 " : pct >= 50 ? "🟠 " : "🔴 ";
                value = "<span style='font-weight:700'>" + icon + (data.label || "") + "</span>";
                return value;
            }
            if (column.fieldname === "coverage_pct") {
                var color = pct >= 80 ? "#16a34a" : pct >= 50 ? "#f97316" : "#dc2626";
                value = "<span style='color:" + color + ";font-weight:700'>" + value + "</span>";
            }
        }

        if (data.indent === 1 && column.fieldname === "label") {
            value = "<span style='color:#666'>" + (data.label || "") + "</span>";
        }

        return value;
    },

    initial_depth: 1,
};
