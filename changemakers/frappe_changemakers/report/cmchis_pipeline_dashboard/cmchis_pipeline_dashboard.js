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

    onload: function () {
        injectNeonDarkTheme();
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // ── Group summary rows (indent 0) ─────────────────────────────────────
        if (data.indent === 0) {
            if (column.fieldname === "label") {
                value = "<strong style='color:#e040fb;font-size:1.02em'>"
                    + (data.label || "") + "</strong>";
                return value;
            }

            if (column.fieldname === "pct_active" && data.pct_active !== "") {
                var pct = parseFloat(data.pct_active) || 0;
                var color = pct >= 30 ? "#00e676" : pct >= 15 ? "#ff6d00" : "#ff1744";
                value = "<span style='color:" + color + ";font-weight:900;font-size:1.08em;"
                    + "text-shadow:0 0 10px " + color + "88'>" + value + "</span>";
                return value;
            }

            if (column.fieldname === "active") {
                var n = parseInt(data.active) || 0;
                if (n > 0) {
                    value = "<span style='color:#00e676;font-weight:700;"
                        + "text-shadow:0 0 6px #00e67655'>" + value + "</span>";
                }
            }
            if (column.fieldname === "applied") {
                var a = parseInt(data.applied) || 0;
                if (a > 0) {
                    value = "<span style='color:#40c4ff;font-weight:600'>" + value + "</span>";
                }
            }
            if (column.fieldname === "reach_gap") {
                var rg = parseInt(data.reach_gap) || 0;
                if (rg > 0) {
                    value = "<span style='color:#78909c;font-weight:600'>" + value + "</span>";
                }
            }
            if (column.fieldname === "no_update") {
                var nu = parseInt(data.no_update) || 0;
                if (nu > 0) {
                    value = "<span style='color:#ff6d00;font-weight:600'>" + value + "</span>";
                }
            }
            if (column.fieldname === "both_missing" || column.fieldname === "no_aadhaar" || column.fieldname === "no_income") {
                var dg = parseInt(data[column.fieldname]) || 0;
                if (dg > 0) {
                    value = "<span style='color:#ff8f00;font-weight:600'>" + value + "</span>";
                }
            }
            if (column.fieldname === "documented") {
                var doc = parseInt(data.documented) || 0;
                if (doc > 0) {
                    value = "<span style='color:#ffd740;font-weight:700'>" + value + "</span>";
                }
            }
            if (column.fieldname === "rejected") {
                var rej = parseInt(data.rejected) || 0;
                if (rej > 0) {
                    value = "<span style='color:#ff1744;font-weight:600'>" + value + "</span>";
                }
            }
        }

        // ── Individual detail rows (indent 1) ─────────────────────────────────
        if (data.indent === 1) {
            if (column.fieldname === "label") {
                value = "<span style='color:#aaa'>" + (data.label || "") + "</span>";
                return value;
            }

            if (column.fieldname === "sub_label" && data.sub_label) {
                value = "<span style='color:#ce93d8;font-size:0.88em'>" + data.sub_label + "</span>";
            }

            if (column.fieldname === "stage" && data.stage) {
                var stageMap = {
                    "Reach Gap (Unvisited)":    { color: "#78909c" },
                    "No Update (Pending Docs)": { color: "#ff6d00" },
                    "Both Docs Missing":        { color: "#ff8f00" },
                    "Aadhaar Missing":          { color: "#ff8f00" },
                    "Income Cert Missing":      { color: "#ff8f00" },
                    "Ready to Apply":           { color: "#ffd740" },
                    "Applied":                  { color: "#40c4ff" },
                    "CMCHIS Active":            { color: "#00e676", glow: true },
                    "Rejected":                 { color: "#ff1744" },
                };
                var s = stageMap[data.stage] || { color: "#aaa" };
                var style = "color:" + s.color + ";font-weight:700";
                if (s.glow) {
                    style += ";text-shadow:0 0 8px " + s.color + "88";
                }
                value = "<span style='" + style + "'>" + data.stage + "</span>";
            }
        }

        return value;
    },

    initial_depth: 1,
};
