frappe.pages["pm-chennai-dashboard"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "PM Chennai Dashboard",
		single_column: true,
	});

	// ── State ────────────────────────────────────────────────────────────────
	const STATE = {
		view: "entitlements",              // entitlements | elderly | performance | blockers
		pivot: "co",                       // co | ac | org
		filters: { org: "", iu: "", month: "" },
		drill: null,                       // { level, parent }
		meta: { orgs: [], ius: [] },
	};

	const LS_KEY = "pm-chennai-dashboard.v1";
	function loadPrefs() {
		try {
			const s = JSON.parse(localStorage.getItem(LS_KEY) || "{}");
			Object.assign(STATE.filters, s.filters || {});
			if (s.view) STATE.view = s.view;
		} catch (e) { /* ignore */ }
	}
	function savePrefs() {
		try { localStorage.setItem(LS_KEY, JSON.stringify({ filters: STATE.filters, view: STATE.view })); }
		catch (e) { /* ignore */ }
	}

	// ── Top-bar filters ──────────────────────────────────────────────────────
	const $org = page.add_field({
		fieldtype: "Select", fieldname: "org", label: "Org", options: "",
		change() { STATE.filters.org = $org.get_value() || ""; refillIU(); savePrefs(); loadCurrent(); },
	});
	const $iu = page.add_field({
		fieldtype: "Select", fieldname: "iu", label: "IU", options: "",
		change() { STATE.filters.iu = $iu.get_value() || ""; savePrefs(); loadCurrent(); },
	});
	const $month = page.add_field({
		fieldtype: "Data", fieldname: "month", label: "Month (YYYY-MM)",
		change() { STATE.filters.month = $month.get_value() || ""; savePrefs(); loadCurrent(); },
	});
	page.add_inner_button("Refresh", () => loadCurrent());

	// ── Container + styles ───────────────────────────────────────────────────
	$(`<style>
		.pm-shell { padding: 12px 16px; font-size: 13px; color: #1B2A41; }
		.pm-flags { display: flex; gap: 12px; flex-wrap: wrap; background: #22334D;
			color: #E7ECF4; padding: 8px 14px; border-radius: 6px; margin-bottom: 12px;
			font-size: 12.5px; }
		.pm-flag-item { display: inline-flex; gap: 6px; align-items: center; }
		.pm-flag-dot { width: 8px; height: 8px; border-radius: 50%; }
		.pm-dot-red { background: #E36049; } .pm-dot-amber { background: #F6C453; }
		.pm-layout { display: flex; gap: 14px; align-items: flex-start; }
		.pm-rail { width: 200px; background: #fff; border: 1px solid #DCE1E8;
			border-radius: 8px; padding: 8px 0; flex: none; }
		.pm-rail button { display: block; width: 100%; text-align: left;
			padding: 9px 14px; border: 0; background: none; font-size: 13px;
			color: #4A5A72; cursor: pointer; border-left: 3px solid transparent; }
		.pm-rail button:hover { background: #F1F3F6; }
		.pm-rail button.on { color: #2F4B8F; border-left-color: #2F4B8F;
			background: #E8EDF8; font-weight: 600; }
		.pm-rail-grp { padding: 10px 14px 4px; font-size: 10.5px; letter-spacing: 1.1px;
			text-transform: uppercase; color: #9AA6B6; font-weight: 600; }
		.pm-main { flex: 1; min-width: 0; }
		.pm-kpis { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 12px; }
		.pm-kpi { background: #fff; border: 1px solid #DCE1E8; border-radius: 8px;
			padding: 10px 14px; min-width: 130px; flex: 1 1 auto; }
		.pm-kpi-v { font-family: 'IBM Plex Mono', Consolas, monospace;
			font-size: 20px; font-weight: 600; }
		.pm-kpi-l { font-size: 11.5px; color: #4A5A72; margin-top: 2px; }
		.pm-card { background: #fff; border: 1px solid #DCE1E8; border-radius: 8px;
			padding: 12px 14px; margin-bottom: 12px; }
		.pm-card h3 { font-size: 12px; text-transform: uppercase; letter-spacing: .7px;
			color: #4A5A72; margin: 0 0 10px; font-weight: 600; }
		.pm-grid2 { display: grid; grid-template-columns: 1fr 1fr; gap: 12px; }
		.pm-num { font-family: 'IBM Plex Mono', Consolas, monospace; font-size: 12.5px; }
		.pm-pill { display: inline-block; padding: 2px 8px; border-radius: 10px;
			font-size: 11px; font-weight: 600; }
		.pm-p-ok { background: #E7F3EC; color: #2E7D4F; }
		.pm-p-warn { background: #FBF1DE; color: #C77E14; }
		.pm-p-bad { background: #F9E9E5; color: #B3402E; }
		.pm-p-mut { background: #EDF0F4; color: #6B7789; }
		.pm-bar { height: 8px; background: #E7EBF1; border-radius: 4px; overflow: hidden; }
		.pm-bar > i { display: block; height: 100%; border-radius: 4px; }
		.pm-tab-btns { display: flex; gap: 4px; margin-bottom: 10px; flex-wrap: wrap; }
		.pm-tab-btns button { border: 1px solid #DCE1E8; background: #fff;
			padding: 4px 12px; font-size: 12.5px; cursor: pointer; color: #4A5A72; }
		.pm-tab-btns button:first-child { border-radius: 6px 0 0 6px; }
		.pm-tab-btns button:last-child { border-radius: 0 6px 6px 0; }
		.pm-tab-btns button.on { background: #1B2A41; color: #fff;
			border-color: #1B2A41; font-weight: 600; }
		.pm-table { width: 100%; border-collapse: collapse; font-size: 12.5px; }
		.pm-table th { text-align: left; font-size: 10.5px; text-transform: uppercase;
			letter-spacing: .5px; color: #8792A3; font-weight: 600; padding: 6px 8px;
			border-bottom: 1px solid #DCE1E8; }
		.pm-table td { padding: 7px 8px; border-bottom: 1px solid #EEF1F5;
			vertical-align: top; }
		.pm-click { cursor: pointer; }
		.pm-click:hover td { background: #F6F8FB; }
		.pm-blocker { background: #F9E9E5; border-left: 3px solid #B3402E;
			border-radius: 0 6px 6px 0; padding: 8px 12px; font-size: 12.5px;
			margin-top: 8px; }
		.pm-blocker b { color: #B3402E; }
		.pm-note { background: #E8EDF8; border-left: 3px solid #2F4B8F;
			border-radius: 0 6px 6px 0; padding: 8px 12px; font-size: 12.5px;
			margin-top: 8px; }
		.pm-crumb { font-size: 12px; color: #4A5A72; margin-bottom: 10px; }
		.pm-crumb a { color: #2F4B8F; cursor: pointer; text-decoration: none; }
		.pm-empty { color: #8792A3; padding: 16px; text-align: center; }
		.pm-chip { display: inline-block; padding: 2px 6px; border-radius: 4px;
			font-size: 10.5px; margin-right: 4px; font-weight: 600; }
		.pm-chip-ok { background: #E7F3EC; color: #2E7D4F; }
		.pm-chip-open { background: #FBF1DE; color: #C77E14; }
		.pm-chip-mut { background: #EDF0F4; color: #6B7789; }
		.pm-pipe { display: flex; gap: 5px; align-items: flex-end; margin: 8px 0 6px; }
		.pm-pipe-bk { flex: 1; text-align: center; }
		.pm-pipe-col { border-radius: 4px 4px 0 0; margin: 0 auto; width: 70%;
			min-height: 6px; }
		.pm-pipe-lbl { font-size: 10px; color: #4A5A72; margin-top: 5px;
			line-height: 1.2; }
		.pm-pipe-cnt { font-family: 'IBM Plex Mono', Consolas, monospace;
			font-size: 12px; font-weight: 600; margin-bottom: 2px; }
		@media (max-width: 900px) {
			.pm-layout { flex-direction: column; }
			.pm-rail { width: 100%; display: flex; overflow-x: auto; }
			.pm-rail button { white-space: nowrap; border-left: none;
				border-bottom: 3px solid transparent; }
			.pm-rail button.on { border-bottom-color: #2F4B8F; }
			.pm-rail-grp { display: none; }
			.pm-grid2 { grid-template-columns: 1fr; }
		}
	</style>
	<div class="pm-shell">
		<div id="pm-flags" class="pm-flags" style="display:none"></div>
		<div class="pm-layout">
			<nav class="pm-rail" id="pm-rail"></nav>
			<div class="pm-main" id="pm-main"></div>
		</div>
	</div>`).appendTo($(wrapper).find(".page-content"));

	// ── Helpers ──────────────────────────────────────────────────────────────
	function esc(s) {
		return String(s == null ? "" : s)
			.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
			.replace(/"/g, "&quot;").replace(/'/g, "&#39;");
	}
	function pct(a, b) { return b > 0 ? Math.round(100 * a / b) : 0; }
	function satColor(p) {
		if (p >= 80) return "#2E7D4F";
		if (p >= 60) return "#C77E14";
		return "#B3402E";
	}
	function bar(p, colour) {
		return `<div class="pm-bar"><i style="width:${Math.max(0, Math.min(100, p))}%;background:${colour || satColor(p)}"></i></div>`;
	}
	function kpi(v, l) {
		return `<div class="pm-kpi"><div class="pm-kpi-v">${esc(v)}</div><div class="pm-kpi-l">${esc(l)}</div></div>`;
	}
	function pill(cls, txt) {
		return `<span class="pm-pill ${cls}">${esc(txt)}</span>`;
	}
	function num(n) { return n == null ? "—" : String(n); }
	function call(method, args, ok) {
		return frappe.call({ method, args: args || {}, callback: (r) => ok(r.message || {}), error: () => ok({ error: "call_failed" }) });
	}

	// ── Rail nav ─────────────────────────────────────────────────────────────
	const RAIL = [
		["grp", "Programmes"],
		["entitlements", "Entitlements"],
		["elderly",      "Elderly care (ECP)"],
		["grp", "Cross-cutting"],
		["performance",  "CO / AC / Org performance"],
		["blockers",     "Blockers & SLA"],
	];
	function renderRail() {
		$("#pm-rail").html(RAIL.map(([k, l]) =>
			k === "grp"
				? `<div class="pm-rail-grp">${l}</div>`
				: `<button data-v="${k}" class="${STATE.view === k ? "on" : ""}">${l}</button>`
		).join(""));
		$("#pm-rail button").on("click", function () {
			STATE.view = $(this).data("v");
			STATE.drill = null;
			savePrefs();
			renderRail();
			loadCurrent();
		});
	}

	// ── Filter meta bootstrap ────────────────────────────────────────────────
	function bootstrapFilters(then) {
		call("changemakers.pm_dashboard_api.get_filter_meta", {}, (m) => {
			STATE.meta = { orgs: m.orgs || [], ius: m.ius || [] };
			fillOrg();
			refillIU();
			if (STATE.filters.month) $month.set_value(STATE.filters.month);
			then && then();
		});
	}
	function fillOrg() {
		const cur = STATE.filters.org || "";
		const opts = [""].concat(STATE.meta.orgs);
		$org.$wrapper.find("select").empty();
		opts.forEach(o => $org.$wrapper.find("select").append(
			`<option value="${esc(o)}">${o ? esc(o) : "All Orgs"}</option>`
		));
		if (opts.indexOf(cur) >= 0) $org.set_value(cur);
	}
	function refillIU() {
		const org = STATE.filters.org;
		const cur = STATE.filters.iu || "";
		const options = STATE.meta.ius
			.filter(x => !org || x.org === org)
			.map(x => x.iu);
		const opts = [""].concat(options);
		$iu.$wrapper.find("select").empty();
		opts.forEach(o => $iu.$wrapper.find("select").append(
			`<option value="${esc(o)}">${o ? esc(o) : "All IUs"}</option>`
		));
		if (opts.indexOf(cur) >= 0) $iu.set_value(cur); else { $iu.set_value(""); STATE.filters.iu = ""; }
	}

	// ── Loaders ──────────────────────────────────────────────────────────────
	function commonArgs() {
		const a = {};
		if (STATE.filters.month) a.month = STATE.filters.month;
		if (STATE.filters.org)   a.implementing_org = STATE.filters.org;
		if (STATE.filters.iu)    a.intervention_unit = STATE.filters.iu;
		return a;
	}
	function loadCurrent() {
		loadFlags();
		if (STATE.drill) return renderDrill();
		if (STATE.view === "entitlements") return loadEntitlements();
		if (STATE.view === "elderly")      return loadElderly();
		if (STATE.view === "performance")  return loadPerformance();
		if (STATE.view === "blockers")     return loadBlockers();
	}

	function loadFlags() {
		call("changemakers.pm_dashboard_api.get_overview", commonArgs(), (d) => {
			renderFlags(d);
		});
	}
	function renderFlags(d) {
		const flags = (d && d.flags) || [];
		if (!flags.length) { $("#pm-flags").hide().empty(); return; }
		const items = flags.map(f => {
			const cls = f.colour === "red" ? "pm-dot-red" : "pm-dot-amber";
			const cnt = f.kind === "manual_blocker" ? "" : ` (${f.count})`;
			return `<span class="pm-flag-item"><span class="pm-flag-dot ${cls}"></span>${esc(f.label)}${esc(cnt)}</span>`;
		});
		$("#pm-flags").show().html(`<b style="color:#F6C453">Today's flags →</b> ${items.join(" · ")}`);
	}

	// ── Entitlements view ────────────────────────────────────────────────────
	function loadEntitlements() {
		$("#pm-main").html(`<div class="pm-empty">Loading entitlements…</div>`);
		call("changemakers.pm_dashboard_api.get_entitlements_view", commonArgs(), (d) => {
			renderEntitlements(d);
		});
	}
	function renderEntitlements(d) {
		const cards = (d && d.cards) || [];
		if (!cards.length) { $("#pm-main").html(`<div class="pm-empty">No entitlements enabled.</div>`); return; }

		const totalLanded = cards.reduce((s, c) => s + (c.landed || 0), 0);
		const totalEligible = cards.reduce((s, c) => s + (c.total || 0), 0);
		const withBlocker = cards.filter(c => c.blocker).length;

		const kpisHtml = `<div class="pm-kpis">
			${kpi(`${pct(totalLanded, totalEligible)}%`, `overall saturation (${totalLanded}/${totalEligible})`)}
			${kpi(cards.length, "entitlements tracked")}
			${kpi(withBlocker, "with a blocker flagged")}
		</div>`;

		const cardsHtml = cards.map(c => entitlementCard(c)).join("");
		const monthLabel = (d.month && d.month.label) || "";
		$("#pm-main").html(kpisHtml + `<div class="pm-card"><h3>Scheme cards — ${esc(monthLabel)}</h3><div class="pm-grid2">${cardsHtml}</div></div>`);

		$(".pm-open-scheme").on("click", function () {
			const code = $(this).data("code");
			STATE.drill = { level: "org", scheme: code };
			loadCurrent();
		});
		$(".pm-edit-note").on("click", function (e) {
			e.stopPropagation();
			openNoteDialog($(this).data("code"));
		});
	}
	function entitlementCard(c) {
		const p = pct(c.landed || 0, c.total || 0);
		const bucketsList = c.buckets ? Object.entries(c.buckets) : [];
		const maxCount = Math.max(1, ...bucketsList.map(([, v]) => v));
		const pipe = bucketsList.length
			? `<div class="pm-pipe">${bucketsList.map(([k, v]) => `
				<div class="pm-pipe-bk" title="${esc(k)}: ${v}">
					<div class="pm-pipe-cnt">${v}</div>
					<div class="pm-pipe-col" style="height:${Math.max(6, Math.round(40 * v / maxCount))}px;background:#2F4B8F"></div>
					<div class="pm-pipe-lbl">${esc(k)}</div>
				</div>`).join("")}</div>`
			: "";
		const b = c.blocker;
		const blockerHtml = b
			? `<div class="pm-blocker"><b>${b.source === "manual" ? "PM note" : "Auto-derived"}${b.resolved ? " · resolved" : ""}:</b> ${esc(b.text)}
				${b.owner_action ? `<div style="margin-top:4px"><b>Next:</b> ${esc(b.owner_action)}</div>` : ""}
				<a class="pm-edit-note" data-code="${c.code}" style="margin-left:6px;font-size:11px;cursor:pointer;color:#2F4B8F">✎ edit</a></div>`
			: `<div class="pm-note" style="padding:4px 8px;font-size:11.5px">No blocker.
				<a class="pm-edit-note" data-code="${c.code}" style="margin-left:6px;cursor:pointer;color:#2F4B8F">+ add PM note</a></div>`;
		return `<div class="pm-card pm-click pm-open-scheme" data-code="${c.code}" style="margin:0">
			<div style="display:flex;justify-content:space-between;align-items:baseline;gap:8px;flex-wrap:wrap">
				<b>${esc(c.name)} <span class="pm-num" style="color:#8792A3;font-weight:400;font-size:11px">${esc(c.code)}</span></b>
				<span class="pm-num" style="font-size:15px;font-weight:600;color:${satColor(p)}">${p}%</span>
			</div>
			<div style="margin:6px 0 3px">${bar(p)}</div>
			<div class="pm-num" style="font-size:11.5px;color:#4A5A72">${c.landed || 0} of ${c.total || 0} eligible reached</div>
			${pipe}
			${blockerHtml}
		</div>`;
	}

	// ── Blocker note dialog ──────────────────────────────────────────────────
	function openNoteDialog(entitlementCode) {
		const month = STATE.filters.month || (new Date()).toISOString().slice(0, 7);
		const dlg = new frappe.ui.Dialog({
			title: `Blocker note — ${entitlementCode} · ${month}`,
			fields: [
				{ fieldtype: "Small Text", fieldname: "blocker_text", label: "What's stuck", reqd: 1 },
				{ fieldtype: "Small Text", fieldname: "owner_action", label: "Owner / next action" },
				{ fieldtype: "Check",      fieldname: "resolved", label: "Mark resolved" },
			],
			primary_action_label: "Save",
			primary_action(vals) {
				frappe.call({
					method: "changemakers.pm_dashboard_api.save_blocker_note",
					args: {
						entitlement_code: entitlementCode, month,
						blocker_text: vals.blocker_text,
						owner_action: vals.owner_action || "",
						resolved: vals.resolved ? 1 : 0,
					},
					callback: () => {
						frappe.show_alert({ message: "Saved", indicator: "green" });
						dlg.hide();
						loadCurrent();
					},
				});
			},
		});
		dlg.show();
	}

	// ── Elderly view ─────────────────────────────────────────────────────────
	function loadElderly() {
		$("#pm-main").html(`<div class="pm-empty">Loading elderly care…</div>`);
		call("changemakers.pm_dashboard_api.get_elderly_view", commonArgs(), (d) => {
			renderElderly(d);
		});
	}
	function renderElderly(d) {
		const cov = d.coverage || {};
		const ev = d.evrat || {};
		const hv = d.home_visits || {};
		const kpis = `<div class="pm-kpis">
			${kpi(cov.total_elderly || 0, "elderly (55+) in scope")}
			${kpi(cov.total_hh || 0, "households with elderly")}
			${kpi(ev.total || 0, "EVRAT assessments (all-time)")}
			${kpi(ev.this_month || 0, "EVRATs this month")}
			${kpi(hv.this_month || 0, "home visits this month")}
		</div>`;

		const covRows = (cov.rows || []).map(r => `<tr>
			<td><b>${esc(r.eco)}</b></td>
			<td class="pm-num">${r.street_count}</td>
			<td class="pm-num">${r.elderly_count}</td>
			<td class="pm-num">${r.hh_with_elderly}</td>
		</tr>`).join("") || `<tr><td colspan="4" class="pm-empty">No coverage rows in scope.</td></tr>`;

		const riskBuckets = ev.risk_distribution || {};
		const riskItems = Object.entries(riskBuckets).map(([k, v]) => `<tr>
			<td>${esc(k)}</td>
			<td class="pm-num">${v}</td>
		</tr>`).join("") || `<tr><td colspan="2" class="pm-empty">${ev.available === false ? "EVRAT tables not present on this bench." : "No risk data."}</td></tr>`;

		const hvItems = (hv.by_eco || []).map(r => `<tr>
			<td>${esc(r.eco)}</td>
			<td class="pm-num">${r.count}</td>
		</tr>`).join("") || `<tr><td colspan="2" class="pm-empty">${hv.available === false ? "Home Visit table not present." : "No home visits this month."}</td></tr>`;

		$("#pm-main").html(kpis + `
			<div class="pm-card"><h3>ECO coverage — streets / elderly / HH</h3>
				<table class="pm-table">
					<tr><th>ECO</th><th>Streets</th><th>Elderly</th><th>HH</th></tr>
					${covRows}
				</table>
			</div>
			<div class="pm-grid2">
				<div class="pm-card"><h3>EVRAT risk distribution</h3>
					<table class="pm-table"><tr><th>Bucket</th><th>Count</th></tr>${riskItems}</table>
				</div>
				<div class="pm-card"><h3>Home visits by ECO — this month</h3>
					<table class="pm-table"><tr><th>ECO</th><th>Visits</th></tr>${hvItems}</table>
				</div>
			</div>`);
	}

	// ── Performance view ─────────────────────────────────────────────────────
	function loadPerformance() {
		$("#pm-main").html(`<div class="pm-empty">Loading performance…</div>`);
		const args = Object.assign({}, commonArgs(), { pivot: STATE.pivot });
		call("changemakers.pm_dashboard_api.get_performance_view", args, (d) => {
			renderPerformance(d);
		});
	}
	function renderPerformance(d) {
		const rows = (d.rows || []);
		const pivotButtons = ["co", "ac", "org"].map(p =>
			`<button data-p="${p}" class="${STATE.pivot === p ? "on" : ""}">${p.toUpperCase()}</button>`
		).join("");
		const otherCodes = new Set();
		rows.forEach(r => Object.keys(r.other || {}).forEach(k => otherCodes.add(k)));
		const otherCols = [...otherCodes];

		const header = `<tr>
			<th>${esc(STATE.pivot.toUpperCase())}</th>
			<th>CMCHIS (E1)</th>
			<th>OAP (E2)</th>
			${otherCols.map(c => `<th>${esc(c)}</th>`).join("")}
			<th>ECP visits</th>
			<th>Total</th>
		</tr>`;
		const body = rows.map(r => {
			const total = (r.cmchis_landed || 0) + (r.e2_landed || 0)
				+ Object.values(r.other || {}).reduce((s, v) => s + v, 0)
				+ (r.ecp_visits || 0);
			return `<tr>
				<td><b>${esc(r.entity)}</b></td>
				<td class="pm-num">${r.cmchis_landed || 0}</td>
				<td class="pm-num">${r.e2_landed || 0}</td>
				${otherCols.map(c => `<td class="pm-num">${(r.other || {})[c] || 0}</td>`).join("")}
				<td class="pm-num">${r.ecp_visits || 0}</td>
				<td class="pm-num"><b>${total}</b></td>
			</tr>`;
		}).join("") || `<tr><td colspan="6" class="pm-empty">No activity in ${esc(d.month && d.month.label || "this period")}.</td></tr>`;

		$("#pm-main").html(`
			<div class="pm-tab-btns">${pivotButtons}</div>
			<div class="pm-card"><h3>Benefits landed / visits made — ${esc(d.month && d.month.label || "")}</h3>
				<table class="pm-table">${header}${body}</table>
				<div style="margin-top:6px;font-size:11px;color:#8792A3">
					CMCHIS is counted from WRP Status Log transitions to Active this month.
					OAP and future entitlements from Generic Beneficiary final_status = active.
					ECP visits from Home Visit - ECP.
				</div>
			</div>`);
		$(".pm-tab-btns button").on("click", function () {
			STATE.pivot = $(this).data("p");
			loadPerformance();
		});
	}

	// ── Blockers view ────────────────────────────────────────────────────────
	function loadBlockers() {
		$("#pm-main").html(`<div class="pm-empty">Loading blockers…</div>`);
		call("changemakers.pm_dashboard_api.get_blockers_view", commonArgs(), (d) => {
			renderBlockers(d);
		});
	}
	function renderBlockers(d) {
		const auto = d.auto || [];
		const manual = d.manual || [];

		const autoRows = auto.map(a => `<div class="pm-blocker">
			<b>${esc(a.entitlement_code)} · auto:</b> ${esc(a.text)}
			<a class="pm-edit-note" data-code="${a.entitlement_code}" style="margin-left:6px;cursor:pointer;color:#2F4B8F">+ turn into PM note</a>
		</div>`).join("") || `<div class="pm-empty">No auto blockers this month.</div>`;

		const manualRows = manual.map(m => `<div class="${m.resolved ? "pm-note" : "pm-blocker"}">
			<div style="display:flex;justify-content:space-between;gap:8px;flex-wrap:wrap">
				<span><b>${esc(m.entitlement_code)}${m.resolved ? " · resolved" : ""}:</b> ${esc(m.blocker_text)}</span>
				<a class="pm-edit-note" data-code="${m.entitlement_code}" style="cursor:pointer;color:#2F4B8F">✎ edit</a>
			</div>
			${m.owner_action ? `<div style="margin-top:4px"><b>Next:</b> ${esc(m.owner_action)}</div>` : ""}
			<div style="margin-top:4px;font-size:11px;color:#8792A3">Updated ${esc(m.modified || "")}</div>
		</div>`).join("") || `<div class="pm-empty">No PM notes for this month yet.</div>`;

		$("#pm-main").html(`
			<div class="pm-card"><h3>Auto-derived — ${esc(d.month && d.month.label || "")}</h3>${autoRows}</div>
			<div class="pm-card"><h3>PM notes</h3>${manualRows}</div>
		`);
		$(".pm-edit-note").on("click", function () { openNoteDialog($(this).data("code")); });
	}

	// ── Drill-down ───────────────────────────────────────────────────────────
	function renderDrill() {
		const d = STATE.drill;
		$("#pm-main").html(`<div class="pm-empty">Loading drill-down…</div>`);
		const args = Object.assign({}, commonArgs(), {
			level: d.level,
			parent: d.parent || "",
		});
		call("changemakers.pm_dashboard_api.get_drilldown_unified", args, (r) => {
			renderDrillRows(r);
		});
	}
	function renderDrillRows(r) {
		const d = STATE.drill;
		const level = r.level || d.level;
		const rows = r.rows || [];
		const crumb = drillCrumbs();

		let body = "";
		if (level === "org") {
			body = `<table class="pm-table"><tr><th>Org</th><th>IUs</th><th>Streets</th></tr>
				${rows.map(x => `<tr class="pm-click" data-nxt="iu" data-p="${esc(x.entity)}">
					<td><b>${esc(x.entity)}</b></td><td class="pm-num">${x.ius || ""}</td><td class="pm-num">${x.streets || ""}</td></tr>`).join("")}</table>`;
		} else if (level === "iu") {
			body = `<table class="pm-table"><tr><th>IU</th><th>Streets</th></tr>
				${rows.map(x => `<tr class="pm-click" data-nxt="street" data-p="${esc(x.entity)}">
					<td><b>${esc(x.entity)}</b></td><td class="pm-num">${x.streets || ""}</td></tr>`).join("")}</table>`;
		} else if (level === "street") {
			body = `<table class="pm-table"><tr><th>Street</th><th>CO</th><th>AC</th><th>Org</th><th>HH</th></tr>
				${rows.map(x => `<tr class="pm-click" data-nxt="hh" data-p="${esc(x.entity)}">
					<td><b>${esc(x.entity)}</b></td><td>${esc(x.co || "—")}</td><td>${esc(x.ac || "—")}</td>
					<td>${esc(x.org || "—")}</td><td class="pm-num">${x.hh_count || 0}</td></tr>`).join("")}</table>`;
		} else if (level === "hh") {
			body = `<table class="pm-table"><tr><th>Household</th><th>Respondent</th><th>CMCHIS</th><th>Members</th></tr>
				${rows.map(x => `<tr class="pm-click" data-nxt="individual" data-p="${esc(x.entity)}">
					<td class="pm-num">${esc(x.entity)}</td><td>${esc(x.respondent || "—")}</td>
					<td>${esc(x.cmchis_status || "—")}</td><td class="pm-num">${x.members || 0}</td></tr>`).join("")}</table>`;
		} else if (level === "individual") {
			body = `<table class="pm-table"><tr><th>Individual</th><th>Age</th><th>Gender</th><th>Status</th><th>Entitlements</th></tr>
				${rows.map(x => {
					const chips = Object.entries(x.entitlements || {}).map(([code, info]) => {
						const cls = info.final_status === "active" ? "pm-chip-ok" : "pm-chip-open";
						const label = info.final_status ? `${code} · ${info.final_status}` : `${code}`;
						return `<span class="pm-chip ${cls}">${esc(label)}</span>`;
					}).join("");
					const evrat = x.evrat ? `<span class="pm-chip pm-chip-ok">EVRAT ✓</span>` : "";
					return `<tr>
						<td>${esc(x.first_name || x.name)} <span class="pm-num" style="color:#8792A3;font-size:10px">#${esc(x.name)}</span></td>
						<td class="pm-num">${x.age || "—"}</td>
						<td>${esc(x.gender || "—")}</td>
						<td>${esc(x.status || "—")}</td>
						<td>${chips || `<span class="pm-chip pm-chip-mut">—</span>`}${evrat}</td>
					</tr>`;
				}).join("") || `<tr><td colspan="5" class="pm-empty">No individuals in this household.</td></tr>`}</table>`;
		}

		$("#pm-main").html(`
			<div class="pm-crumb">${crumb}</div>
			<div class="pm-card"><h3>Drill-down: ${esc(level)}</h3>${body || `<div class="pm-empty">No rows.</div>`}</div>
		`);

		$(".pm-click[data-nxt]").on("click", function () {
			const nxt = $(this).data("nxt");
			const p = $(this).data("p");
			STATE.drill = { level: nxt, parent: String(p) };
			// Also update org filter when clicking through an org row so pivots stay aligned
			if (d.level === "org") STATE.filters.org = String(p);
			if (d.level === "iu")  STATE.filters.iu = String(p);
			savePrefs();
			loadCurrent();
		});
	}
	function drillCrumbs() {
		const links = [`<a data-go="exit">← ${esc(STATE.view)}</a>`];
		links.push(`<span> / drill-down (${esc(STATE.drill.level)}${STATE.drill.parent ? ": " + esc(STATE.drill.parent) : ""})</span>`);
		setTimeout(() => {
			$("[data-go='exit']").off("click").on("click", () => {
				STATE.drill = null;
				loadCurrent();
			});
		}, 0);
		return links.join("");
	}

	// ── Boot ─────────────────────────────────────────────────────────────────
	loadPrefs();
	renderRail();
	bootstrapFilters(loadCurrent);
};
