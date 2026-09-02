// DPDP export control (Mathew, 3-Sep-2026): before any export leaves the MIS, show the notice and
// ask for a one-line reason. System Managers see the notice but are not asked for the reason.
// Server side (changemakers/dpdp_export.py) refuses an export that arrives without one.
(function () {
	const CMDS = {
		"frappe.desk.reportview.export_query": 1,
		"frappe.desk.query_report.export_query": 1,
	};
	const DATA_EXPORT = "frappe.core.doctype.data_export.exporter.export_data";

	function exempt() {
		return (frappe.user_roles || []).indexOf("System Manager") > -1 || frappe.session.user === "Administrator";
	}

	function notice_html() {
		return (
			'<div style="border-left:4px solid #b45f06;background:#fbebd3;padding:10px 12px;border-radius:6px;font-size:13px;line-height:1.5;margin-bottom:8px">' +
			"<b>Before you download</b><br>" +
			"As per the Digital Personal Data Protection (DPDP) Act, this data must not be shared outside the organisation. " +
			"Download only when it is critical for your work. If you only need a report, ask the Foundation MIS team for it. " +
			"Every export is recorded with your name, the date, what was exported and the reason you give here." +
			"</div>"
		);
	}

	function ask(then) {
		const fields = [{ fieldtype: "HTML", fieldname: "notice", options: notice_html() }];
		if (!exempt()) {
			fields.push({
				fieldtype: "Small Text",
				fieldname: "reason",
				label: __("Why do you need this data? One line."),
				reqd: 1,
				description: __("For example: monthly report to the PM, verification list for the AC, audit query."),
			});
		}
		const d = new frappe.ui.Dialog({
			title: __("Export data"),
			fields: fields,
			primary_action_label: __("Export"),
			primary_action(values) {
				const reason = (values.reason || "").trim();
				if (!exempt() && reason.length < 5) {
					frappe.msgprint(__("Please give a reason of at least a few words."));
					return;
				}
				d.hide();
				then(reason || "System Manager export");
			},
		});
		d.show();
	}

	// report builder / list view / query report exports all go through open_url_post
	if (window.open_url_post && !window.open_url_post.__dpdp) {
		const original = window.open_url_post;
		const wrapped = function (url, params, new_window) {
			if (params && CMDS[params.cmd] && !params.export_reason) {
				return ask(function (reason) {
					params.export_reason = reason;
					original(url, params, new_window);
				});
			}
			return original(url, params, new_window);
		};
		wrapped.__dpdp = true;
		window.open_url_post = wrapped;
	}

	// the Data Export tool posts to the method URL directly
	if (window.open_url_post) {
		const inner = window.open_url_post;
		const wrapped2 = function (url, params, new_window) {
			if (typeof url === "string" && url.indexOf(DATA_EXPORT) > -1 && params && !params.export_reason) {
				return ask(function (reason) {
					params.export_reason = reason;
					inner(url, params, new_window);
				});
			}
			return inner(url, params, new_window);
		};
		wrapped2.__dpdp = true;
		window.open_url_post = wrapped2;
	}

	// anything that calls the data export method through frappe.call
	if (frappe.call && !frappe.call.__dpdp) {
		const original_call = frappe.call;
		const wrapped_call = function (opts) {
			if (opts && typeof opts === "object" && opts.method === DATA_EXPORT && !(opts.args && opts.args.export_reason)) {
				const o = opts;
				ask(function (reason) {
					o.args = Object.assign({}, o.args || {}, { export_reason: reason });
					original_call(o);
				});
				return;
			}
			return original_call.apply(this, arguments);
		};
		wrapped_call.__dpdp = true;
		frappe.call = wrapped_call;
	}
})();
