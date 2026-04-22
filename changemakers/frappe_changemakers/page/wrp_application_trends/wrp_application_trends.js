frappe.pages["wrp-application-trends"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Application Trends",
		single_column: true,
	});

	let _meta = { orgs: [], ius: [], acs: [], streets: [], cos: [] };

	// ── Filters ───────────────────────────────────────────────────────────────
	const $groupBy = page.add_field({ fieldtype:"Select", fieldname:"group_by", label:"View By",
		options:"Day\nWeek\nMonth", default:"Day", change() { render(); } });
	const $from = page.add_field({ fieldtype:"Date", fieldname:"date_from", label:"From",
		default: frappe.datetime.month_start(), change() { render(); } });
	const $to = page.add_field({ fieldtype:"Date", fieldname:"date_to", label:"To",
		default: frappe.datetime.nowdate(), change() { render(); } });
	const $org    = page.add_field({ fieldtype:"Select", fieldname:"org",    label:"Org",    options:"", change() { cascadeIU(); render(); } });
	const $iu     = page.add_field({ fieldtype:"Select", fieldname:"iu",     label:"IU",     options:"", change() { cascadeAC(); render(); } });
	const $ac     = page.add_field({ fieldtype:"Select", fieldname:"ac",     label:"AC",     options:"", change() { cascadeStreet(); render(); } });
	const $street = page.add_field({ fieldtype:"Select", fieldname:"street", label:"Street", options:"", change() { cascadeCO(); render(); } });
	const $co     = page.add_field({ fieldtype:"Select", fieldname:"co",     label:"CO",     options:"", change() { render(); } });
	page.add_inner_button("Refresh", () => loadMeta());

	// ── Layout ────────────────────────────────────────────────────────────────
	$(`<div style="padding:16px">
		<div id="apt-totals" style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap"></div>
		<div id="apt-chart-wrap" style="background:#fff;border:1px solid #eee;border-radius:8px;padding:16px 16px 8px;margin-bottom:20px">
			<div id="apt-chart"></div>
		</div>
		<div id="apt-table-wrap"></div>
	</div>`).appendTo($(wrapper).find(".page-content"));

	// ── Cascade ───────────────────────────────────────────────────────────────
	function setSelect($f, opts, keep) {
		const cur = $f.get_value();
		const all = [""].concat(opts);
		$f.$wrapper.find("select").empty();
		all.forEach(o => $f.$wrapper.find("select").append(`<option value="${o}">${o || "(All)"}</option>`));
		$f.set_value(keep && all.includes(cur) ? cur : "");
	}
	function cascadeIU()     { setSelect($iu,     _meta.ius,     false); cascadeAC(); }
	function cascadeAC()     { setSelect($ac,     _meta.acs,     false); cascadeStreet(); }
	function cascadeStreet() { setSelect($street, _meta.streets, false); cascadeCO(); }
	function cascadeCO() {
		const $sel = $co.$wrapper.find("select");
		$sel.empty().append(`<option value="">(All)</option>`);
		_meta.cos.forEach(x => $sel.append(`<option value="${x.v}">${x.label || x.v}</option>`));
		$co.set_value("");
	}

	// ── Meta ──────────────────────────────────────────────────────────────────
	function loadMeta() {
		frappe.call({
			method: "changemakers.dashboard_api.get_trends_filter_meta",
			callback({ message: m }) {
				_meta = { orgs: m.orgs||[], ius: m.ius||[], acs: m.acs||[], streets: m.streets||[], cos: m.cos||[] };
				setSelect($org,    _meta.orgs,    true);
				setSelect($iu,     _meta.ius,     true);
				setSelect($ac,     _meta.acs,     true);
				setSelect($street, _meta.streets, true);
				cascadeCO();
				render();
			},
		});
	}

	// ── Render ────────────────────────────────────────────────────────────────
	let _lastData = null;
	let _chart = null;

	function getFilters() {
		return {
			implementing_org:  $org.get_value()    || "",
			intervention_unit: $iu.get_value()     || "",
			ac:                $ac.get_value()     || "",
			street:            $street.get_value() || "",
			co:                $co.get_value()     || "",
		};
	}

	function render() {
		frappe.call({
			method: "changemakers.dashboard_api.get_application_trends",
			args: {
				date_from: $from.get_value() || frappe.datetime.month_start(),
				date_to:   $to.get_value()   || frappe.datetime.nowdate(),
				group_by:  ($groupBy.get_value() || "Day").toLowerCase(),
				filters:   JSON.stringify(getFilters()),
			},
			callback({ message: data }) {
				_lastData = data;
				renderTotals(data);
				renderChart(data);
				renderTable(data);
			},
		});
	}

	// ── Totals (clickable) ────────────────────────────────────────────────────
	const METRIC_COLOR = { aadhaar: "#3498db", income: "#27ae60", cmchis: "#e67e22" };
	const METRIC_LABEL = { aadhaar: "Aadhaar Applied", income: "Income Cert Applied", cmchis: "CMCHIS Applied" };

	function renderTotals(data) {
		const t = data.totals || {};
		const card = (metric) => {
			const val   = t[metric] != null ? t[metric] : "—";
			const color = METRIC_COLOR[metric];
			const label = METRIC_LABEL[metric];
			return `<div class="apt-card" data-metric="${metric}"
				style="background:${color};border-radius:8px;padding:14px 28px;text-align:center;
				       min-width:140px;cursor:pointer;transition:opacity .15s"
				onmouseover="this.style.opacity='.85'" onmouseout="this.style.opacity='1'">
				<div style="font-size:30px;font-weight:700;color:#fff">${val}</div>
				<div style="font-size:12px;color:rgba(255,255,255,.85);margin-top:2px">${label}</div>
				<div style="font-size:10px;color:rgba(255,255,255,.7);margin-top:4px">Cumulative up to selected end date · click to drill down ↓</div>
			</div>`;
		};
		$("#apt-totals").html(card("aadhaar") + card("income") + card("cmchis"));

		$(".apt-card").on("click", function () {
			openDrilldown($(this).data("metric"));
		});
	}

	// ── Chart ─────────────────────────────────────────────────────────────────
	function renderChart(data) {
		const allPeriods = [...new Set([
			...data.aadhaar.map(r => r.period),
			...data.income.map(r => r.period),
			...data.cmchis.map(r => r.period),
		])].sort();

		if (!allPeriods.length) {
			$("#apt-chart").html(`<p style="color:#aaa;text-align:center;padding:32px">No data for selected period.</p>`);
			return;
		}
		const labelMap = {};
		[...data.aadhaar, ...data.income, ...data.cmchis].forEach(r => { labelMap[r.period] = r.label; });
		const labels = allPeriods.map(p => labelMap[p] || p);
		const toArr  = series => {
			const arr = new Array(allPeriods.length).fill(0);
			series.forEach(r => { arr[allPeriods.indexOf(r.period)] = r.count; });
			return arr;
		};
		$("#apt-chart").empty();
		_chart = null;
		_chart = new frappe.Chart("#apt-chart", {
			type: "bar", height: 240,
			colors: ["#3498db", "#27ae60", "#e67e22"],
			data: {
				labels,
				datasets: [
					{ name: "Aadhaar Applied",    values: toArr(data.aadhaar) },
					{ name: "Income Cert Applied", values: toArr(data.income)  },
					{ name: "CMCHIS Applied",      values: toArr(data.cmchis)  },
				],
			},
			axisOptions: { xIsSeries: true },
			barOptions:  { spaceRatio: 0.3 },
		});
	}

	// ── Table ─────────────────────────────────────────────────────────────────
	function renderTable(data) {
		const allPeriods = [...new Set([
			...data.aadhaar.map(r => r.period),
			...data.income.map(r => r.period),
			...data.cmchis.map(r => r.period),
		])].sort();
		if (!allPeriods.length) { $("#apt-table-wrap").empty(); return; }

		const byP = arr => Object.fromEntries(arr.map(r => [r.period, r]));
		const aM  = byP(data.aadhaar), iM = byP(data.income), cM = byP(data.cmchis);

		const rows = allPeriods.map((p, i) => {
			const bg = i % 2 === 0 ? "#fff" : "#fafafa";
			const a  = (aM[p] || {}).count || 0;
			const ic = (iM[p] || {}).count || 0;
			const cm = (cM[p] || {}).count || 0;
			const lbl = ((aM[p] || iM[p] || cM[p]) || {}).label || p;
			return `<tr style="background:${bg}">
				<td style="padding:7px 12px;font-weight:500">${lbl}</td>
				<td style="padding:7px 12px;text-align:center;color:#3498db;font-weight:600">${a  || "—"}</td>
				<td style="padding:7px 12px;text-align:center;color:#27ae60;font-weight:600">${ic || "—"}</td>
				<td style="padding:7px 12px;text-align:center;color:#e67e22;font-weight:600">${cm || "—"}</td>
			</tr>`;
		}).join("");

		$("#apt-table-wrap").html(`
			<table style="width:100%;border-collapse:collapse;border:1px solid #eee;border-radius:8px;overflow:hidden;font-size:13px">
				<thead>
					<tr style="background:#f4f4f4;font-size:11px;text-transform:uppercase;color:#555">
						<th style="padding:8px 12px;text-align:left">Period</th>
						<th style="padding:8px 12px;text-align:center;color:#3498db">Aadhaar Applied</th>
						<th style="padding:8px 12px;text-align:center;color:#27ae60">Income Cert Applied</th>
						<th style="padding:8px 12px;text-align:center;color:#e67e22">CMCHIS Applied</th>
					</tr>
				</thead>
				<tbody>${rows}</tbody>
			</table>`);
	}

	// ── Drilldown modal ───────────────────────────────────────────────────────
	// Stack: [{level, label, filters}]
	let _ddMetric  = null;
	let _ddStack   = [];
	let _ddDialog  = null;

	const LEVELS = ["org", "iu", "street", "hh"];
	const LEVEL_LABEL = { org: "Partner", iu: "Intervention Unit", street: "Street", hh: "Household" };
	const NEXT_FILTER_KEY = { org: "implementing_org", iu: "intervention_unit", street: "street_name" };

	function openDrilldown(metric) {
		_ddMetric = metric;
		_ddStack  = [{ level: "org", label: "All Partners", filters: {} }];

		_ddDialog = new frappe.ui.Dialog({
			title: METRIC_LABEL[metric] + " — Drilldown",
			size:  "large",
		});
		_ddDialog.$wrapper.find(".modal-body").css({ padding: "0", maxHeight: "70vh", overflowY: "auto" });
		_ddDialog.show();
		loadDrillLevel();
	}

	function loadDrillLevel() {
		const top     = _ddStack[_ddStack.length - 1];
		const filters = Object.assign({}, getFilters(), top.filters);
		const date_from = $from.get_value() || frappe.datetime.month_start();
		const date_to   = $to.get_value()   || frappe.datetime.nowdate();

		frappe.call({
			method: "changemakers.dashboard_api.get_application_drilldown",
			args: { metric: _ddMetric, date_from, date_to, level: top.level, filters: JSON.stringify(filters) },
			callback({ message: rows }) {
				renderDrillLevel(rows, top);
			},
		});
	}

	function renderDrillLevel(rows, top) {
		const color  = METRIC_COLOR[_ddMetric];
		const isHH   = top.level === "hh";

		// Breadcrumb
		const crumbs = _ddStack.map((s, i) => {
			const isLast = i === _ddStack.length - 1;
			return isLast
				? `<span style="color:#333;font-weight:600">${s.label}</span>`
				: `<a class="dd-crumb" data-idx="${i}" style="color:${color};cursor:pointer">${s.label}</a>`;
		}).join(" &rsaquo; ");

		// Table
		let tableHtml = "";
		if (!rows.length) {
			tableHtml = `<p style="color:#aaa;padding:24px;text-align:center">No data.</p>`;
		} else if (isHH) {
			// HH-level: different columns per metric
			const isCmchis = _ddMetric === "cmchis";
			const heads = isCmchis
				? ["Household", "Street", "IU", "Org", "AC", "CO", "Applied On"]
				: ["Individual", "Household", "Street", "CO", "Applied On"];
			const bodyR = rows.map((r, i) => {
				const bg = i % 2 === 0 ? "#fff" : "#fafafa";
				const cells = isCmchis
					? [r.hh, r.street, r.iu, r.org, r.ac, r.co, r.date]
					: [r.individual, r.hh, r.street, r.co, r.date];
				return `<tr style="background:${bg}">` +
					cells.map(c => `<td style="padding:6px 10px;font-size:12px">${c || "—"}</td>`).join("") +
					`</tr>`;
			}).join("");
			tableHtml = `<table style="width:100%;border-collapse:collapse;font-size:12px">
				<thead><tr style="background:#f4f4f4;text-transform:uppercase;font-size:11px;color:#555">
					${heads.map(h => `<th style="padding:7px 10px;text-align:left">${h}</th>`).join("")}
				</tr></thead>
				<tbody>${bodyR}</tbody></table>`;
		} else {
			const nextLevel = LEVELS[LEVELS.indexOf(top.level) + 1];
			const bodyR = rows.map((r, i) => {
				const bg   = i % 2 === 0 ? "#fff" : "#fafafa";
				const pct  = rows[0].count > 0 ? Math.round(r.count / rows[0].count * 100) : 0;
				const bar  = `<div style="background:${color};opacity:.25;height:8px;border-radius:4px;width:${pct}%;min-width:4px"></div>`;
				const link = nextLevel
					? `<a class="dd-row" data-key="${encodeURIComponent(r.key)}" data-label="${encodeURIComponent(r.label)}"
					      style="color:${color};cursor:pointer;font-weight:600">${r.label}</a>`
					: `<span style="font-weight:500">${r.label}</span>`;
				return `<tr style="background:${bg}">
					<td style="padding:7px 10px">${link}</td>
					<td style="padding:7px 10px;width:40%">${bar}</td>
					<td style="padding:7px 10px;text-align:right;font-weight:600">${r.count}</td>
				</tr>`;
			}).join("");
			tableHtml = `<table style="width:100%;border-collapse:collapse">
				<thead><tr style="background:#f4f4f4;font-size:11px;text-transform:uppercase;color:#555">
					<th style="padding:7px 10px;text-align:left">${LEVEL_LABEL[top.level]}</th>
					<th style="padding:7px 10px"></th>
					<th style="padding:7px 10px;text-align:right">Count</th>
				</tr></thead>
				<tbody>${bodyR}</tbody></table>`;
		}

		const $body = _ddDialog.$wrapper.find(".modal-body");
		$body.html(`
			<div style="padding:12px 16px;border-bottom:1px solid #eee;font-size:12px;color:#888">${crumbs}</div>
			<div id="dd-table">${tableHtml}</div>
		`);

		// Breadcrumb click → pop to that level
		$body.find(".dd-crumb").on("click", function () {
			const idx = parseInt($(this).data("idx"));
			_ddStack = _ddStack.slice(0, idx + 1);
			loadDrillLevel();
		});

		// Row click → drill down
		$body.find(".dd-row").on("click", function () {
			const key      = decodeURIComponent($(this).data("key"));
			const label    = decodeURIComponent($(this).data("label"));
			const filterKey = NEXT_FILTER_KEY[top.level];
			const newFilters = Object.assign({}, top.filters, { [filterKey]: key });
			const nextLevel  = LEVELS[LEVELS.indexOf(top.level) + 1];
			_ddStack.push({ level: nextLevel, label, filters: newFilters });
			loadDrillLevel();
		});
	}

	loadMeta();
};
