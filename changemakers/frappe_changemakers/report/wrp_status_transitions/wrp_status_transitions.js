frappe.query_reports["WRP Status Transitions"] = {
    filters: [
        {
            fieldname: "period",
            label: __("Period"),
            fieldtype: "Select",
            options: ["Last Week", "Last Month", "Last Quarter", "Custom"],
            default: "Last Month",
            reqd: 1,
            on_change: function () {
                const period = frappe.query_report.get_filter_value("period");
                const show = period === "Custom";
                frappe.query_report.toggle_filter_display("from_date", !show);
                frappe.query_report.toggle_filter_display("to_date",   !show);
                if (!show) {
                    frappe.query_report.set_filter_value("from_date", "");
                    frappe.query_report.set_filter_value("to_date",   "");
                }
            },
        },
        {
            fieldname: "from_date",
            label: __("From Date"),
            fieldtype: "Date",
            hidden: 1,
        },
        {
            fieldname: "to_date",
            label: __("To Date"),
            fieldtype: "Date",
            hidden: 1,
        },
        {
            fieldname: "field_changed",
            label: __("Status Field"),
            fieldtype: "Select",
            options: ["All", "aadhaar_status", "income_status", "cmchis_status"],
            default: "All",
        },
        {
            fieldname: "group_by",
            label: __("Group By"),
            fieldtype: "Select",
            options: ["CO", "AC", "Project Manager", "Intervention Unit", "Street", "Implementing Org"],
            default: "CO",
            reqd: 1,
        },
        {
            fieldname: "intervention_unit",
            label: __("Intervention Unit"),
            fieldtype: "Link",
            options: "Intervention Units-WRP",
        },
        {
            fieldname: "street",
            label: __("Street"),
            fieldtype: "Link",
            options: "Street List  - WRP",
        },
    ],

    get_chart_data: function (columns, result) {
        // Chart is returned server-side — no extra work needed here
        return null;
    },

    formatter: function (value, row, column, data, default_formatter) {
        value = default_formatter(value, row, column, data);
        if (!data) return value;

        // Colour-code the Transition column
        if (column.fieldname === "detail" && data.detail) {
            if (data.detail.includes("CMCHIS Active")) {
                value = `<span style="color:#22C55E;font-weight:600">${data.detail}</span>`;
            } else if (data.detail.includes("Aadhaar Received") || data.detail.includes("Income Cert")) {
                value = `<span style="color:#4169E1">${data.detail}</span>`;
            } else if (data.detail.includes("Rejected")) {
                value = `<span style="color:#EF4444">${data.detail}</span>`;
            }
        }

        // Bold & background for group rows
        if (data.bold) {
            value = `<b>${value}</b>`;
        }

        return value;
    },
};
