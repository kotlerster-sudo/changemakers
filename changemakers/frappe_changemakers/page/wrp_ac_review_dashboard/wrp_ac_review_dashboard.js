frappe.pages["wrp-ac-review-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "AC Review Dashboard",
		single_column: true,
	});

	// ── Filter state ──────────────────────────────────────────────────────────
	let _filterMeta = { ius: [], streets: [], acs: [] };

	// ── Filters (order matters for cascade) ──────────────────────────────────
	const $iu = page.add_field({
		fieldtype: "Select",
		fieldname: "intervention_unit",
		label: "Intervention Unit",
		options: "",
		change() { onIUChange(); },
	});

	const $ac = page.add_field({
		fieldtype: "Select",
		fieldname: "ac",
		label: "AC",
		options: "",
		change() { onACChange(); },
	});

	const $street = page.add_field({
		fieldtype: "Select",
		fieldname: "street",
		label: "Street",
		options: "",
		change() { render(); },
	});

	const $status = page.add_field({
		fieldtype: "Select",
		fieldname: "status",
		label: "Status",
		options: "\nPending AC Review\nCleared – Will Apply\nBlocked – No Resolution",
		default: "Pending AC Review",
		change() { render(); },
	});

	page.add_inner_button("Refresh", () => loadFilters());

	// ── Container ─────────────────────────────────────────────────────────────
	$(`<div style="padding:16px">
		<div id="ac-review-summary" style="display:flex;gap:16px;margin-bottom:16px;flex-wrap:wrap"></div>
		<div id="ac-review-table"></div>
	</div>`).appendTo($(wrapper).find(".page-content"));

	// ── Filter population & cascade ───────────────────────────────────────────
	function loadFilters() {
		frappe.call({
			method: "changemakers.dashboard_api.get_ac_review_filter_meta",
			callback({ message }) {
				_filterMeta = message || { ius: [], streets: [], acs: [] };
				populateIU();
				populateAC();
				populateStreet();
				render();
			},
		});
	}

	function populateIU() {
		const cur = $iu.get_value();
		const opts = [""].concat(_filterMeta.ius);
		$iu.df.options = opts.join("\n");
		$iu.$wrapper.find("select").empty();
		opts.forEach(o => $iu.$wrapper.find("select").append(`<option value="${o}">${o || "All IUs"}</option>`));
		if (opts.includes(cur)) $iu.set_value(cur);
	}

	function populateAC(iu) {
		const cur = $ac.get_value();
		const acs = iu
			? _filterMeta.acs.filter(a => a.iu === iu).map(a => a.ac)
			: _filterMeta.acs.map(a => a.ac);
		const unique = [""].concat([...new Set(acs)].sort());
		$ac.$wrapper.find("select").empty();
		unique.forEach(o => $ac.$wrapper.find("select").append(`<option value="${o}">${o || "All ACs"}</option>`));
		if (unique.includes(cur)) $ac.set_value(cur); else $ac.set_value("");
	}

	function populateStreet(iu, ac) {
		const cur = $street.get_value();
		let streets = _filterMeta.streets;
		if (iu)  streets = streets.filter(s => s.iu === iu);
		if (ac)  streets = streets.filter(s => s.ac === ac);
		const names = [""].concat(streets.map(s => s.name).sort());
		$street.$wrapper.find("select").empty();
		names.forEach(o => $street.$wrapper.find("select").append(`<option value="${o}">${o || "All Streets"}</option>`));
		if (names.includes(cur)) $street.set_value(cur); else $street.set_value("");
	}

	function onIUChange() {
		const iu = $iu.get_value();
		populateAC(iu);
		populateStreet(iu, "");
		render();
	}

	function onACChange() {
		const iu = $iu.get_value();
		const ac = $ac.get_value();
		populateStreet(iu, ac);
		render();
	}

	// ── Data fetch & render ───────────────────────────────────────────────────
	function render() {
		frappe.call({
			method: "changemakers.dashboard_api.get_ac_review_list",
			args: {
				status:            $status.get_value() || "",
				street:            $street.get_value() || "",
				intervention_unit: $iu.get_value() || "",
				ac:                $ac.get_value() || "",
			},
			callback({ message: rows }) {
				renderSummary(rows);
				renderTable(rows, $status.get_value());
			},
		});
	}

	// ── Summary cards ─────────────────────────────────────────────────────────
	function renderSummary(rows) {
		const pending = rows.filter(r => r.status === "Pending AC Review").length;
		const cleared = rows.filter(r => r.status === "Cleared – Will Apply").length;
		const blocked = rows.filter(r => r.status === "Blocked – No Resolution").length;
		const oldest  = rows.length ? Math.max(...rows.map(r => r.days_pending || 0)) : 0;

		const card = (label, val, color) =>
			`<div style="background:${color};border-radius:8px;padding:12px 20px;min-width:120px;text-align:center">
				<div style="font-size:22px;font-weight:700;color:#fff">${val}</div>
				<div style="font-size:12px;color:rgba(255,255,255,.85)">${label}</div>
			</div>`;

		$("#ac-review-summary").html(
			card("Pending",      pending, "#e74c3c") +
			card("Cleared",      cleared, "#27ae60") +
			card("Blocked",      blocked, "#7f8c8d") +
			card("Oldest (days)",oldest,  "#2980b9")
		);
	}

	// ── Table ─────────────────────────────────────────────────────────────────
	function renderTable(rows, statusFilter) {
		if (!rows.length) {
			$("#ac-review-table").html(`<p style="color:#888;margin-top:24px">No records found.</p>`);
			return;
		}

		const isPending = !statusFilter || statusFilter === "Pending AC Review";

		const header = `<thead>
			<tr style="background:#f4f4f4;font-size:12px;text-transform:uppercase;color:#555">
				<th style="padding:8px 12px">Household</th>
				<th style="padding:8px 12px">Respondent</th>
				<th style="padding:8px 12px">Street</th>
				<th style="padding:8px 12px">AC</th>
				<th style="padding:8px 12px">CO</th>
				<th style="padding:8px 12px">Visits</th>
				<th style="padding:8px 12px">Escalated On</th>
				<th style="padding:8px 12px">Days</th>
				<th style="padding:8px 12px">Status</th>
				${isPending ? `<th style="padding:8px 12px">Action</th>` : ""}
			</tr>
		</thead>`;

		const bodyRows = rows.map((r, i) => {
			const bg       = i % 2 === 0 ? "#fff" : "#fafafa";
			const dayBadge = r.days_pending > 7
				? `<span style="color:#e74c3c;font-weight:600">${r.days_pending}</span>`
				: r.days_pending;
			const actions  = isPending
				? `<td style="padding:8px 12px;white-space:nowrap">
					<button class="btn btn-xs btn-success ac-action" data-name="${r.name}"
						data-status="Cleared – Will Apply" style="margin-right:4px">Cleared</button>
					<button class="btn btn-xs btn-danger ac-action" data-name="${r.name}"
						data-status="Blocked – No Resolution">Blocked</button>
				  </td>`
				: "";

			return `<tr style="background:${bg};font-size:13px">
				<td style="padding:8px 12px;font-family:monospace">${r.household}</td>
				<td style="padding:8px 12px">${r.respondent || "—"}</td>
				<td style="padding:8px 12px">${r.street || "—"}</td>
				<td style="padding:8px 12px">${r.ac_alloted || "—"}</td>
				<td style="padding:8px 12px">${r.co || "—"}</td>
				<td style="padding:8px 12px;text-align:center">${r.visit_count}</td>
				<td style="padding:8px 12px">${r.escalation_date}</td>
				<td style="padding:8px 12px;text-align:center">${dayBadge}</td>
				<td style="padding:8px 12px">${statusBadgeHtml(r.status)}</td>
				${actions}
			</tr>`;
		}).join("");

		$("#ac-review-table").html(`
			<table style="width:100%;border-collapse:collapse;border:1px solid #eee;border-radius:8px;overflow:hidden">
				${header}<tbody>${bodyRows}</tbody>
			</table>`);

		$(".ac-action").on("click", function () {
			const name   = $(this).data("name");
			const status = $(this).data("status");
			frappe.prompt(
				{ fieldtype: "Small Text", fieldname: "ac_notes", label: "Notes (optional)" },
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
				`Mark as: ${status}`, "Confirm"
			);
		});
	}

	function statusBadgeHtml(status) {
		const map = {
			"Pending AC Review":         ["#e74c3c", "Pending"],
			"Cleared – Will Apply": ["#27ae60", "Cleared"],
			"Blocked – No Resolution": ["#7f8c8d", "Blocked"],
		};
		const [color, label] = map[status] || ["#ccc", status];
		return `<span style="background:${color};color:#fff;border-radius:4px;padding:2px 8px;font-size:11px">${label}</span>`;
	}

	loadFilters();
};
