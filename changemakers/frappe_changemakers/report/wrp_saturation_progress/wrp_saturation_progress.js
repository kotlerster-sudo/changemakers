frappe.query_reports["WRP Saturation Progress"] = {
	filters: [
		{
			fieldname: "co",
			label: __("Community Organiser"),
			fieldtype: "Link",
			options: "Staff details - WRP",
		},
		{
			fieldname: "ac",
			label: __("Area Coordinator (name)"),
			fieldtype: "Data",
		},
		{
			fieldname: "street",
			label: __("Street"),
			fieldtype: "Link",
			options: "Street List  - WRP",
		},
		{
			fieldname: "intervention_unit",
			label: __("Intervention Unit / Settlement"),
			fieldtype: "Link",
			options: "Intervention Units-WRP",
		},
		{
			fieldname: "implementing_org",
			label: __("Implementing Organisation"),
			fieldtype: "Data",
		},
		{
			fieldname: "from_date",
			label: __("From Date"),
			fieldtype: "Date",
		},
		{
			fieldname: "to_date",
			label: __("To Date"),
			fieldtype: "Date",
		},
	],
};
