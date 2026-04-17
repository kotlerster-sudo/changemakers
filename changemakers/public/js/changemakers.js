frappe.provide("changemakers.utils");

function set_query_for_district(frm) {
	frm.set_query("district", () => {
		return {
			filters: {
				state: frm.doc.state,
			},
		};
	});
}

function set_query_for_zone(frm) {
	frm.set_query("zone", () => {
		return {
			filters: {
				district: frm.doc.district,
			},
		};
	});
}

function set_query_for_ward(frm) {
	frm.set_query("ward", () => {
		return {
			filters: {
				zone: frm.doc.zone,
			},
		};
	});
}

changemakers.utils.handle_state_field = (frm) => {
	set_query_for_district(frm);
	// Clear the district if it does not belong to that state
	frappe.db.get_value("District", frm.doc.district, "state", (r) => {
		if (r.state != frm.doc.state) {
			frm.set_value("district", "");
			frm.set_value("zone", "");
			frm.set_value("ward", "");
		}
	});
};

changemakers.utils.handle_district_field = (frm) => {
	set_query_for_zone(frm);
	if (frm.doc.district) {
		frappe.db.get_value("District", frm.doc.district, "state", (r) => {
			frm.set_value("state", r.state);
		});
	}
};

changemakers.utils.handle_zone_field = (frm) => {
	set_query_for_ward(frm);
	if (frm.doc.zone) {
		frappe.db.get_value("Zone", frm.doc.zone, "district", (r) => {
			frm.set_value("district", r.district);
		});
	}
};

changemakers.utils.handle_ward_field = (frm) => {
	if (frm.doc.ward) {
		frappe.db.get_value("Ward", frm.doc.ward, "zone", (r) => {
			frm.set_value("zone", r.zone);
		});
	}
};

changemakers.utils.set_query_for_district = set_query_for_district;
changemakers.utils.set_query_for_zone = set_query_for_zone;
changemakers.utils.set_query_for_ward = set_query_for_ward;

// ── Neon dark theme for WRP Performance reports ───────────────────────────────
function injectNeonDarkTheme() {
    if (document.getElementById("neon-dark-report-style")) return;
    var s = document.createElement("style");
    s.id = "neon-dark-report-style";
    s.textContent = [
        ".report-wrapper .datatable { background:#0d0d0d; border-color:#1e1e1e; }",
        ".report-wrapper .dt-scrollable { background:#0d0d0d !important; }",
        ".report-wrapper .dt-freeze { background:#0d0d0d !important; }",
        ".report-wrapper .dt-cell { background:#0d0d0d !important; border-color:#1e1e1e !important; }",
        ".report-wrapper .dt-cell__content { background:#0d0d0d !important; color:#d8d8d8 !important; }",
        ".report-wrapper .dt-cell--header .dt-cell__content { background:#111 !important; color:#e0e0e0 !important; font-weight:600; border-bottom:1px solid #2a2a2a !important; }",
        ".report-wrapper .dt-row:hover .dt-cell { background:#181818 !important; }",
        ".report-wrapper .dt-row:hover .dt-cell__content { background:#181818 !important; }",
        ".report-wrapper .dt-input { background:#1a1a1a !important; color:#e0e0e0 !important; border-color:#333 !important; }",
        ".report-wrapper .dt-cell--alt .dt-cell__content { background:#0f0f0f !important; }",
    ].join("\n");
    document.head.appendChild(s);
}


// ── WRP Programme Dashboard — auto-init via MutationObserver ─────────────────
(function () {
  var _dashInited = false;

  function _initDash() {
    if (_dashInited) return;
    var root = document.getElementById('wrp-dash-root');
    if (!root) return;
    _dashInited = true;

  var ROOT = null; // set inside init() after HTML is in DOM
    var PANEL_TITLES = {
      unvisited:            'Unvisited Households',
      visited_no_change_7d: 'Visited \u2014 No Change in 7 Days',
      stagnant_14d:         'Stagnant 14+ Days (2+ Visits)',
      aadhaar_internal_sla: 'Aadhaar Internal Applied \u2014 SLA Exceeded',
      aadhaar_external_sla: 'Aadhaar External Applied \u2014 SLA Exceeded',
      income_sla:           'Income Cert Applied \u2014 SLA Exceeded',
      cmchis_sla:           'CMCHIS Applied \u2014 SLA Exceeded',
      co_below_25:          'COs Below 25% Visit Target',
      co_below_50:          'COs 25\u201350% Visit Target',
      co_below_75:          'COs 50\u201375% Visit Target',
      co_low_impact:        'Low-Impact COs'
    };
    var LEVEL_LABELS = ['org','iu','street','co','hh','individual'];
    var _data = null, _filters = {}, _navStack = [], _overlayEl = null, _panelEl = null;
  
    function api(method, args) {
      return new Promise(function(res, rej) {
        var t = setTimeout(function() { rej(new Error('API timeout: ' + method)); }, 20000);
        frappe.call({method: method, args: args,
          callback: function(r) { clearTimeout(t); res(r.message); },
          error:    function(e) { clearTimeout(t); rej(typeof e === 'object' ? e : new Error(String(e))); }
        });
      });
    }
  
    function fmt(n) {
      if (n === null || n === undefined) return '\u2014';
      return Number(n).toLocaleString();
    }
    function esc(s) {
      if (!s) return '';
      return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');
    }
    function smallCard(val, lbl, color) {
      return '<div class="wrp-card"><div class="wrp-card-val" style="color:'+color+'">'+fmt(val)+'</div><div class="wrp-card-lbl">'+lbl+'</div></div>';
    }
  
    async function init() {
      ROOT = document.getElementById('wrp-dash-root');
      if (!ROOT) { console.error('WRP: #wrp-dash-root not in DOM yet, retrying…'); setTimeout(init, 200); return; }
      try {
        ROOT.innerHTML = '<div class="wrp-loading"><span class="spinner-border spinner-border-sm"></span> Loading\u2026</div>';
        _data = await api('changemakers.dashboard_api.get_dashboard_overview', {filters: _filters});
        if (!_data || _data.error === 'no_access') {
          ROOT.innerHTML = '<div class="wrp-loading">No data access for your account.</div>'; return;
        }
        renderDashboard();
        buildPanel();
      } catch(err) {
        var msg = err && (err.message || err.statusCode || String(err)) || 'unknown error';
        if (ROOT) ROOT.innerHTML = '<div class="wrp-loading" style="color:red;padding:20px;white-space:pre-wrap"><b>Dashboard error</b>\n' + msg + '</div>';
        console.error('WRP Dashboard init:', err);
      }
    }
  
    function renderDashboard() {
      var s = _data.structure, p = _data.pipeline, a = _data.alerts, c = _data.co_performance;
      var scope = '<div class="wrp-scope"><label>Scope:</label>'
        + '<label>Org</label><select id="wrp-f-org"><option value="">All</option></select>'
        + '<label>IU</label><select id="wrp-f-iu"><option value="">All</option></select>'
        + '<label>Street</label><select id="wrp-f-st"><option value="">All</option></select>'
        + '<button onclick="wrpDashRefresh()">Apply</button></div>';
  
      var struct = '<div class="wrp-section-title">Programme Structure</div><div class="wrp-row">'
        + smallCard(s.orgs,    'Organisations',        '#4f46e5')
        + smallCard(s.ius,     'Intervention Units',   '#4f46e5')
        + smallCard(s.streets, 'Streets',              '#4f46e5')
        + smallCard(s.cos,     'Community Organisers', '#4f46e5')
        + smallCard(s.acs,     'Area Coordinators',    '#4f46e5')
        + smallCard(s.pms,     'Programme Managers',   '#4f46e5')
        + '</div>';
  
      var total = p.total || 1;
      var pRows = [
        {key:'unvisited',       label:'Unvisited',           color:'#6b7280', drill:'unvisited'},
        {key:'missing_both',    label:'Missing Both Docs',   color:'#f59e0b', drill:null},
        {key:'missing_aadhaar', label:'Missing Aadhaar',     color:'#f59e0b', drill:null},
        {key:'missing_income',  label:'Missing Income Cert', color:'#f59e0b', drill:null},
        {key:'docs_ready',      label:'Docs Ready',          color:'#8b5cf6', drill:null},
        {key:'applied',         label:'CMCHIS Applied',      color:'#3b82f6', drill:null},
        {key:'active',          label:'CMCHIS Active \u2605',color:'#22c55e', drill:null},
        {key:'rejected',        label:'Rejected',            color:'#ef4444', drill:null}
      ];
      var pipe = '<div class="wrp-section-title">Pipeline \u2014 '+fmt(p.total)+' Households</div>'
        + '<div style="padding:8px 12px;background:var(--card-bg,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:8px">';
      for (var i=0;i<pRows.length;i++) {
        var r = pRows[i], cnt = p[r.key]||0, pct = (cnt/total*100).toFixed(1);
        var cls = r.drill ? 'clickable' : '', click = r.drill ? 'onclick="wrpDrill(\''+r.drill+'\',\'org\',null,\''+esc(PANEL_TITLES[r.drill]||r.label)+'\')"' : '';
        pipe += '<div class="wrp-pipe-row '+cls+'" '+click+'>'
          + '<div class="wrp-pipe-lbl">'+r.label+'</div>'
          + '<div class="wrp-pipe-bar"><div class="wrp-pipe-fill" style="width:'+pct+'%;background:'+r.color+'"></div></div>'
          + '<div class="wrp-pipe-cnt" style="color:'+r.color+'">'+fmt(cnt)+'</div>'
          + '<div class="wrp-pipe-pct">'+pct+'%</div></div>';
      }
      pipe += '</div>';
  
      var alertDefs = [
        {key:'visited_no_change_7d', val:a.visited_no_change_7d, lbl:'Visited \u2014 No Change 7d',       cls:'orange'},
        {key:'stagnant_14d',         val:a.stagnant_14d,         lbl:'Stagnant 14d+ (2+ visits)',          cls:'orange'},
        {key:'aadhaar_internal_sla', val:a.aadhaar_internal_sla, lbl:'Aadhaar Internal \u2192 SLA',        cls:'red'},
        {key:'aadhaar_external_sla', val:a.aadhaar_external_sla, lbl:'Aadhaar External \u2192 SLA',        cls:'red'},
        {key:'income_sla',           val:a.income_sla,           lbl:'Income Cert \u2192 SLA',             cls:'red'},
        {key:'cmchis_sla',           val:a.cmchis_sla,           lbl:'CMCHIS Applied \u2192 SLA',          cls:'blue'}
      ];
      var alerts = '<div class="wrp-section-title">Alerts \u26a0\ufe0f</div><div class="wrp-row">';
      for (var j=0;j<alertDefs.length;j++) {
        var ac = alertDefs[j];
        alerts += '<div class="wrp-alert '+ac.cls+'" onclick="wrpDrill(\''+ac.key+'\',\'org\',null,\''+esc(PANEL_TITLES[ac.key]||ac.lbl)+'\')">'
          + '<div class="wrp-alert-val">'+fmt(ac.val)+'</div>'
          + '<div class="wrp-alert-lbl">'+ac.lbl+'</div></div>';
      }
      alerts += '</div>';
  
      var cc = c.counts;
      var coDefs = [
        {key:'co_below_25',  val:cc.below_25,   lbl:'COs &lt;25% target',  cls:'red'},
        {key:'co_below_50',  val:cc.below_50,   lbl:'COs 25\u201350% target', cls:'orange'},
        {key:'co_below_75',  val:cc.below_75,   lbl:'COs 50\u201375% target', cls:'orange'},
        {key:'co_low_impact',val:cc.low_impact, lbl:'Low-Impact COs',      cls:'blue'}
      ];
      var coHtml = '<div class="wrp-section-title">CO Performance</div><div class="wrp-row">';
      for (var k=0;k<coDefs.length;k++) {
        var co = coDefs[k];
        coHtml += '<div class="wrp-alert '+co.cls+'" onclick="wrpDrill(\''+co.key+'\',\'co\',null,\''+esc(PANEL_TITLES[co.key]||co.lbl)+'\')">'
          + '<div class="wrp-alert-val">'+fmt(co.val)+'</div>'
          + '<div class="wrp-alert-lbl">'+co.lbl+'</div></div>';
      }
      coHtml += '</div>';
  
      ROOT.innerHTML = scope + struct + pipe + alerts + coHtml;
      populateScopeOptions();
    }
  
    function populateScopeOptions() {
      Promise.all([
        frappe.db.get_list('Street List  - WRP', {fields:['implementing_org'], group_by:'implementing_org', limit:200}),
        frappe.db.get_list('Street List  - WRP', {fields:['intervention_units'], group_by:'intervention_units', limit:500}),
        frappe.db.get_list('Street List  - WRP', {fields:['name'], limit:1000})
      ]).then(function(results) {
        function fill(id, items, field) {
          var el = document.getElementById(id); if (!el) return;
          var cur = el.value;
          el.innerHTML = '<option value="">All</option>' + items.filter(function(r){return r[field];}).map(function(r){return '<option'+(r[field]===cur?' selected':'')+'>'+esc(r[field])+'</option>';}).join('');
        }
        fill('wrp-f-org', results[0], 'implementing_org');
        fill('wrp-f-iu',  results[1], 'intervention_units');
        fill('wrp-f-st',  results[2], 'name');
      }).catch(function(){});
    }
  
    window.wrpDashRefresh = function() {
      _filters = {};
      var org = document.getElementById('wrp-f-org');  if (org && org.value)  _filters.implementing_org  = org.value;
      var iu  = document.getElementById('wrp-f-iu');   if (iu  && iu.value)   _filters.intervention_unit = iu.value;
      var st  = document.getElementById('wrp-f-st');   if (st  && st.value)   _filters.street            = st.value;
      init();
    };
  
    function buildPanel() {
      if (document.getElementById('wrp-panel-overlay')) return;
      _overlayEl = document.createElement('div');
      _overlayEl.id = 'wrp-panel-overlay';
      _overlayEl.className = 'wrp-panel-overlay';
      _overlayEl.onclick = function(e) { if (e.target===_overlayEl) closePanel(); };
      _panelEl = document.createElement('div');
      _panelEl.className = 'wrp-panel';
      _panelEl.innerHTML = '<div class="wrp-panel-head">'
        + '<button class="back" onclick="wrpPanelBack()">\u2190 Back</button>'
        + '<div class="title" id="wrp-panel-title">Loading\u2026</div>'
        + '<button class="close" onclick="wrpPanelClose()">&times;</button></div>'
        + '<div class="wrp-panel-body" id="wrp-panel-body">'
        + '<div class="wrp-panel-loading"><span class="spinner-border spinner-border-sm"></span> Loading\u2026</div></div>';
      _overlayEl.appendChild(_panelEl);
      document.body.appendChild(_overlayEl);
    }
  
    function openPanel()  { _overlayEl.classList.add('open'); setTimeout(function(){_panelEl.classList.add('open');},10); }
    function closePanel() { _panelEl.classList.remove('open'); _overlayEl.classList.remove('open'); _navStack=[]; }
  
    window.wrpPanelClose = closePanel;
    window.wrpPanelBack  = function() { if (_navStack.length<=1){closePanel();return;} _navStack.pop(); renderPanelData(_navStack[_navStack.length-1]); };
  
    window.wrpDrill = async function(metric, level, parent, titleHint) {
      openPanel();
      document.getElementById('wrp-panel-title').textContent = titleHint || PANEL_TITLES[metric] || metric;
      document.getElementById('wrp-panel-body').innerHTML = '<div class="wrp-panel-loading"><span class="spinner-border spinner-border-sm"></span> Loading\u2026</div>';
      var result = await api('changemakers.dashboard_api.get_drilldown', {metric:metric, level:level, parent:parent||null, filters:_filters});
      var frame = {metric:metric, level:level, parent:parent, title:titleHint||PANEL_TITLES[metric]||metric, rows:result.rows||[], columns:result.columns||[]};
      _navStack.push(frame);
      renderPanelData(frame);
    };
  
    function renderPanelData(frame) {
      document.getElementById('wrp-panel-title').textContent = frame.title;
      var body = document.getElementById('wrp-panel-body');
      var crumb = '<div class="wrp-breadcrumb">';
      for (var i=0;i<_navStack.length;i++) {
        var n=_navStack[i];
        crumb += (i<_navStack.length-1) ? '<span onclick="wrpPanelJump('+i+')">'+esc(n.title)+'</span> &rsaquo; ' : '<b>'+esc(n.title)+'</b>';
      }
      crumb += '</div>';
      var rows=frame.rows, columns=frame.columns;
      if (!rows||rows.length===0){body.innerHTML=crumb+'<div class="wrp-empty">\u2713 No issues found.</div>';return;}
      var isAgg = columns.length===2 && columns[1].fieldname==='count';
      var nextLevel = LEVEL_LABELS[LEVEL_LABELS.indexOf(frame.level)+1]||null;
      var html = crumb+'<div class="wrp-table-wrap"><table class="wrp-table"><thead><tr>';
      for (var c=0;c<columns.length;c++) html += '<th>'+esc(columns[c].label)+'</th>';
      if (isAgg) html += '<th></th>';
      html += '</tr></thead><tbody>';
      for (var r=0;r<rows.length;r++) {
        var row=rows[r], drillable=isAgg&&nextLevel;
        html += '<tr class="'+(drillable?'drillable':'')+'"'+(drillable?' onclick="wrpDrillDown(\''+esc(frame.metric)+'\',\''+nextLevel+'\',\''+esc(row.name)+'\',\''+esc(frame.title+' \u203a '+row.name)+'\')"':'')+' >';
        for (var cc=0;cc<columns.length;cc++) { var val=row[columns[cc].fieldname]; html+='<td>'+esc(val===null||val===undefined?'':String(val))+'</td>'; }
        if (isAgg) html += '<td style="color:var(--primary,#4f46e5);font-size:11px">Drill \u2192</td>';
        html += '</tr>';
      }
      html += '</tbody></table></div><div style="font-size:11px;color:var(--text-muted);margin-top:10px;text-align:right">'+fmt(rows.length)+' row'+(rows.length!==1?'s':'')+'</div>';
      body.innerHTML = html;
    }
  
    window.wrpPanelJump = function(idx) { _navStack=_navStack.slice(0,idx+1); renderPanelData(_navStack[_navStack.length-1]); };
  
    window.wrpDrillDown = async function(metric, level, parent, title) {
      document.getElementById('wrp-panel-body').innerHTML='<div class="wrp-panel-loading"><span class="spinner-border spinner-border-sm"></span> Loading\u2026</div>';
      var result = await api('changemakers.dashboard_api.get_drilldown',{metric:metric,level:level,parent:parent,filters:_filters});
      var frame = {metric:metric,level:level,parent:parent,title:title,rows:result.rows||[],columns:result.columns||[]};
      _navStack.push(frame);
      renderPanelData(frame);
    };
  
    // kick off
    init();
  }

  // Try immediately (page already loaded) then watch for DOM changes
  frappe.ready(function () {
    _initDash();
    if (!_dashInited) {
      var obs = new MutationObserver(function () {
        if (document.getElementById('wrp-dash-root')) {
          obs.disconnect();
          _initDash();
        }
      });
      obs.observe(document.body, { childList: true, subtree: true });
    }
  });
})();
