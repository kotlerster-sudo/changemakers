frappe.pages["wrp-application-trends"].on_page_load = function (wrapper) {
	const page = frappe.ui.make_app_page({
		parent: wrapper,
		title: "Application Trends",
		single_column: true,
	});

	// ── Filter state ──────────────────────────────────────────────────────────
	let _meta = { orgs: [], ius: [], acs: [], streets: [], cos: [] };

	// ── Filters ───────────────────────────────────────────────────────────────
	const $groupBy = page.add_field({
		fieldtype: "Select",
		fieldname: "group_by",
		label: "View By",
		options: "Day\nWeek\nMonth",
		default: "Day",
		change() { render(); },
	});

	const $from = page.add_field({
		fieldtype: "Date",
		fieldname: "date_from",
		label: "From",
		default: frappe.datetime.month_start(),
		change() { render(); },
	});

	const $to = page.add_field({
		fieldtype: "Date",
		fieldname: "date_to",
		label: "To",
		default: frappe.datetime.nowdate(),
		change() { render(); },
	});

	const $org = page.add_field({
		fieldtype: "Select", fieldname: "org", label: "Org",
		options: "", change() { cascadeIU(); render(); },
	});

	const $iu = page.add_field({
		fieldtype: "Select", fieldname: "iu", label: "Intervention Unit",
		options: "", change() { cascadeAC(); render(); },
	});

	const $ac = page.add_field({
		fieldtype: "Select", fieldname: "ac", label: "AC",
		options: "", change() { cascadeStreet(); render(); },
	});

	const $street = page.add_field({
		fieldtype: "Select", fieldname: "street", label: "Street",
		options: "", change() { cascadeCO(); render(); },
	});

	const $co = page.add_field({
		fieldtype: "Select", fieldname: "co", label: "CO",
		options: "", change() { render(); },
	});

	page.add_inner_button("Refresh", () => loadMeta());

	// ── Layout ────────────────────────────────────────────────────────────────
	const $body = $(`
		<div style="padding:16px">
			<div id="apt-totals" style="display:flex;gap:12px;margin-bottom:20px;flex-wrap:wrap"></div>
			<div id="apt-chart-wrap" style="background:#fff;border:1px solid #eee;border-radius:8px;padding:16px;margin-bottom:20px">
				<div id="apt-chart"></div>
			</div>
			<div id="apt-table-wrap"></div>
		</div>
	`).appendTo($(wrapper).find(".page-content"));

	// ── Cascade helpers ───────────────────────────────────────────────────────
	function setSelect($field, options, preserve) {
		const cur = $field.get_value();
		const opts = [""].concat(options);
		$field.$wrapper.find("select").empty();
		opts.forEach(o => $field.$wrapper.find("select").append(
			`<option value="${o}">${o || "(All)"}</option>`
		));
		$field.set_value(preserve && opts.includes(cur) ? cur : "");
	}

	function cascadeIU() {
		const org = $org.get_value();
		const ius = org ? _meta.ius.filter(x => x.org === org).map(x => x.v) : _meta.ius.map(x => x.v);
		setSelect($iu, [...new Set(ius)].sort(), false);
		cascadeAC();
	}

	function cascadeAC() {
		const org = $org.get_value(), iu = $iu.get_value();
		let acs = _meta.acs;
		if (org) acs = acs.filter(x => x.org === org);
		if (iu)  acs = acs.filter(x => x.iu  === iu);
		setSelect($ac, [...new Set(acs.map(x => x.v))].sort(), false);
		cascadeStreet();
	}

	function cascadeStreet() {
		const org = $org.get_value(), iu = $iu.get_value(), ac = $ac.get_value();
		let streets = _meta.streets;
		if (org) streets = streets.filter(x => x.org === org);
		if (iu)  streets = streets.filter(x => x.iu  === iu);
		if (ac)  streets = streets.filter(x => x.ac  === ac);
		setSelect($street, [...new Set(streets.map(x => x.v))].sort(), false);
		cascadeCO();
	}

	function cascadeCO() {
		const org = $org.get_value(), iu = $iu.get_value(),
		      ac  = $ac.get_value(),  st = $street.get_value();
		let cos = _meta.cos;
		if (org) cos = cos.filter(x => x.org === org);
		if (iu)  cos = cos.filter(x => x.iu  === iu);
		if (ac)  cos = cos.filter(x => x.ac  === ac);
		if (st)  cos = cos.filter(x => x.street === st);
		const $sel = $co.$wrapper.find("select");
		$sel.empty().append(`<option value="">(All)</option>`);
		[...new Map(cos.map(x => [x.v, x])).values()]
			.sort((a, b) => (a.label || "").localeCompare(b.label || ""))
			.forEach(x => $sel.append(`<option value="${x.v}">${x.label || x.v}</option>`));
		$co.set_value("");
	}

	// ── Meta load ─────────────────────────────────────────────────────────────
	function loadMeta() {
		frappe.call({
			method: "changemakers.dashboard_api.get_trends_filter_meta",
			callback({ message: m }) {
				// Enrich with org/iu/ac context from Status Log distinct query
				// The API returns flat lists; we keep them flat and filter by selected values
				_meta = {
					orgs:    (m.orgs    || []),
					ius:     (m.ius     || []).map(v => ({ v })),
					acs:     (m.acs     || []).map(v => ({ v })),
					streets: (m.streets || []).map(v => ({ v })),
					cos:     (m.cos     || []),
				};
				setSelect($org,    _meta.orgs,            true);
				setSelect($iu,     _meta.ius.map(x => x.v), true);
				setSelect($ac,     _meta.acs.map(x => x.v), true);
				setSelect($street, _meta.streets.map(x => x.v), true);
				const $sel = $co.$wrapper.find("select");
				$sel.empty().append(`<option value="">(All)</option>`);
				_meta.cos.forEach(x => $sel.append(`<option value="${x.v}">${x.label || x.v}</option>`));
				render();
			},
		});
	}

	// ── Render ────────────────────────────────────────────────────────────────
	let _chart = null;

	function render() {
		frappe.call({
			method: "changemakers.dashboard_api.get_application_trends",
			args: {
				date_from: $from.get_value() || frappe.datetime.month_start(),
				date_to:   $to.get_value()   || frappe.datetime.nowdate(),
				group_by:  ($groupBy.get_value() || "Day").toLowerCase(),
				filters: JSON.stringify({
					implementing_org:  $org.get_value()    || "",
					intervention_unit: $iu.get_value()     || "",
					ac:                $ac.get_value()     || "",
					street:            $street.get_value() || "",
					co:                $co.get_value()     || "",
				}),
			},
			callback({ message: data }) {
				renderTotals(data);
				renderChart(data);
				renderTable(data);
			},
		});
	}

	// ── Totals strip ──────────────────────────────────────────────────────────
	function renderTotals(data) {
		const sum = arr => arr.reduce((s, r) => s + r.count, 0);
		const card = (label, val, color) =>
			`<div style="background:${color};border-radius:8px;padding:12px 24px;text-align:center;min-width:130px">
				<div style="font-size:28px;font-weight:700;color:#fff">${val}</div>
				<div style="font-size:12px;color:rgba(255,255,255,.85);margin-top:2px">${label}</div>
			</div>`;
		$("#apt-totals").html(
			card("Aadhaar Applied",    sum(data.aadhaar), "#3498db") +
			card("Income Cert Applied",sum(data.income),  "#27ae60") +
			card("CMCHIS Applied",     sum(data.cmchis),  "#e67e22")
		);
	}

	// ── Chart ─────────────────────────────────────────────────────────────────
	function renderChart(data) {
		// Merge all periods across the three series into a sorted label set
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
		[...data.aadhaar, ...data.income, ...data.cmchis].forEach(r => {
			labelMap[r.period] = r.label;
		});
		const labels = allPeriods.map(p => labelMap[p] || p);

		const idx = p => allPeriods.indexOf(p);
		const toArr = series => {
			const arr = new Array(allPeriods.length).fill(0);
			series.forEach(r => { arr[idx(r.period)] = r.count; });
			return arr;
		};

		$("#apt-chart").empty();

		if (_chart) { try { _chart = null; } catch(e) {} }

		_chart = new frappe.Chart("#apt-chart", {
			type:   "bar",
			height: 260,
			colors: ["#3498db", "#27ae60", "#e67e22"],
			data: {
				labels,
				datasets: [
					{ name: "Aadhaar Applied",     values: toArr(data.aadhaar) },
					{ name: "Income Cert Applied",  values: toArr(data.income)  },
					{ name: "CMCHIS Applied",       values: toArr(data.cmchis)  },
				],
			},
			axisOptions: { xIsSeries: true },
			barOptions:  { spaceRatio: 0.3 },
			tooltipOptions: { formatTooltipX: d => d, formatTooltipY: d => `${d} applications` },
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

		const byPeriod = (arr) => Object.fromEntries(arr.map(r => [r.period, r]));
		const aMap = byPeriod(data.aadhaar);
		const iMap = byPeriod(data.income);
		const cMap = byPeriod(data.cmchis);

		const rows = allPeriods.map((p, i) => {
			const bg = i % 2 === 0 ? "#fff" : "#fafafa";
			const a  = (aMap[p] || {}).count || 0;
			const ic = (iMap[p] || {}).count || 0;
			const cm = (cMap[p] || {}).count || 0;
			const label = (aMap[p] || iMap[p] || cMap[p] || {}).label || p;
			return `<tr style="background:${bg}">
				<td style="padding:7px 12px;font-weight:500">${label}</td>
				<td style="padding:7px 12px;text-align:center;color:#3498db;font-weight:600">${a || "—"}</td>
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

	loadMeta();
};
