"""DPDP export control (Mathew, 3-Sep-2026).

Every export of data out of the MIS - report builder, query report, Data Export tool - must carry a
one-line reason from the person exporting. The reason is stored on the Access Log row that Frappe
already writes for the export, so the log answers who, what, when and WHY. System Managers
(Foundation MIS team) are exempt from the reason; the notice is still shown to everyone.

Wired through hooks.override_whitelisted_methods; the browser side (public/js/dpdp_export.js) asks
for the reason before the download starts, and this file refuses an export that arrives without one.
Reversible: remove the three hook lines and the app_include_js entry.
"""
import frappe
from frappe import _

EXEMPT_ROLES = ("System Manager", "Administrator")
MIN_LEN = 5


def _exempt():
	return frappe.session.user == "Administrator" or any(r in frappe.get_roles() for r in EXEMPT_ROLES)


def _take_reason(source=None):
	"""Pull export_reason out of the request so the original export never sees it; enforce it."""
	src = source if source is not None else frappe.local.form_dict
	reason = (src.pop("export_reason", None) or "").strip()
	if len(reason) < MIN_LEN and not _exempt():
		frappe.throw(
			_("Say in one line why you need this data before exporting. As per the DPDP Act, MIS data must "
			  "not be shared outside the organisation. If you only need a report, ask the Foundation MIS team."),
			title=_("Export needs a reason"),
		)
	return reason[:500]


def _stamp(reason):
	"""The export writes its own Access Log row; put the reason on the newest one for this user."""
	if not reason:
		return
	try:
		name = frappe.db.get_value(
			"Access Log", {"user": frappe.session.user}, "name", order_by="creation desc"
		)
		if name and frappe.db.has_column("Access Log", "export_reason"):
			frappe.db.set_value("Access Log", name, "export_reason", reason, update_modified=False)
			frappe.db.commit()
	except Exception:
		frappe.log_error("DPDP export reason not stamped", frappe.get_traceback())


@frappe.whitelist()
def reportview_export_query():
	"""Report builder / list view export."""
	reason = _take_reason()
	from frappe.desk.reportview import export_query
	out = export_query()
	_stamp(reason)
	return out


@frappe.whitelist()
def query_report_export_query():
	"""Query / script report export."""
	reason = _take_reason()
	from frappe.desk.query_report import export_query
	out = export_query()
	_stamp(reason)
	return out


@frappe.whitelist()
def data_export_export_data(**kwargs):
	"""Data Export tool."""
	reason = _take_reason(kwargs)
	from frappe.core.doctype.data_export.exporter import export_data
	out = export_data(**kwargs)
	_stamp(reason)
	return out
