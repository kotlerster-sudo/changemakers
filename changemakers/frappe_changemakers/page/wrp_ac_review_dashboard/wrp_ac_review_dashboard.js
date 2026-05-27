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
	$(`<style>
		@media (max-width: 767px) {
			.ac-desktop-table { display: none !important; }
			.ac-mobile-cards  { display: block !important; }
		}
		@media (min-width: 768px) {
			.ac-desktop-table { display: table !important; }
			.ac-mobile-cards  { display: none !important; }
		}
		.ac-mobile-card {
			background: #fff;
			border: 1px solid #e8e8e8;
			border-radius: 8px;
			padding: 12px 14px;
			margin-bottom: 10px;
		}
		.ac-mobile-card-top {
			display: flex;
			justify-content: space-between;
			align-items: center;
			margin-bottom: 4px;
		}
		.ac-mobile-card-sub {
			font-size: 12px;
			color: #666;
			margin-bottom: 8px;
		}
		.ac-mobile-card-actions { display: flex; gap: 8px; margin-top: 8px; }
		.ac-notes-block { margin-top: 8px; font-size: 12px; line-height: 1.4; }
		.ac-notes-block .ac-note-original {
			background: #fff8e1;
			border-left: 3px solid #f1c40f;
			padding: 6px 8px;
			border-radius: 3px;
			color: #5d4e00;
			white-space: pre-wrap;
		}
		.ac-notes-block .ac-note-followups {
			margin-top: 6px;
			background: #f4f9ff;
			border-left: 3px solid #2980b9;
			padding: 6px 8px;
			border-radius: 3px;
			color: #1a3d5c;
			white-space: pre-wrap;
		}
		.ac-notes-block .ac-note-label {
			text-transform: uppercase;
			font-size: 10px;
			font-weight: 700;
			letter-spacing: 0.5px;
			opacity: 0.7;
			margin-bottom: 2px;
		}
	</style>
	<div style="padding:12px 16px">
		<div id="ac-review-summary" style="display:flex;gap:12px;margin-bottom:16px;flex-wrap:wrap"></div>
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
		const fresh  = rows.filter(r => (r.days_pending || 0) <= 7).length;
		const mid    = rows.filter(r => (r.days_pending || 0) > 7 && (r.days_pending || 0) <= 14).length;
		const stale  = rows.filter(r => (r.days_pending || 0) > 14).length;

		const card = (label, val, color) =>
			`<div style="background:${color};border-radius:8px;padding:12px 20px;min-width:120px;text-align:center">
				<div style="font-size:22px;font-weight:700;color:#fff">${val}</div>
				<div style="font-size:12px;color:rgba(255,255,255,.85)">${label}</div>
			</div>`;

		const ageBucketCard = `
			<div style="background:#2980b9;border-radius:8px;padding:12px 20px;min-width:160px;text-align:center">
				<div style="display:flex;justify-content:center;gap:14px;align-items:baseline">
					<span style="font-size:20px;font-weight:700;color:#fff">${fresh}</span>
					<span style="font-size:11px;color:rgba(255,255,255,.7)">|</span>
					<span style="font-size:20px;font-weight:700;color:#f39c12">${mid}</span>
					<span style="font-size:11px;color:rgba(255,255,255,.7)">|</span>
					<span style="font-size:20px;font-weight:700;color:#e74c3c">${stale}</span>
				</div>
				<div style="font-size:11px;color:rgba(255,255,255,.75);margin-top:4px">≤7d &nbsp;·&nbsp; 8–14d &nbsp;·&nbsp; &gt;14d</div>
			</div>`;

		$("#ac-review-summary").html(
			card("Pending", pending, "#e74c3c") +
			card("Cleared", cleared, "#27ae60") +
			card("Blocked", blocked, "#7f8c8d") +
			ageBucketCard
		);
	}

	// ── Table ─────────────────────────────────────────────────────────────────
	function renderTable(rows, statusFilter) {
		if (!rows.length) {
			$("#ac-review-table").html(`<p style="color:#888;margin-top:24px">No records found.</p>`);
			return;
		}

		const isPending = !statusFilter || statusFilter === "Pending AC Review";

		// ── Desktop table ──────────────────────────────────────────────────────
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
				<th style="padding:8px 12px;min-width:240px">Notes</th>
				<th style="padding:8px 12px">Action</th>
			</tr>
		</thead>`;

		const bodyRows = rows.map((r, i) => {
			const bg       = i % 2 === 0 ? "#fff" : "#fafafa";
			const dayBadge = dayBadgeHtml(r.days_pending);
			const resolved = r.status === "Cleared – Will Apply" || r.status === "Blocked – No Resolution";
			const actions  = isPending
				? actionCellHtml(r.name)
				: (resolved ? followupActionCellHtml(r.name) : `<td style="padding:8px 12px"></td>`);
			return `<tr style="background:${bg};font-size:13px;vertical-align:top">
				<td style="padding:8px 12px;font-family:monospace">${r.household}</td>
				<td style="padding:8px 12px">${r.respondent || "—"}</td>
				<td style="padding:8px 12px">${r.street || "—"}</td>
				<td style="padding:8px 12px">${r.ac_alloted || "—"}</td>
				<td style="padding:8px 12px">${r.co || "—"}</td>
				<td style="padding:8px 12px;text-align:center">${r.visit_count}</td>
				<td style="padding:8px 12px">${r.escalation_date}</td>
				<td style="padding:8px 12px;text-align:center">${dayBadge}</td>
				<td style="padding:8px 12px">${statusBadgeHtml(r.status)}</td>
				<td style="padding:8px 12px">${notesBlockHtml(r)}</td>
				${actions}
			</tr>`;
		}).join("");

		const desktopHtml = `
			<table class="ac-desktop-table" style="width:100%;border-collapse:collapse;border:1px solid #eee;border-radius:8px;overflow:hidden">
				${header}<tbody>${bodyRows}</tbody>
			</table>`;

		// ── Mobile cards ───────────────────────────────────────────────────────
		const cards = rows.map(r => {
			const days = r.days_pending || 0;
			const dayColor = days > 14 ? "#e74c3c" : days > 7 ? "#e67e22" : "#27ae60";
			const resolved = r.status === "Cleared – Will Apply" || r.status === "Blocked – No Resolution";
			let actionBtns = "";
			if (isPending) {
				actionBtns = `<div class="ac-mobile-card-actions">
					<button class="btn btn-sm btn-success ac-action" data-name="${r.name}"
						data-status="Cleared – Will Apply" style="flex:1">Cleared</button>
					<button class="btn btn-sm btn-danger ac-action" data-name="${r.name}"
						data-status="Blocked – No Resolution" style="flex:1">Blocked</button>
				   </div>`;
			} else if (resolved) {
				actionBtns = `<div class="ac-mobile-card-actions">
					<button class="btn btn-sm btn-default ac-followup" data-name="${r.name}" style="flex:1">+ Add Follow-up Note</button>
				   </div>`;
			}
			return `<div class="ac-mobile-card">
				<div class="ac-mobile-card-top">
					<span style="font-family:monospace;font-size:13px;font-weight:600">${r.household}</span>
					<span style="font-size:13px;font-weight:700;color:${dayColor}">${days}d &nbsp;${statusBadgeHtml(r.status)}</span>
				</div>
				<div style="font-size:14px;font-weight:500;margin-bottom:2px">${r.respondent || "—"}</div>
				<div class="ac-mobile-card-sub">${r.street || "—"} &nbsp;·&nbsp; CO: ${r.co || "—"} &nbsp;·&nbsp; ${r.visit_count} visits</div>
				${notesBlockHtml(r)}
				${actionBtns}
			</div>`;
		}).join("");

		const mobileHtml = `<div class="ac-mobile-cards">${cards}</div>`;

		$("#ac-review-table").html(desktopHtml + mobileHtml);

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

		$(".ac-followup").on("click", function () {
			const name = $(this).data("name");
			frappe.prompt(
				{ fieldtype: "Small Text", fieldname: "note", label: "Follow-up note", reqd: 1 },
				({ note }) => {
					frappe.call({
						method: "changemakers.dashboard_api.append_ac_followup_note",
						args: { name, note },
						callback() {
							frappe.show_alert({ message: "Note added", indicator: "green" });
							render();
						},
					});
				},
				"Add follow-up note", "Save"
			);
		});
	}

	function escapeHtml(s) {
		return String(s || "")
			.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
	}

	function notesBlockHtml(r) {
		const original = (r.ac_notes || "").trim();
		const followups = (r.followup_notes || "").trim();
		if (!original && !followups) return `<span style="color:#bbb;font-size:12px">—</span>`;
		let html = `<div class="ac-notes-block">`;
		if (original) {
			html += `<div class="ac-note-original">
				<div class="ac-note-label">Original (at ${escapeHtml(r.resolved_date || "resolution")})</div>
				${escapeHtml(original)}
			</div>`;
		}
		if (followups) {
			html += `<div class="ac-note-followups">
				<div class="ac-note-label">Follow-ups</div>
				${escapeHtml(followups)}
			</div>`;
		}
		html += `</div>`;
		return html;
	}

	function followupActionCellHtml(name) {
		return `<td style="padding:8px 12px;white-space:nowrap">
			<button class="btn btn-xs btn-default ac-followup" data-name="${name}">+ Note</button>
		</td>`;
	}

	function dayBadgeHtml(days) {
		const d = days || 0;
		const color = d > 14 ? "#e74c3c" : d > 7 ? "#e67e22" : "inherit";
		return color !== "inherit"
			? `<span style="color:${color};font-weight:600">${d}</span>`
			: d;
	}

	function actionCellHtml(name) {
		return `<td style="padding:8px 12px;white-space:nowrap">
			<button class="btn btn-xs btn-success ac-action" data-name="${name}"
				data-status="Cleared – Will Apply" style="margin-right:4px">Cleared</button>
			<button class="btn btn-xs btn-danger ac-action" data-name="${name}"
				data-status="Blocked – No Resolution">Blocked</button>
		</td>`;
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
