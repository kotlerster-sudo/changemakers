"""
Creates three Entitlement Dashboard HTML blocks and their Workspaces:
  - Entitlement Programme Dashboard  → OAP Programme workspace (WRP-PM, WRP-MIS, WRP-HR)
  - Entitlement AC Dashboard         → OAP AC workspace       (WRP-AC, WRP-PM)
  - Entitlement MIS Dashboard        → OAP MIS workspace      (WRP-MIS, WRP-PM)
Idempotent — updates existing blocks if they exist.
"""
import json
import frappe

# ─── HTML block content ────────────────────────────────────────────────────────

COMMON_CSS = (
    "#ent-root *{box-sizing:border-box;font-family:var(--font-stack,'Inter',sans-serif)}"
    "#ent-root{--g:#22c55e;--r:#ef4444;--o:#f97316;--y:#eab308;--b:#3b82f6;--p:#7c3aed;--grey:#6b7280;padding:0 2px 24px}"
    ".ent-loading{padding:40px;text-align:center;color:var(--text-muted)}"
    ".ent-sec{font-size:11px;font-weight:700;text-transform:uppercase;letter-spacing:.08em;color:var(--text-muted);margin:20px 0 8px}"
    ".ent-row{display:flex;flex-wrap:wrap;gap:10px;margin-bottom:8px}"
    ".ent-card{flex:1;min-width:100px;padding:12px 14px;background:var(--card-bg,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:8px}"
    ".ent-card.click{cursor:pointer;transition:box-shadow .15s,transform .1s}"
    ".ent-card.click:hover{box-shadow:0 4px 12px rgba(0,0,0,.12);transform:translateY(-1px)}"
    ".ent-val{font-size:22px;font-weight:700;line-height:1.1}"
    ".ent-lbl{font-size:11px;color:var(--text-muted);margin-top:2px}"
    ".ent-scope{display:flex;gap:8px;align-items:center;flex-wrap:wrap;margin-bottom:16px;padding:10px 14px;background:var(--card-bg,#fff);border:1px solid var(--border-color);border-radius:8px}"
    ".ent-scope label{font-size:12px;color:var(--text-muted);margin:0 2px 0 0}"
    ".ent-scope select,.ent-scope button{font-size:12px;padding:4px 8px;border:1px solid var(--border-color);border-radius:4px;background:var(--bg-color,#fff);color:var(--text-color,#111);cursor:pointer}"
    ".ent-scope button{border-color:var(--primary,#4f46e5);color:var(--primary,#4f46e5)}"
    ".ent-pipe-row{display:flex;align-items:center;gap:8px;padding:5px 4px;border-bottom:1px solid var(--border-color,#f3f4f6);border-radius:4px;margin:0 -4px}"
    ".ent-pipe-row:last-child{border:none}"
    ".ent-pipe-row.click{cursor:pointer}"
    ".ent-pipe-row.click:hover{background:var(--bg-color,#f9fafb)}"
    ".ent-pipe-lbl{min-width:130px;font-size:12px}"
    ".ent-pipe-bar{flex:1;height:10px;background:var(--border-color,#e5e7eb);border-radius:5px;overflow:hidden}"
    ".ent-pipe-fill{height:100%;border-radius:5px}"
    ".ent-pipe-cnt{min-width:50px;text-align:right;font-size:12px;font-weight:600}"
    ".ent-pipe-pct{min-width:38px;text-align:right;font-size:11px;color:var(--text-muted)}"
    ".ent-band{flex:1;min-width:110px;padding:12px 14px;border-radius:8px;border:1px solid;text-align:center}"
    ".ent-band-val{font-size:20px;font-weight:700}"
    ".ent-band-lbl{font-size:11px;margin-top:4px}"
    ".ent-overlay{position:fixed;inset:0;background:rgba(0,0,0,.5);z-index:9999;display:none;align-items:center;justify-content:center}"
    ".ent-overlay.open{display:flex}"
    ".ent-panel{width:min(800px,95vw);max-height:88vh;background:var(--card-bg,#fff);border-radius:12px;box-shadow:0 24px 60px rgba(0,0,0,.35);display:flex;flex-direction:column;opacity:0;transform:scale(.96) translateY(8px);transition:opacity .2s,transform .2s}"
    ".ent-panel.open{opacity:1;transform:scale(1) translateY(0)}"
    ".ent-ph{display:flex;align-items:center;gap:8px;padding:14px 18px;border-bottom:1px solid var(--border-color);flex-shrink:0}"
    ".ent-ph .back{background:none;border:1px solid var(--border-color);border-radius:4px;padding:3px 10px;cursor:pointer;font-size:12px}"
    ".ent-ph .ttl{flex:1;font-size:13px;font-weight:600;overflow:hidden;text-overflow:ellipsis;white-space:nowrap}"
    ".ent-ph .cls{background:none;border:none;font-size:20px;cursor:pointer;color:var(--text-muted);line-height:1}"
    ".ent-pb{flex:1;overflow-y:auto;padding:16px 18px}"
    "table.ent-tbl{width:100%;border-collapse:collapse;font-size:12px}"
    "table.ent-tbl th{background:var(--bg-color,#f9fafb);padding:7px 10px;text-align:left;font-weight:600;border-bottom:2px solid var(--border-color);white-space:nowrap}"
    "table.ent-tbl td{padding:7px 10px;border-bottom:1px solid var(--border-color,#f3f4f6)}"
    "table.ent-tbl tr.drill:hover td{background:var(--bg-color,#f0f9ff);cursor:pointer}"
    ".ent-empty{text-align:center;padding:40px;color:var(--text-muted);font-size:13px}"
    ".band-critical{background:#fef2f2;border-color:#fecaca;color:#991b1b}.band-critical .ent-band-val{color:#dc2626}"
    ".band-poor{background:#fff7ed;border-color:#fed7aa;color:#9a3412}.band-poor .ent-band-val{color:#ea580c}"
    ".band-acceptable{background:#fefce8;border-color:#fef08a;color:#713f12}.band-acceptable .ent-band-val{color:#ca8a04}"
    ".band-good{background:#f0fdf4;border-color:#bbf7d0;color:#14532d}.band-good .ent-band-val{color:#16a34a}"
)

# ─── Programme Dashboard ───────────────────────────────────────────────────────

PROG_HTML = '<div id="ent-root"><div class="ent-loading"><span class="spinner-border spinner-border-sm"></span> Loading…</div></div>'

PROG_SCRIPT = r"""
var R=null,_scheme='',_data=null,_perf=null,_ovl=null,_pan=null,_stk=[];
var BUCKET_COLORS={unvisited:'#6b7280',docs_in_progress:'#f59e0b',docs_ready:'#8b5cf6',applied_pending:'#3b82f6',goal:'#22c55e',negative:'#ef4444'};
var BUCKET_LABELS={unvisited:'Unvisited',docs_in_progress:'Docs In Progress',docs_ready:'Docs Ready',applied_pending:'Applied – Pending',goal:'Goal Achieved',negative:'Closed – Negative'};

function api(m,a){return new Promise(function(res,rej){var t=setTimeout(function(){rej(new Error('timeout'));},25000);frappe.call({method:m,args:a,callback:function(r){clearTimeout(t);res(r.message);},error:function(e){clearTimeout(t);rej(e);}});});}
function fmt(n){if(n==null)return '—';return Number(n).toLocaleString();}
function pct(n){if(n==null)return '';return Number(n).toFixed(1)+'%';}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

async function init(){
  R=root_element.querySelector('#ent-root');
  _scheme=localStorage.getItem('ent_scheme_'+frappe.session.user)||'';
  try{
    var schemes=await api('changemakers.generic_dashboard_api.get_dashboard_schemes',{});
    if(!schemes||!schemes.schemes||!schemes.schemes.length){R.innerHTML='<div class="ent-loading">No active schemes found.</div>';return;}
    if(!_scheme||!schemes.schemes.find(function(s){return s.entitlement_code===_scheme;}))
      _scheme=schemes.schemes[0].entitlement_code;
    renderScope(schemes.schemes);
    await loadData();
  }catch(e){R.innerHTML='<div class="ent-loading" style="color:red">Error: '+esc(e&&e.message||String(e))+'</div>';}
}

function renderScope(schemes){
  var opts=schemes.map(function(s){return '<option value="'+esc(s.entitlement_code)+'"'+(s.entitlement_code===_scheme?' selected':'')+'>'+esc(s.entitlement_name)+'</option>';}).join('');
  var scope='<div class="ent-scope"><label>Scheme:</label><select id="ent-sel">'+opts+'</select><button onclick="entRefresh()">Refresh</button></div>';
  var body=R.innerHTML.replace('<div class="ent-loading"><span class="spinner-border spinner-border-sm"></span> Loading…</div>','');
  R.innerHTML=scope+'<div id="ent-body"><div class="ent-loading"><span class="spinner-border spinner-border-sm"></span> Loading…</div></div>';
  var sel=R.querySelector('#ent-sel');
  if(sel)sel.onchange=function(){_scheme=sel.value;localStorage.setItem('ent_scheme_'+frappe.session.user,_scheme);entRefresh();};
}

async function loadData(){
  var body=R.querySelector('#ent-body');
  if(body)body.innerHTML='<div class="ent-loading"><span class="spinner-border spinner-border-sm"></span> Loading…</div>';
  var results=await Promise.all([
    api('changemakers.generic_dashboard_api.get_programme_overview',{entitlement_code:_scheme}),
    api('changemakers.generic_dashboard_api.get_co_performance_table',{entitlement_code:_scheme}),
  ]);
  _data=results[0];_perf=results[1];
  renderDashboard();
  buildPanel();
}

window.entRefresh=function(){
  var sel=R&&R.querySelector('#ent-sel');
  if(sel&&sel.value)_scheme=sel.value;
  localStorage.setItem('ent_scheme_'+frappe.session.user,_scheme);
  loadData();
};

function renderDashboard(){
  if(!_data){return;}
  var total=_data.total||1;
  var cards='<div class="ent-sec">Overview — '+esc(_data.entitlement_name)+'</div><div class="ent-row">'
    +'<div class="ent-card"><div class="ent-val">'+fmt(_data.total)+'</div><div class="ent-lbl">Total Beneficiaries</div></div>'
    +'<div class="ent-card"><div class="ent-val" style="color:var(--b)">'+fmt(_data.visited)+'</div><div class="ent-lbl">Visited ('+pct(_data.coverage_pct)+')</div></div>'
    +'<div class="ent-card"><div class="ent-val" style="color:var(--g)">'+fmt(_data.goal_count)+'</div><div class="ent-lbl">'+esc(_data.final_status_label||'Goal')+' ('+pct(_data.saturation_pct)+')</div></div>'
    +'<div class="ent-card click" onclick="entDrillAlert(\'sla\')"><div class="ent-val" style="color:var(--r)">'+fmt(_data.sla_overdue_count)+'</div><div class="ent-lbl">SLA Overdue</div></div>'
    +'<div class="ent-card click" onclick="entDrillAlert(\'ac_review\')"><div class="ent-val" style="color:var(--o)">'+fmt(_data.pending_ac_reviews)+'</div><div class="ent-lbl">Pending AC Reviews</div></div>'
    +'</div>';

  var bucketOrder=['unvisited','docs_in_progress','docs_ready','applied_pending','goal','negative'];
  var bCounts=_data.bucket_counts||{};
  var pipe='<div class="ent-sec">Pipeline</div><div style="padding:8px 12px;background:var(--card-bg,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:8px">';
  for(var i=0;i<bucketOrder.length;i++){
    var bk=bucketOrder[i],cnt=bCounts[bk]||0,pp=(cnt/total*100).toFixed(1),col=BUCKET_COLORS[bk]||'#6b7280',lbl=BUCKET_LABELS[bk]||bk;
    pipe+='<div class="ent-pipe-row click" onclick="entDrillBucket(\''+esc(bk)+'\',\''+esc(lbl)+'\')">'
      +'<div class="ent-pipe-lbl">'+lbl+'</div>'
      +'<div class="ent-pipe-bar"><div class="ent-pipe-fill" style="width:'+pp+'%;background:'+col+'"></div></div>'
      +'<div class="ent-pipe-cnt" style="color:'+col+'">'+fmt(cnt)+'</div>'
      +'<div class="ent-pipe-pct">'+pp+'%</div></div>';
  }
  pipe+='</div>';

  var bands=_data.update_rate_bands||{};
  var bandHtml='<div class="ent-sec">Update Rate Bands (30d)</div><div class="ent-row">'
    +'<div class="ent-band band-critical"><div class="ent-band-val">'+fmt(bands.critical)+'</div><div class="ent-band-lbl">Critical (&lt;25%)</div></div>'
    +'<div class="ent-band band-poor"><div class="ent-band-val">'+fmt(bands.poor)+'</div><div class="ent-band-lbl">Poor (25–50%)</div></div>'
    +'<div class="ent-band band-acceptable"><div class="ent-band-val">'+fmt(bands.acceptable)+'</div><div class="ent-band-lbl">Acceptable (50–75%)</div></div>'
    +'<div class="ent-band band-good"><div class="ent-band-val">'+fmt(bands.good)+'</div><div class="ent-band-lbl">Good (&gt;75%)</div></div>'
    +'</div>';

  var rows=(_perf&&_perf.rows)||[];
  var coHtml='<div class="ent-sec">CO Performance Table</div><div style="overflow-x:auto"><table class="ent-tbl"><thead><tr>'
    +'<th>CO</th><th>Total</th><th>Visited</th><th>Goal</th><th>Sat%</th><th>Cov%</th><th>In Progress</th><th>Docs Ready</th><th>SLA Overdue</th><th>Update Rate</th><th>Pending Review</th>'
    +'</tr></thead><tbody>';
  for(var j=0;j<rows.length;j++){
    var ro=rows[j];
    coHtml+='<tr><td>'+esc(ro.co_name||ro.co_id)+'</td>'
      +'<td>'+fmt(ro.total)+'</td>'
      +'<td>'+fmt(ro.visited)+'</td>'
      +'<td style="color:var(--g);font-weight:600">'+fmt(ro.goal)+'</td>'
      +'<td>'+pct(ro.saturation_pct)+'</td>'
      +'<td>'+pct(ro.coverage_pct)+'</td>'
      +'<td>'+fmt(ro.docs_in_progress)+'</td>'
      +'<td>'+fmt(ro.docs_ready)+'</td>'
      +'<td style="color:'+(ro.sla_overdue>0?'var(--r)':'inherit')+'">'+fmt(ro.sla_overdue)+'</td>'
      +'<td><span style="color:'+esc(ro.update_rate_color||'#111')+';font-weight:600">'+pct(ro.update_rate)+'</span> <span style="font-size:10px;color:var(--text-muted)">('+esc(ro.update_rate_band)+')</span></td>'
      +'<td style="color:'+(ro.pending_ac_review>0?'var(--o)':'inherit')+'">'+fmt(ro.pending_ac_review)+'</td>'
      +'</tr>';
  }
  coHtml+='</tbody></table></div>';

  var body=R.querySelector('#ent-body');
  if(body)body.innerHTML=cards+pipe+bandHtml+coHtml;
}

function buildPanel(){
  if(root_element.querySelector('.ent-overlay'))return;
  _ovl=document.createElement('div');_ovl.className='ent-overlay';
  _ovl.onclick=function(e){if(e.target===_ovl)entClose();};
  _pan=document.createElement('div');_pan.className='ent-panel';
  _pan.innerHTML='<div class="ent-ph"><button class="back" onclick="entBack()">← Back</button><div class="ttl" id="ent-ptitle">Loading…</div><button class="cls" onclick="entClose()">&times;</button></div><div class="ent-pb" id="ent-pbody"><div class="ent-loading"><span class="spinner-border spinner-border-sm"></span></div></div>';
  _ovl.appendChild(_pan);root_element.appendChild(_ovl);
}
function openPanel(){_ovl.classList.add('open');setTimeout(function(){_pan.classList.add('open');},10);}
window.entClose=function(){_pan.classList.remove('open');_ovl.classList.remove('open');_stk=[];};
window.entBack=function(){if(_stk.length<=1){entClose();return;}_stk.pop();renderPanel(_stk[_stk.length-1]);};

window.entDrillBucket=async function(bucket,title){
  if(!_data||!_data.bucket_counts)return;
  openPanel();
  root_element.querySelector('#ent-ptitle').textContent=title;
  root_element.querySelector('#ent-pbody').innerHTML='<div class="ent-loading"><span class="spinner-border spinner-border-sm"></span></div>';
  var result=await api('changemakers.generic_dashboard_api.get_programme_overview',{entitlement_code:_scheme});
  var frame={title:title,items:[]};
  _stk=[frame];
  root_element.querySelector('#ent-pbody').innerHTML='<div class="ent-empty">Drill into bucket: '+esc(bucket)+'<br><small>Use the beneficiary list in the CO app.</small></div>';
};

window.entDrillAlert=async function(type){
  openPanel();
  var title=type==='sla'?'SLA Overdue':'Pending AC Reviews';
  root_element.querySelector('#ent-ptitle').textContent=title;
  root_element.querySelector('#ent-pbody').innerHTML='<div class="ent-loading"><span class="spinner-border spinner-border-sm"></span></div>';
  if(type==='ac_review'){
    var result=await api('changemakers.generic_dashboard_api.get_ac_review_queue',{entitlement_code:_scheme,status_filter:'Pending AC Review'});
    var rows=result&&result.reviews||[];
    var html=rows.length?'<table class="ent-tbl"><thead><tr><th>Beneficiary</th><th>Container</th><th>CO</th><th>Visits</th><th>Escalated</th></tr></thead><tbody>'
      +rows.map(function(r){return '<tr><td>'+esc(r.beneficiary_name||r.beneficiary)+'</td><td>'+esc(r.container)+'</td><td>'+esc(r.co)+'</td><td>'+fmt(r.visit_count)+'</td><td>'+esc(r.escalation_date)+'</td></tr>';}).join('')
      +'</tbody></table>':'<div class="ent-empty">✓ No pending AC reviews.</div>';
    root_element.querySelector('#ent-pbody').innerHTML=html;
  } else {
    root_element.querySelector('#ent-pbody').innerHTML='<div class="ent-empty">SLA drill: open the CO performance screen in the app.</div>';
  }
};

function renderPanel(frame){
  root_element.querySelector('#ent-ptitle').textContent=frame.title;
  root_element.querySelector('#ent-pbody').innerHTML=frame.html||'<div class="ent-empty">No data.</div>';
}

init();
"""

# ─── AC Dashboard ─────────────────────────────────────────────────────────────

AC_HTML = '<div id="ent-root"><div class="ent-loading"><span class="spinner-border spinner-border-sm"></span> Loading…</div></div>'

AC_SCRIPT = r"""
var R=null,_scheme='';
function api(m,a){return new Promise(function(res,rej){frappe.call({method:m,args:a,callback:function(r){res(r.message);},error:function(e){rej(e);}});});}
function fmt(n){if(n==null)return '—';return Number(n).toLocaleString();}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

async function init(){
  R=root_element.querySelector('#ent-root');
  _scheme=localStorage.getItem('ent_scheme_'+frappe.session.user)||'';
  try{
    var schemes=await api('changemakers.generic_dashboard_api.get_dashboard_schemes',{});
    if(!schemes||!schemes.schemes||!schemes.schemes.length){R.innerHTML='<div class="ent-loading">No active schemes found.</div>';return;}
    if(!_scheme||!schemes.schemes.find(function(s){return s.entitlement_code===_scheme;}))
      _scheme=schemes.schemes[0].entitlement_code;
    renderScope(schemes.schemes);
    await loadData();
  }catch(e){R.innerHTML='<div class="ent-loading" style="color:red">Error: '+esc(e&&e.message||String(e))+'</div>';}
}

function renderScope(schemes){
  var opts=schemes.map(function(s){return '<option value="'+esc(s.entitlement_code)+'"'+(s.entitlement_code===_scheme?' selected':'')+'>'+esc(s.entitlement_name)+'</option>';}).join('');
  R.innerHTML='<div class="ent-scope"><label>Scheme:</label><select id="ent-sel">'+opts+'</select><button onclick="acRefresh()">Refresh</button></div>'
    +'<div id="ent-body"><div class="ent-loading"><span class="spinner-border spinner-border-sm"></span> Loading…</div></div>';
  var sel=R.querySelector('#ent-sel');
  if(sel)sel.onchange=function(){_scheme=sel.value;localStorage.setItem('ent_scheme_'+frappe.session.user,_scheme);acRefresh();};
}

async function loadData(){
  var body=R.querySelector('#ent-body');
  if(body)body.innerHTML='<div class="ent-loading"><span class="spinner-border spinner-border-sm"></span></div>';
  var result=await api('changemakers.generic_dashboard_api.get_ac_review_queue',{entitlement_code:_scheme,status_filter:''});
  renderReviews(result&&result.reviews||[]);
}

window.acRefresh=function(){var sel=R&&R.querySelector('#ent-sel');if(sel)_scheme=sel.value;localStorage.setItem('ent_scheme_'+frappe.session.user,_scheme);loadData();};

function renderReviews(reviews){
  var pending=reviews.filter(function(r){return r.status==='Pending AC Review';});
  var resolved=reviews.filter(function(r){return r.status!=='Pending AC Review';});
  var html='<div class="ent-sec">Pending AC Review ('+fmt(pending.length)+')</div>';
  if(!pending.length){
    html+='<div class="ent-empty">✓ No pending reviews. All clear.</div>';
  } else {
    html+='<div style="overflow-x:auto"><table class="ent-tbl"><thead><tr>'
      +'<th>Beneficiary</th><th>Container / Street</th><th>CO</th><th>Visits</th><th>Escalated</th><th>Action</th>'
      +'</tr></thead><tbody>';
    for(var i=0;i<pending.length;i++){
      var r=pending[i];
      html+='<tr>'
        +'<td>'+esc(r.beneficiary_name||r.beneficiary)+'</td>'
        +'<td>'+esc(r.container)+'</td>'
        +'<td>'+esc(r.co)+'</td>'
        +'<td>'+fmt(r.visit_count)+'</td>'
        +'<td>'+esc(r.escalation_date)+'</td>'
        +'<td style="white-space:nowrap">'
        +'<button style="font-size:11px;padding:3px 8px;margin-right:4px;background:#dcfce7;border:1px solid #86efac;color:#166534;border-radius:4px;cursor:pointer" onclick="acResolve(\''+esc(r.name)+'\',\'Cleared – Will Apply\')">Clear</button>'
        +'<button style="font-size:11px;padding:3px 8px;background:#fee2e2;border:1px solid #fca5a5;color:#991b1b;border-radius:4px;cursor:pointer" onclick="acResolve(\''+esc(r.name)+'\',\'Blocked – No Resolution\')">Block</button>'
        +'</td></tr>';
    }
    html+='</tbody></table></div>';
  }

  if(resolved.length){
    html+='<div class="ent-sec" style="margin-top:24px">Resolved ('+fmt(resolved.length)+')</div>'
      +'<div style="overflow-x:auto"><table class="ent-tbl"><thead><tr>'
      +'<th>Beneficiary</th><th>Container</th><th>Status</th><th>Resolved</th>'
      +'</tr></thead><tbody>';
    for(var j=0;j<Math.min(resolved.length,50);j++){
      var rv=resolved[j];
      var statusColor=rv.status==='Cleared – Will Apply'?'#16a34a':'#dc2626';
      html+='<tr><td>'+esc(rv.beneficiary_name||rv.beneficiary)+'</td>'
        +'<td>'+esc(rv.container)+'</td>'
        +'<td style="color:'+statusColor+';font-weight:600">'+esc(rv.status)+'</td>'
        +'<td>'+esc(rv.resolved_date||'')+'</td></tr>';
    }
    html+='</tbody></table></div>';
  }

  var body=R.querySelector('#ent-body');
  if(body)body.innerHTML=html;
}

window.acResolve=async function(reviewId,status){
  var notes=prompt('Notes (optional):','')||'';
  try{
    await api('changemakers.generic_dashboard_api.update_ac_review',{review_id:reviewId,status:status,ac_notes:notes});
    frappe.show_alert({message:'Review updated: '+status,indicator:'green'},3);
    await loadData();
  }catch(e){frappe.show_alert({message:'Error: '+(e&&e.message||String(e)),indicator:'red'},5);}
};

init();
"""

# ─── MIS Dashboard ────────────────────────────────────────────────────────────

MIS_HTML = '<div id="ent-root"><div class="ent-loading"><span class="spinner-border spinner-border-sm"></span> Loading…</div></div>'

MIS_SCRIPT = r"""
var R=null,_scheme='',_data=null,_sankey=null,_rates=null;
var BUCKET_COLORS={unvisited:'#6b7280',docs_in_progress:'#f59e0b',docs_ready:'#8b5cf6',applied_pending:'#3b82f6',goal:'#22c55e',negative:'#ef4444'};
var BUCKET_LABELS={unvisited:'Unvisited',docs_in_progress:'Docs In Progress',docs_ready:'Docs Ready',applied_pending:'Applied – Pending',goal:'Goal Achieved',negative:'Closed – Negative'};

function api(m,a){return new Promise(function(res,rej){frappe.call({method:m,args:a,callback:function(r){res(r.message);},error:function(e){rej(e);}});});}
function fmt(n){if(n==null)return '—';return Number(n).toLocaleString();}
function pct(n){return n==null?'':Number(n).toFixed(1)+'%';}
function esc(s){return String(s||'').replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}

async function init(){
  R=root_element.querySelector('#ent-root');
  _scheme=localStorage.getItem('ent_scheme_'+frappe.session.user)||'';
  try{
    var schemes=await api('changemakers.generic_dashboard_api.get_dashboard_schemes',{});
    if(!schemes||!schemes.schemes||!schemes.schemes.length){R.innerHTML='<div class="ent-loading">No active schemes found.</div>';return;}
    if(!_scheme||!schemes.schemes.find(function(s){return s.entitlement_code===_scheme;}))
      _scheme=schemes.schemes[0].entitlement_code;
    renderScope(schemes.schemes);
    await loadData();
  }catch(e){R.innerHTML='<div class="ent-loading" style="color:red">Error: '+esc(e&&e.message||String(e))+'</div>';}
}

function renderScope(schemes){
  var opts=schemes.map(function(s){return '<option value="'+esc(s.entitlement_code)+'"'+(s.entitlement_code===_scheme?' selected':'')+'>'+esc(s.entitlement_name)+'</option>';}).join('');
  R.innerHTML='<div class="ent-scope"><label>Scheme:</label><select id="ent-sel">'+opts+'</select><button onclick="misRefresh()">Refresh</button></div>'
    +'<div id="ent-body"><div class="ent-loading"><span class="spinner-border spinner-border-sm"></span></div></div>';
  var sel=R.querySelector('#ent-sel');
  if(sel)sel.onchange=function(){_scheme=sel.value;localStorage.setItem('ent_scheme_'+frappe.session.user,_scheme);misRefresh();};
}

async function loadData(){
  var body=R.querySelector('#ent-body');
  if(body)body.innerHTML='<div class="ent-loading"><span class="spinner-border spinner-border-sm"></span></div>';
  var results=await Promise.all([
    api('changemakers.generic_dashboard_api.get_programme_overview',{entitlement_code:_scheme}),
    api('changemakers.generic_dashboard_api.get_sankey_data',{entitlement_code:_scheme,days:30}),
    api('changemakers.generic_dashboard_api.get_update_rate_by_co',{entitlement_code:_scheme,days:30}),
  ]);
  _data=results[0];_sankey=results[1];_rates=results[2];
  renderDashboard();
}

window.misRefresh=function(){var sel=R&&R.querySelector('#ent-sel');if(sel)_scheme=sel.value;localStorage.setItem('ent_scheme_'+frappe.session.user,_scheme);loadData();};

function renderDashboard(){
  if(!_data)return;
  var total=_data.total||1;

  // Overview cards
  var cards='<div class="ent-sec">Programme Overview — '+esc(_data.entitlement_name)+'</div><div class="ent-row">'
    +'<div class="ent-card"><div class="ent-val">'+fmt(_data.total)+'</div><div class="ent-lbl">Total</div></div>'
    +'<div class="ent-card"><div class="ent-val" style="color:#3b82f6">'+pct(_data.coverage_pct)+'</div><div class="ent-lbl">Coverage</div></div>'
    +'<div class="ent-card"><div class="ent-val" style="color:#22c55e">'+pct(_data.saturation_pct)+'</div><div class="ent-lbl">'+esc(_data.final_status_label||'Goal')+'</div></div>'
    +'<div class="ent-card"><div class="ent-val" style="color:#ef4444">'+fmt(_data.sla_overdue_count)+'</div><div class="ent-lbl">SLA Overdue</div></div>'
    +'<div class="ent-card"><div class="ent-val" style="color:#f97316">'+fmt(_data.pending_ac_reviews)+'</div><div class="ent-lbl">Pending AC Reviews</div></div>'
    +'</div>';

  // Bucket pipeline
  var bk=_data.bucket_counts||{};
  var bucketOrder=['unvisited','docs_in_progress','docs_ready','applied_pending','goal','negative'];
  var pipe='<div class="ent-sec">Pipeline Breakdown</div><div style="padding:8px 12px;background:var(--card-bg,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:8px">';
  for(var i=0;i<bucketOrder.length;i++){
    var b=bucketOrder[i],cnt=bk[b]||0,pp=(cnt/total*100).toFixed(1),col=BUCKET_COLORS[b]||'#6b7280',lbl=BUCKET_LABELS[b]||b;
    pipe+='<div class="ent-pipe-row"><div class="ent-pipe-lbl">'+lbl+'</div>'
      +'<div class="ent-pipe-bar"><div class="ent-pipe-fill" style="width:'+pp+'%;background:'+col+'"></div></div>'
      +'<div class="ent-pipe-cnt" style="color:'+col+'">'+fmt(cnt)+'</div>'
      +'<div class="ent-pipe-pct">'+pp+'%</div></div>';
  }
  pipe+='</div>';

  // Transitions table
  var trans=_sankey&&_sankey.bucket_transitions||[];
  var transHtml='<div class="ent-sec">Bucket Transitions (last 30 days)</div>';
  if(!trans.length){
    transHtml+='<div class="ent-empty">No transitions recorded yet.</div>';
  } else {
    transHtml+='<div style="overflow-x:auto"><table class="ent-tbl"><thead><tr><th>From</th><th>To</th><th>Count</th></tr></thead><tbody>';
    for(var j=0;j<trans.length;j++){
      var t=trans[j];
      transHtml+='<tr><td>'+esc(t.from)+'</td><td>'+esc(t.to)+'</td><td>'+fmt(t.count)+'</td></tr>';
    }
    transHtml+='</tbody></table></div>';
  }

  // Doc slot transitions
  var slotTrans=_sankey&&_sankey.slot_transitions||[];
  var slotHtml='<div class="ent-sec">Document Status Changes (last 30 days, top 20)</div>';
  if(!slotTrans.length){
    slotHtml+='<div class="ent-empty">No changes recorded yet.</div>';
  } else {
    slotHtml+='<div style="overflow-x:auto"><table class="ent-tbl"><thead><tr><th>Document</th><th>From</th><th>To</th><th>Count</th></tr></thead><tbody>';
    for(var k=0;k<Math.min(slotTrans.length,20);k++){
      var st=slotTrans[k];
      slotHtml+='<tr><td>'+esc(st.doc_label)+'</td><td>'+esc(st.old_label)+'</td><td>'+esc(st.new_label)+'</td><td>'+fmt(st.cnt)+'</td></tr>';
    }
    slotHtml+='</tbody></table></div>';
  }

  // Update rate bar chart (using CSS bars)
  var rateRows=_rates&&_rates.rows||[];
  var rateHtml='<div class="ent-sec">CO Update Rate (last 30 days)</div>';
  if(!rateRows.length){
    rateHtml+='<div class="ent-empty">No data.</div>';
  } else {
    rateHtml+='<div style="padding:8px 12px;background:var(--card-bg,#fff);border:1px solid var(--border-color,#e5e7eb);border-radius:8px">';
    for(var m=0;m<rateRows.length;m++){
      var rr=rateRows[m];
      rateHtml+='<div class="ent-pipe-row"><div class="ent-pipe-lbl">'+esc(rr.co_name||rr.co_id)+'</div>'
        +'<div class="ent-pipe-bar"><div class="ent-pipe-fill" style="width:'+rr.rate+'%;background:'+esc(rr.color)+'"></div></div>'
        +'<div class="ent-pipe-cnt" style="color:'+esc(rr.color)+'">'+pct(rr.rate)+'</div>'
        +'<div class="ent-pipe-pct" style="color:'+esc(rr.color)+';font-weight:600">'+esc(rr.band)+'</div></div>';
    }
    rateHtml+='</div>';
  }

  var body=R.querySelector('#ent-body');
  if(body)body.innerHTML=cards+pipe+transHtml+slotHtml+rateHtml;
}

init();
"""


def _upsert_html_block(name, html, script, style, roles):
    if frappe.db.exists("Custom HTML Block", name):
        doc = frappe.get_doc("Custom HTML Block", name)
    else:
        doc = frappe.new_doc("Custom HTML Block")
        doc.name = name

    doc.html = html
    doc.script = script
    doc.style = style

    doc.set("roles", [])
    for role in roles:
        doc.append("roles", {"role": role})

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)


def _upsert_workspace(name, title, roles, html_block_name, module="Frappe Changemakers"):
    """Create or update a workspace with a single HTML block content item."""
    content = json.dumps([
        {
            "id": f"{name.lower().replace(' ', '_')}_block",
            "type": "custom-block",
            "data": {"custom_block_name": html_block_name, "col": 12},
        }
    ])

    if frappe.db.exists("Workspace", name):
        doc = frappe.get_doc("Workspace", name)
        doc.title = title
        doc.label = title
    else:
        doc = frappe.new_doc("Workspace")
        doc.name = name
        doc.title = title
        doc.label = title
        doc.module = module
        doc.is_standard = 0
        doc.public = 1
        doc.content = content

    # Update roles
    doc.set("roles", [])
    for role in roles:
        doc.append("roles", {"role": role})

    if doc.is_new():
        doc.insert(ignore_permissions=True)
    else:
        doc.save(ignore_permissions=True)


def execute():
    if not frappe.db.exists("DocType", "Custom HTML Block"):
        return

    style = COMMON_CSS

    _upsert_html_block(
        "Entitlement Programme Dashboard",
        PROG_HTML, PROG_SCRIPT, style,
        roles=["System Manager", "WRP-PM", "WRP-MIS", "WRP-HR"],
    )

    _upsert_html_block(
        "Entitlement AC Dashboard",
        AC_HTML, AC_SCRIPT, style,
        roles=["System Manager", "WRP-AC", "WRP-PM"],
    )

    _upsert_html_block(
        "Entitlement MIS Dashboard",
        MIS_HTML, MIS_SCRIPT, style,
        roles=["System Manager", "WRP-MIS", "WRP-PM"],
    )

    if frappe.db.exists("DocType", "Workspace"):
        _upsert_workspace(
            "OAP Programme",
            "OAP Programme Dashboard",
            roles=["WRP-PM", "WRP-HR", "WRP-MIS", "System Manager"],
            html_block_name="Entitlement Programme Dashboard",
        )
        _upsert_workspace(
            "OAP AC Review",
            "OAP AC Review Dashboard",
            roles=["WRP-AC", "WRP-PM", "System Manager"],
            html_block_name="Entitlement AC Dashboard",
        )
        _upsert_workspace(
            "OAP MIS",
            "OAP MIS Dashboard",
            roles=["WRP-MIS", "WRP-PM", "System Manager"],
            html_block_name="Entitlement MIS Dashboard",
        )

    frappe.db.commit()
    frappe.logger().info("Setup entitlement dashboards and workspaces")
