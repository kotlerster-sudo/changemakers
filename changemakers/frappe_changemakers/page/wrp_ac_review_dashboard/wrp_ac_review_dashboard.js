frappe.pages["wrp-ac-review-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "AC Review Dashboard",
		single_column: true,
	});

	// ── Filters ──────────────────────────────────────────────────────────────
	const $status = page.add_field({
		fieldtype: "Select",
		fieldname: "status",
		label: "Status",
		options: "\nPending AC Review\nCleared – Will Apply\nBlocked – No Resolution",
		default: "Pending AC Review",
		change() { render(); },
	});

	const $street = page.add_field({
		fieldtype: "Link",
		fieldname: "street",
		label: "Street",
		options: "Street List  - WRP",
		change() { render(); },
	});

	const $iu = page.add_field({
		fieldtype: "Data",
		fieldname: "intervention_unit",
		label: "Intervention Unit",
		change() { render(); },
	});

	page.add_inner_button("Refresh", () => render());

	// ── Container ─────────────────────────────────────────────────────────────
	const $container = $(`
		<div style="padding:16px">
			<div id="ac-review-summary"
				 style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap"></div>
			<div id="ac-review-table"></div>
		</div>
	`).appendTo($(wrapper).find(".page-content"));

	// ── Render ────────────────────────────────────────────────────────────────
	function render() {
		const status = $status.get_value();
		const street = $street.get_value();
		const iu     = $iu.get_value();

		frappe.call({
			method: "changemakers.dashboard_api.get_ac_review_list",
			args: { status: status || "", street: street || "", intervention_unit: iu || "" },
			callback({ message: rows }) {
				renderSummary(rows);
				renderTable(rows, status);
			},
		});
	}

	// ── Summary cards ─────────────────────────────────────────────────────────
	function renderSummary(rows) {
		const pending  = rows.filter(r => r.status === "Pending AC Review").length;
		const cleared  = rows.filter(r => r.status === "Cleared – Will Apply").length;
		const blocked  = rows.filter(r => r.status === "Blocked – No Resolution").length;
		const oldest   = rows.length
			? Math.max(...rows.map(r => r.days_pending || 0))
			: 0;

		const card = (label, val, color) =>
			`<div style="background:${color};border-radius:8px;padding:12px 20px;min-width:120px;text-align:center">
				<div style="font-size:22px;font-weight:700;color:#fff">${val}</div>
				<div style="font-size:12px;color:rgba(255,255,255,.85)">${label}</div>
			</div>`;

		$("#ac-review-summary").html(
			card("Pending", pending,  "#e74c3c") +
			card("Cleared", cleared,  "#27ae60") +
			card("Blocked", blocked,  "#7f8c8d") +
			card("Oldest (days)", oldest, "#2980b9")
		);
	}

	// ── Table ─────────────────────────────────────────────────────────────────
	function renderTable(rows, statusFilter) {
		if (!rows.length) {
			$("#ac-review-table").html(
				`<p style="color:#888;margin-top:24px">No records found.</p>`
			);
			return;
		}

		const isPending = !statusFilter || statusFilter === "Pending AC Review";

		const header = `
			<thead>
				<tr style="background:#f4f4f4;font-size:12px;text-transform:uppercase;color:#555">
					<th style="padding:8px 12px">Household</th>
					<th style="padding:8px 12px">Respondent</th>
					<th style="padding:8px 12px">Street</th>
					<th style="padding:8px 12px">CO</th>
					<th style="padding:8px 12px">Visits</th>
					<th style="padding:8px 12px">Escalated On</th>
					<th style="padding:8px 12px">Days</th>
					<th style="padding:8px 12px">Status</th>
					${isPending ? `<th style="padding:8px 12px">Action</th>` : ""}
				</tr>
			</thead>`;

		const bodyRows = rows.map((r, i) => {
			const bg     = i % 2 === 0 ? "#fff" : "#fafafa";
			const dayBadge = r.days_pending > 7
				? `<span style="color:#e74c3c;font-weight:600">${r.days_pending}</span>`
				: r.days_pending;
			const statusBadge = statusBadgeHtml(r.status);
			const actions = isPending
				? `<td style="padding:8px 12px;white-space:nowrap">
					<button class="btn btn-xs btn-success ac-action"
						data-name="${r.name}" data-status="Cleared – Will Apply"
						style="margin-right:4px">Cleared</button>
					<button class="btn btn-xs btn-danger ac-action"
						data-name="${r.name}" data-status="Blocked – No Resolution">Blocked</button>
				  </td>`
				: "";

			return `<tr style="background:${bg};font-size:13px">
				<td style="padding:8px 12px;font-family:monospace">${r.household}</td>
				<td style="padding:8px 12px">${r.respondent || "—"}</td>
				<td style="padding:8px 12px">${r.street || "—"}</td>
				<td style="padding:8px 12px">${r.co || "—"}</td>
				<td style="padding:8px 12px;text-align:center">${r.visit_count}</td>
				<td style="padding:8px 12px">${r.escalation_date}</td>
				<td style="padding:8px 12px;text-align:center">${dayBadge}</td>
				<td style="padding:8px 12px">${statusBadge}</td>
				${actions}
			</tr>`;
		}).join("");

		const table = `
			<table style="width:100%;border-collapse:collapse;border:1px solid #eee;border-radius:8px;overflow:hidden">
				${header}
				<tbody>${bodyRows}</tbody>
			</table>`;

		$("#ac-review-table").html(table);

		// ── Action buttons ────────────────────────────────────────────────────
		$(".ac-action").on("click", function () {
			const name   = $(this).data("name");
			const status = $(this).data("status");

			frappe.prompt(
				{
					fieldtype: "Small Text",
					fieldname: "ac_notes",
					label: "Notes (optional)",
				},
				({ ac_notes }) => {
					frappe.call({
						method: "changemakers.dashboard_api.resolve_ac_review",
						args: { name, status, ac_notes: ac_notes || "" },
						callback() {
							frappe.show_alert({ message: "Saved", indicator: "green" });
							render();
						},
					});
				},
				`Mark as: ${status}`,
				"Confirm"
			);
		});
	}

	function statusBadgeHtml(status) {
		const map = {
			"Pending AC Review":      ["#e74c3c", "Pending"],
			"Cleared – Will Apply":   ["#27ae60", "Cleared"],
			"Blocked – No Resolution":["#7f8c8d", "Blocked"],
		};
		const [color, label] = map[status] || ["#ccc", status];
		return `<span style="background:${color};color:#fff;border-radius:4px;padding:2px 8px;font-size:11px">${label}</span>`;
	}

	render();
};
