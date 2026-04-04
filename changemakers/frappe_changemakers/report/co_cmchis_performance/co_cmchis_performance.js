frappe.query_reports["CO CMCHIS Performance"] = {
    filters: [
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
                if (iu) {
                    return { filters: { intervention_units: iu } };
                }
                return {};
            },
        },
    ],

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        var pct = parseFloat(data.pct_active) || 0;

        // Subtle row background tint based on performance
        var rowBg = pct >= 30
            ? "rgba(0,230,118,0.06)"
            : pct >= 15
            ? "rgba(255,109,0,0.06)"
            : "rgba(255,23,68,0.05)";

        // CO name — neon purple badge
        if (column.fieldname === "co_name" && value) {
            value = "<span style='color:#e040fb;font-weight:700'>" + value + "</span>";
        }

        // % CMCHIS Active — neon colour + glow
        if (column.fieldname === "pct_active") {
            var color = pct >= 30 ? "#00e676" : pct >= 15 ? "#ff6d00" : "#ff1744";
            value = "<span style='color:" + color + ";font-weight:900;font-size:1.05em;"
                + "text-shadow:0 0 8px " + color + "88'>" + value + "</span>";
        }

        // Active count — neon green if > 0
        if (column.fieldname === "active") {
            var n = parseInt(data.active) || 0;
            if (n > 0) {
                value = "<span style='color:#00e676;font-weight:700'>" + value + "</span>";
            }
        }

        // Rejected count — neon red if > 0
        if (column.fieldname === "rejected") {
            var r = parseInt(data.rejected) || 0;
            if (r > 0) {
                value = "<span style='color:#ff1744;font-weight:600'>" + value + "</span>";
            }
        }

        // Applied — neon blue
        if (column.fieldname === "applied") {
            var a = parseInt(data.applied) || 0;
            if (a > 0) {
                value = "<span style='color:#40c4ff;font-weight:600'>" + value + "</span>";
            }
        }

        // Unvisited — orange if significant (>20% of total)
        if (column.fieldname === "unvisited") {
            var total = parseInt(data.total_hh) || 1;
            var unv = parseInt(data.unvisited) || 0;
            if (unv / total > 0.2) {
                value = "<span style='color:#ff6d00;font-weight:600'>" + value + "</span>";
            }
        }

        return value;
    },
};
