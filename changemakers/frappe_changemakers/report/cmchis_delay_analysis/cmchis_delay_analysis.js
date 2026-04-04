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

    onload: function () {
        injectNeonDarkTheme();
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // max_days_stuck — neon red with glow
        if (column.fieldname === "max_days_stuck" && data.max_days_stuck !== undefined) {
            var d = parseFloat(data.max_days_stuck) || 0;
            if (d > 60) {
                value = "<span style='color:#ff1744;font-weight:900;"
                    + "text-shadow:0 0 10px #ff174488;font-size:1.05em'>" + value + "</span>";
            } else if (d > 30) {
                value = "<span style='color:#ff1744;font-weight:700;"
                    + "text-shadow:0 0 6px #ff174455'>" + value + "</span>";
            } else if (d > 14) {
                value = "<span style='color:#ff6d00;font-weight:600'>" + value + "</span>";
            }
        }

        // avg_days_pending — orange/red
        if (column.fieldname === "avg_days_pending" && data.avg_days_pending !== undefined) {
            var dp = parseFloat(data.avg_days_pending) || 0;
            if (dp > 30) {
                value = "<span style='color:#ff1744;font-weight:700'>" + value + "</span>";
            } else if (dp > 21) {
                value = "<span style='color:#ff6d00;font-weight:600'>" + value + "</span>";
            }
        }

        // avg_days_ready — yellow/orange when high
        if (column.fieldname === "avg_days_ready" && data.avg_days_ready !== undefined) {
            var dr = parseFloat(data.avg_days_ready) || 0;
            if (dr > 21) {
                value = "<span style='color:#ff6d00;font-weight:600'>" + value + "</span>";
            } else if (dr > 14) {
                value = "<span style='color:#ffd740;font-weight:600'>" + value + "</span>";
            }
        }

        // avg_days_applied — long waits in neon red
        if (column.fieldname === "avg_days_applied" && data.avg_days_applied !== undefined) {
            var da = parseFloat(data.avg_days_applied) || 0;
            if (da > 60) {
                value = "<span style='color:#ff1744;font-weight:900;"
                    + "text-shadow:0 0 8px #ff174466'>" + value + "</span>";
            } else if (da > 45) {
                value = "<span style='color:#ff1744;font-weight:700'>" + value + "</span>";
            } else if (da > 30) {
                value = "<span style='color:#ff6d00;font-weight:600'>" + value + "</span>";
            }
        }

        // Group label — neon purple
        if (column.fieldname === "group_label" && value) {
            value = "<span style='color:#e040fb;font-weight:700'>" + value + "</span>";
        }

        // Stage badge
        if (column.fieldname === "stage" && data.stage) {
            var stageColors = {
                "Reach Gap":       "#78909c",
                "Pending Docs":    "#ff6d00",
                "Ready to Apply":  "#ffd740",
                "Applied":         "#40c4ff",
                "CMCHIS Active":   "#00e676",
                "Rejected":        "#ff1744",
            };
            var sc = stageColors[data.stage] || "#aaa";
            value = "<span style='color:" + sc + ";font-weight:600'>" + value + "</span>";
        }

        return value;
    },
};
