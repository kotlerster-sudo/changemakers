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

    onload: function () {
        injectNeonDarkTheme();
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // CO summary rows (indent 0)
        if (data.indent === 0) {
            var pct = parseFloat(data.coverage_pct) || 0;

            if (column.fieldname === "label") {
                var icon = pct >= 80 ? "🟢 " : pct >= 50 ? "🟠 " : "🔴 ";
                value = "<span style='color:#e040fb;font-weight:700'>"
                    + icon + (data.label || "") + "</span>";
                return value;
            }

            if (column.fieldname === "coverage_pct") {
                var color = pct >= 80 ? "#00e676" : pct >= 50 ? "#ff6d00" : "#ff1744";
                value = "<span style='color:" + color + ";font-weight:900;font-size:1.08em;"
                    + "text-shadow:0 0 10px " + color + "88'>" + value + "</span>";
            }

            if (column.fieldname === "visited") {
                var v = parseInt(data.visited) || 0;
                if (v > 0) {
                    value = "<span style='color:#00e676;font-weight:700'>" + value + "</span>";
                }
            }
        }

        // Individual detail rows (indent 1)
        if (data.indent === 1) {
            if (column.fieldname === "label") {
                value = "<span style='color:#aaa'>" + (data.label || "") + "</span>";
                return value;
            }

            if (column.fieldname === "stage") {
                var stageColors = {
                    "CMCHIS Active":       "#00e676",
                    "Applied":             "#40c4ff",
                    "Ready to Apply":      "#ffd740",
                    "Both Docs Missing":   "#ff6d00",
                    "Aadhaar Missing":     "#ff8f00",
                    "Income Cert Missing": "#ff8f00",
                    "No Update":           "#ff6d00",
                    "First Visit":         "#b388ff",
                    "Rejected":            "#ff1744",
                };
                var sc = stageColors[data.stage] || "#aaa";
                value = "<span style='color:" + sc + ";font-weight:600'>"
                    + (data.stage || "") + "</span>";
            }

            if (column.fieldname === "visit_type") {
                var vtColors = {
                    "first":   "#b388ff",
                    "doc":     "#40c4ff",
                    "regular": "#78909c",
                };
                var vtLabels = {
                    "first":   "First Visit",
                    "doc":     "Doc Follow-up",
                    "regular": "Regular",
                };
                var vt = data.visit_type || "";
                var vtc = vtColors[vt] || "#aaa";
                var vtl = vtLabels[vt] || vt;
                value = "<span style='color:" + vtc + ";font-weight:600;font-size:0.9em'>"
                    + vtl + "</span>";
            }
        }

        return value;
    },

    initial_depth: 1,
};
