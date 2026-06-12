// Custom on_change disables Frappe's built-in refresh-on-filter-change, so each
// handler must trigger the refresh itself. Debounced so a cascading clear
// (org -> cluster -> IU -> street) results in a single report run.
var co_cmchis_perf_refresh = frappe.utils.debounce(function () {
    frappe.query_report.refresh();
}, 300);

function co_cmchis_perf_clear(query_report, fieldnames) {
    fieldnames.forEach(function (fieldname) {
        if (query_report.get_filter_value(fieldname)) {
            query_report.set_filter_value(fieldname, "");
        }
    });
}

frappe.query_reports["CO CMCHIS Performance"] = {
    filters: [
        {
            fieldname: "organisation",
            label: __("Organisation"),
            fieldtype: "Link",
            options: "Implementing Org-WRP",
            on_change: function (query_report) {
                co_cmchis_perf_clear(query_report, ["cluster", "intervention_unit", "street"]);
                co_cmchis_perf_refresh();
            },
        },
        {
            fieldname: "cluster",
            label: __("Cluster"),
            fieldtype: "Link",
            options: "Cluster - WRP",
            on_change: function (query_report) {
                co_cmchis_perf_clear(query_report, ["intervention_unit", "street"]);
                co_cmchis_perf_refresh();
            },
        },
        {
            fieldname: "intervention_unit",
            label: __("Intervention Unit"),
            fieldtype: "Link",
            options: "Intervention Units-WRP",
            get_query: function () {
                var f = {};
                var org = frappe.query_report.get_filter_value("organisation");
                var cluster = frappe.query_report.get_filter_value("cluster");
                if (org) f.implementing_org = org;
                if (cluster) f.cluster = cluster;
                return { filters: f };
            },
            on_change: function (query_report) {
                co_cmchis_perf_clear(query_report, ["street"]);
                co_cmchis_perf_refresh();
            },
        },
        {
            fieldname: "street",
            label: __("Street"),
            fieldtype: "Link",
            options: "Street List  - WRP",
            get_query: function () {
                var f = {};
                var iu = frappe.query_report.get_filter_value("intervention_unit");
                var org = frappe.query_report.get_filter_value("organisation");
                var cluster = frappe.query_report.get_filter_value("cluster");
                if (iu) f.intervention_units = iu;
                if (org) f.implementing_org = org;
                if (cluster) f.cluster = cluster;
                return { filters: f };
            },
        },
    ],

    onload: function () {
        injectNeonDarkTheme();
    },

    // Street sub-rows start collapsed; click a CO row to expand
    initial_depth: 0,

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        var pct = parseFloat(data.pct_active) || 0;

        // CO name — neon purple
        if (column.fieldname === "co_name" && value) {
            value = "<span style='color:#e040fb;font-weight:700'>" + value + "</span>";
        }

        // % CMCHIS Active — neon glow
        if (column.fieldname === "pct_active") {
            var color = pct >= 30 ? "#00e676" : pct >= 15 ? "#ff6d00" : "#ff1744";
            value = "<span style='color:" + color + ";font-weight:900;font-size:1.05em;"
                + "text-shadow:0 0 8px " + color + "88'>" + value + "</span>";
        }

        // Active count — neon green
        if (column.fieldname === "active") {
            var n = parseInt(data.active) || 0;
            if (n > 0) {
                value = "<span style='color:#00e676;font-weight:700;"
                    + "text-shadow:0 0 6px #00e67655'>" + value + "</span>";
            }
        }

        // Rejected — neon red
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

        // Unvisited — orange if >20% of total
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
