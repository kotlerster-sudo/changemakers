// "Your Cockpit is arriving" banner + sidebar countdown (Mathew, 28-Sep-2026).
// Shown to COs, ACs, PMs and MIS coordinators until the Cockpit opens on Wed 30-Sep 09:30 IST.
// Banner: on the 1st, 4th, 7th … fresh visit (a "login"), or when 2 hours or more have passed since it last showed.
// Sidebar row: always, above the sidebar items; tap it to open the banner again.
// After the opening the sidebar row says "open now" for 12 hours, then this file does nothing.
// Preview for anyone: add ?ck_arriving=co (or ac / pm / mis) to any /app URL.
// Revert: remove the cockpit_arriving.js line from app_include_js in hooks.py and redeploy.
(function () {
	const LAUNCH = Date.parse("2026-09-30T09:30:00+05:30");
	const START = Date.parse("2026-09-28T09:00:00+05:30"); // the loader's 0%
	const STOP = LAUNCH + 12 * 36e5;
	const SPAN = LAUNCH - START;
	const COCKPIT_URL = "/app/my-cockpit";

	const SCOPE = {
		field: {
			en: ["Your work comes to you as cards. One card is one job for one person or one house.",
				"Plan your day in My Day. Update papers and schemes from the card, on your phone.",
				"Could not finish? Record why (door locked, come later). It still counts as your effort."],
			ta: ["உங்கள் வேலை கார்டுகளாக வரும். ஒரு கார்டு = ஒரு நபர் அல்லது ஒரு வீட்டுக்கான ஒரு வேலை.",
				"My Day-இல் உங்கள் நாளைத் திட்டமிடுங்கள். ஆவணங்கள், திட்டங்களை கார்டிலிருந்தே உங்கள் போனில் பதிவு செய்யுங்கள்.",
				"முடிக்க முடியவில்லையா? காரணத்தைப் பதிவு செய்யுங்கள் (கதவு பூட்டியிருந்தது, பிறகு வரச் சொன்னார்கள்). அதுவும் உங்கள் முயற்சியாகக் கணக்கில் வரும்."],
		},
		ac: {
			en: ["Phase 1 is for you and your COs. Your cards come as one job each: referrals and checks.",
				"See your team's cards, visits and what is waiting, street by street.",
				"Help your COs plan their day. Record why a card could not be finished."],
			ta: ["முதல் கட்டம் உங்களுக்கும் உங்கள் CO-க்களுக்கும். உங்கள் கார்டுகள் ஒவ்வொன்றும் ஒரு வேலை: பரிந்துரைகள், சரிபார்ப்புகள்.",
				"உங்கள் குழுவின் கார்டுகள், வருகைகள், காத்திருப்பவை: தெரு வாரியாகப் பாருங்கள்.",
				"உங்கள் CO-க்கள் நாளைத் திட்டமிட உதவுங்கள். கார்டு முடியாவிட்டால் காரணத்தைப் பதிவு செய்யுங்கள்."],
		},
		lead: {
			en: ["Phase 1 opens for COs and ACs only. You can see their cards, visits and the dashboard.",
				"Help your team in the first days. Send problems through Report an Issue.",
				"Watch the dashboard: cards done, attempts and locked doors, by partner."],
			ta: ["முதல் கட்டம் CO, AC-க்களுக்கு மட்டும். அவர்களின் கார்டுகள், வருகைகள், டாஷ்போர்டு உங்களுக்குத் தெரியும்.",
				"முதல் நாட்களில் உங்கள் குழுவுக்கு உதவுங்கள். பிரச்சனைகளை Report an Issue வழியாக அனுப்புங்கள்.",
				"டாஷ்போர்டைப் பாருங்கள்: முடிந்த கார்டுகள், முயற்சிகள், பூட்டிய கதவுகள், பார்ட்னர் வாரியாக."],
		},
	};

	function ls(k, v) {
		try {
			if (v === undefined) return localStorage.getItem(k);
			localStorage.setItem(k, v);
		} catch (e) { return null; }
	}
	function ss(k, v) {
		try {
			if (v === undefined) return sessionStorage.getItem(k);
			sessionStorage.setItem(k, v);
		} catch (e) { return null; }
	}

	// which scope lines this user sees; null = not for this user
	function audience() {
		const m = /[?&]ck_arriving=(co|ac|pm|mis)/.exec(location.search);
		if (m) return { co: "field", ac: "ac", pm: "lead", mis: "lead" }[m[1]];
		const r = frappe.user_roles || [];
		if (r.indexOf("WRP - CO") > -1) return "field";
		if (r.indexOf("WRP-AC") > -1) return "ac";
		if (r.indexOf("WRP-PM") > -1 || r.indexOf("WRP-MIS") > -1) return "lead";
		return null;
	}

	const CSS = `
.ckarr-ov{position:fixed;inset:0;z-index:1100;background:rgba(40,40,40,.45);display:flex;align-items:flex-start;justify-content:center;padding:24px 16px;overflow:auto;font-family:Arial,"Helvetica Neue",Helvetica,sans-serif;color:#262626;font-size:15px;line-height:1.5}
.ckarr-ov *{box-sizing:border-box}
.ckarr-ta{font-family:"Hind Madurai","Noto Sans Tamil",Arial,sans-serif}
.ckarr-b{background:#fff;border-radius:10px;box-shadow:0 18px 44px rgba(0,0,0,.25);width:100%;max-width:900px;overflow:hidden;animation:ckarr-pop .45s cubic-bezier(.2,.9,.3,1.2)}
@keyframes ckarr-pop{from{transform:translateY(14px) scale(.97);opacity:.4}to{transform:none;opacity:1}}
.ckarr-head{padding:20px 26px 12px;display:grid;grid-template-columns:1fr 1fr;gap:4px 28px}
.ckarr-rule{height:7px;margin:0 26px;border-top:4px solid #E36C09;border-bottom:1px solid #E36C09}
.ckarr-eb{font-size:12px;letter-spacing:.1em;text-transform:uppercase;color:#E36C09;font-weight:700}
.ckarr-head h1{font-size:28px;line-height:1.15;font-weight:700;margin:0;color:#262626}
.ckarr-head .ckarr-ta h1{font-size:24px}
.ckarr-head p{margin:2px 0 0;color:#5F5F5F}
.ckarr-cd{display:flex;justify-content:center;gap:10px;padding:16px 16px 4px;flex-wrap:wrap}
.ckarr-cell{min-width:80px;text-align:center;background:#fff;border:1.5px solid #F7C9A0;border-radius:8px;padding:8px 6px 6px}
.ckarr-n{font-weight:700;font-size:36px;line-height:1;font-variant-numeric:tabular-nums}
.ckarr-u{font-size:12px;color:#5F5F5F;line-height:1.3;margin-top:4px}
.ckarr-cell.sec{background:#E36C09;border-color:#E36C09}.ckarr-cell.sec .ckarr-n,.ckarr-cell.sec .ckarr-u{color:#fff}
.ckarr-rw{padding:4px 26px 12px}
.ckarr-lbl{display:flex;justify-content:space-between;gap:10px;font-size:13px;color:#5F5F5F;margin-bottom:2px;flex-wrap:wrap}
.ckarr-lbl b{color:#E36C09;font-variant-numeric:tabular-nums}
.ckarr-sc{position:relative;height:112px}
.ckarr-floor{position:absolute;left:0;right:0;bottom:16px;height:3px;border-radius:2px;background:#E3E3E3}
.ckarr-ticks{position:absolute;left:0;right:0;bottom:0;height:16px}
.ckarr-tick{position:absolute;bottom:0;transform:translateX(-50%);font-size:11px;color:#5F5F5F}
.ckarr-flag{position:absolute;right:0;bottom:19px;width:34px;height:56px}
.ckarr-pile{position:absolute;left:calc(86% - 10px);bottom:19px;width:22px;height:22px}
.ckarr-pile i{position:absolute;left:0;width:20px;height:13px;border-radius:2px;border:1px solid #B8860B;background:linear-gradient(135deg,#FBE7A1,#E9B949 55%,#B8860B)}
.ckarr-box{position:absolute;bottom:19px;width:34px;height:44px;transform:translateX(-50%)}
.ckarr-tray{position:absolute;left:0;right:0;bottom:0;height:20px;border:2.5px solid #BDBDBD;border-top:0;border-radius:0 0 6px 6px;background:#FAFAFA;z-index:2}
.ckarr-box.full .ckarr-tray{border-color:#3C8D3F;background:#EAF5EA}
.ckarr-box.now .ckarr-tray{border-color:#E36C09;background:#FFF3E8}
.ckarr-box.full::after{content:"✓";position:absolute;left:50%;bottom:-17px;transform:translateX(-50%);font-size:11px;color:#3C8D3F;font-weight:700;z-index:3}
.ckarr-card{position:absolute;left:5px;width:22px;height:14px;border-radius:3px;z-index:1;overflow:hidden;border:1px solid rgba(0,0,0,.18)}
.ckarr-card::before{content:"";position:absolute;left:3px;right:7px;top:3px;height:2px;border-radius:1px;background:rgba(255,255,255,.85)}
.ckarr-gold{background:linear-gradient(135deg,#FBE7A1,#E9B949 55%,#B8860B)}
.ckarr-orange{background:linear-gradient(135deg,#F9B57A,#E36C09)}
.ckarr-green{background:linear-gradient(135deg,#9FD4A1,#3C8D3F)}
.ckarr-rose{background:linear-gradient(135deg,#F4B6C2,#C2185B)}
.ckarr-blue{background:linear-gradient(135deg,#A9CCEB,#1F6FB2)}
.ckarr-card.ckarr-gold::after,.ckarr-fly::after{content:"";position:absolute;top:-4px;bottom:-4px;width:6px;left:-10px;background:rgba(255,255,255,.9);transform:skewX(-20deg);animation:ckarr-shine 2.6s ease-in-out infinite}
@keyframes ckarr-shine{0%,70%{left:-10px}100%{left:30px}}
.ckarr-card.new{animation:ckarr-settle .45s ease-out}
@keyframes ckarr-settle{from{transform:translateY(-10px)}}
.ckarr-p{position:absolute;bottom:19px;width:30px;height:50px;z-index:3}
.ckarr-p svg{width:30px;height:50px;display:block;overflow:visible}
.ckarr-walk .lg1{transform-origin:15px 34px;animation:ckarr-step .45s ease-in-out infinite alternate}
.ckarr-walk .lg2{transform-origin:15px 34px;animation:ckarr-step .45s ease-in-out infinite alternate-reverse}
@keyframes ckarr-step{from{transform:rotate(14deg)}to{transform:rotate(-14deg)}}
.ckarr-tosser{transform:translateX(-100%);transition:left .8s ease-in-out}
.ckarr-tosser .arm{transform-origin:16px 22px;animation:ckarr-toss 1.6s ease-in-out infinite}
@keyframes ckarr-toss{0%,55%{transform:rotate(0)}70%{transform:rotate(-38deg)}100%{transform:rotate(0)}}
.ckarr-tosser .held{animation:ckarr-held 1.6s linear infinite}
@keyframes ckarr-held{0%,62%{opacity:1}63%,100%{opacity:0}}
.ckarr-fly{position:absolute;width:16px;height:11px;border-radius:2px;z-index:4;animation:ckarr-flyk 1.6s ease-in infinite;opacity:0;overflow:hidden;background:linear-gradient(135deg,#FBE7A1,#E9B949 55%,#B8860B)}
@keyframes ckarr-flyk{0%,62%{opacity:0;transform:translate(0,0) rotate(0)}63%{opacity:1;transform:translate(0,0) rotate(0)}82%{opacity:1;transform:translate(14px,-16px) rotate(120deg)}100%{opacity:0;transform:translate(26px,8px) rotate(200deg)}}
.ckarr-spark{position:absolute;width:10px;height:10px;z-index:5;pointer-events:none;opacity:0;animation:ckarr-sparkk 1.6s ease-out infinite}
.ckarr-spark::before{content:"";position:absolute;inset:0;background:#E9B949;clip-path:polygon(50% 0,62% 38%,100% 50%,62% 62%,50% 100%,38% 62%,0 50%,38% 38%)}
@keyframes ckarr-sparkk{0%,86%{opacity:0;transform:scale(.2) rotate(0)}92%{opacity:1;transform:scale(1.1) rotate(30deg)}100%{opacity:0;transform:scale(.4) rotate(60deg)}}
.ckarr-lane{position:absolute;bottom:0;top:0;pointer-events:none}
.ckarr-lane .ckarr-p{animation:ckarr-pace var(--dur,4s) linear infinite}
@keyframes ckarr-pace{0%{left:0;transform:scaleX(1)}46%{left:calc(100% - 30px);transform:scaleX(1)}54%{left:calc(100% - 30px);transform:scaleX(-1)}100%{left:0;transform:scaleX(-1)}}
.ckarr-lane .held{animation:ckarr-carry var(--dur,4s) linear infinite}
@keyframes ckarr-carry{0%,53%{opacity:0}54%,100%{opacity:1}}
.ckarr-lift{position:absolute;width:16px;height:11px;border-radius:2px;z-index:1;overflow:hidden;animation:ckarr-liftk var(--dur,4s) ease-out infinite;border:1px solid rgba(0,0,0,.18)}
@keyframes ckarr-liftk{0%,50%{opacity:0;transform:translateY(0)}56%{opacity:1;transform:translateY(0)}64%{opacity:1;transform:translateY(-14px)}68%,100%{opacity:0;transform:translateY(-16px)}}
.ckarr-checker .arm{transform-origin:16px 22px;animation:ckarr-tickarm 1.2s ease-in-out infinite alternate}
@keyframes ckarr-tickarm{to{transform:rotate(-12deg)}}
.ckarr-steps{display:flex;gap:6px 16px;flex-wrap:wrap;margin-top:6px;font-size:12.5px;color:#5F5F5F}
.ckarr-steps span::before{content:"✓ ";color:#3C8D3F;font-weight:700}
.ckarr-bi{display:grid;grid-template-columns:1fr 1fr}
.ckarr-col{padding:14px 26px 6px}
.ckarr-col + .ckarr-col{border-left:1px solid #E3E3E3}
.ckarr-lang{font-size:11px;letter-spacing:.1em;text-transform:uppercase;color:#5F5F5F;margin-bottom:6px}
.ckarr-col h3{font-size:17px;margin:4px 0 6px;color:#262626;font-weight:700}
.ckarr-col ol{margin:0 0 12px;padding-left:20px;display:grid;gap:6px}
.ckarr-col ol li::marker{color:#E36C09;font-weight:700}
.ckarr-col p{margin:0 0 10px}
.ckarr-note{border-left:4px solid #E36C09;background:#FFF3E8;padding:10px 12px;margin-bottom:10px}
.ckarr-warn{border-left:4px solid #BDBDBD;background:#F7F7F7;padding:10px 12px;margin-bottom:12px}
.ckarr-thanks{font-weight:700;font-size:18px;color:#E36C09}
.ckarr-phase{display:inline-block;background:#E36C09;color:#fff;border-radius:4px;font-size:11.5px;padding:1px 7px;margin-left:6px;vertical-align:2px;letter-spacing:.04em}
.ckarr-foot{display:flex;justify-content:flex-end;padding:14px 26px 20px;border-top:1px solid #E3E3E3}
.ckarr-exit{background:#E36C09;color:#fff;border:0;border-radius:6px;padding:10px 22px;font-weight:700;font-size:15px;cursor:pointer}
.ckarr-exit:hover{background:#B85607}
.ckarr-exit:focus-visible,.ckarr-side:focus-visible{outline:3px solid #E36C09;outline-offset:2px}
.ckarr-side{display:flex;align-items:center;gap:10px;padding:7px 10px;margin:4px 8px 6px;border-radius:8px;background:#FFF3E8;border:1px solid #F7C9A0;color:#262626;text-align:left;cursor:pointer;font-family:Arial,sans-serif;width:calc(100% - 16px)}
.ckarr-side:hover{border-color:#E36C09}
.ckarr-ring{width:28px;height:28px;flex:none}
.ckarr-ring circle{fill:none;stroke-width:4}
.ckarr-side small{display:block;font-size:11.5px;color:#5F5F5F;line-height:1.2}
.ckarr-side strong{font-size:13px;font-variant-numeric:tabular-nums;line-height:1.3;color:#262626}
.ckarr-side.mini{width:34px;padding:2px;margin:4px auto 6px;justify-content:center;background:transparent;border-color:transparent}
.ckarr-side.mini .ckarr-stxt{display:none}
@media (max-width:760px){
  .ckarr-head,.ckarr-bi{grid-template-columns:1fr}
  .ckarr-col + .ckarr-col{border-left:0;border-top:1px solid #E3E3E3}
  .ckarr-cell{min-width:64px}.ckarr-n{font-size:28px}
  .ckarr-head,.ckarr-col,.ckarr-rw,.ckarr-foot{padding-left:16px;padding-right:16px}
  .ckarr-rule{margin:0 16px}
  .ckarr-ov{padding:12px 8px}
  .ckarr-box{width:26px}.ckarr-card{left:2px;width:20px}
}
@media (prefers-reduced-motion:reduce){.ckarr-ov *,.ckarr-side *{animation:none!important;transition:none!important}}
`;

	function pad(n) { return String(n).padStart(2, "0"); }
	function left() { return Math.max(0, LAUNCH - Date.now()); }
	function progress() { return Math.min(1, Math.max(0, (Date.now() - START) / SPAN)); }

	// ---------- banner ----------
	let ov = null, draw = null;

	function figure(g, skin, cloth, hair, held, walk, extra) {
		const legc = g === "w" ? skin : "#3A3A3A";
		const legs = '<g class="lg1"><rect x="12" y="33" width="3" height="13" rx="1.5" fill="' + legc + '"/></g>' +
			'<g class="lg2"><rect x="15" y="33" width="3" height="13" rx="1.5" fill="' + legc + '"/></g>';
		const body = g === "w"
			? '<path d="M10 19 H20 L23 38 H7 Z" fill="' + cloth + '"/><path d="M11 19 L21 31" stroke="#fff" stroke-opacity=".55" stroke-width="2.2"/>'
			: '<rect x="9.5" y="19" width="11" height="15" rx="4" fill="' + cloth + '"/>';
		const hr = g === "w"
			? '<path d="M9 12 Q9 4 15 4.5 Q21 4 21 12 Q19 8 15 8 Q11 8 9 12 Z" fill="' + hair + '"/><circle cx="10" cy="9" r="3" fill="' + hair + '"/>'
			: '<path d="M9.2 11 Q9.5 5 15 5 Q20.5 5 20.8 11 Q18 8 15 8.3 Q12 8 9.2 11 Z" fill="' + hair + '"/>';
		const arm = '<g class="arm"><rect x="17" y="21" width="10" height="3" rx="1.5" fill="' + skin + '"/>' +
			(held ? '<rect class="held" x="21" y="14.5" width="9" height="6.5" rx="1" fill="#E9B949" stroke="#B8860B" stroke-width=".8"/>' : "") + (extra || "") + "</g>";
		return '<svg viewBox="0 0 30 50"><g' + (walk ? ' class="ckarr-walk"' : "") + ">" + legs + "</g>" + body +
			'<circle cx="15" cy="12" r="6" fill="' + skin + '"/>' + hr + '<circle cx="17.6" cy="12" r=".9" fill="#222"/>' + arm + "</svg>";
	}

	function build(kind) {
		const s = SCOPE[kind];
		const li = (a) => a.map((t) => "<li>" + t + "</li>").join("");
		ov = document.createElement("div");
		ov.className = "ckarr-ov";
		ov.innerHTML = `
<section class="ckarr-b" role="dialog" aria-modal="true" aria-labelledby="ckarr-t">
 <header class="ckarr-head">
  <div><div class="ckarr-eb">Phase 1 · Chennai WRP</div><h1 id="ckarr-t">Your Cockpit is arriving</h1><p>Opens <b>Wednesday 30 September, 9:30 am</b></p></div>
  <div class="ckarr-ta" lang="ta"><div class="ckarr-eb">முதல் கட்டம்</div><h1>உங்கள் காக்பிட் வருகிறது</h1><p><b>புதன், 30 செப்டம்பர், காலை 9:30</b> மணிக்குத் திறக்கிறது</p></div>
 </header>
 <div class="ckarr-rule"></div>
 <div class="ckarr-cd">
  <div class="ckarr-cell"><div class="ckarr-n" data-k="d">0</div><div class="ckarr-u">days · <span class="ckarr-ta">நாள்</span></div></div>
  <div class="ckarr-cell"><div class="ckarr-n" data-k="h">00</div><div class="ckarr-u">hours · <span class="ckarr-ta">மணி</span></div></div>
  <div class="ckarr-cell"><div class="ckarr-n" data-k="m">00</div><div class="ckarr-u">minutes · <span class="ckarr-ta">நிமிடம்</span></div></div>
  <div class="ckarr-cell sec"><div class="ckarr-n" data-k="s">00</div><div class="ckarr-u">seconds · <span class="ckarr-ta">விநாடி</span></div></div>
 </div>
 <div class="ckarr-rw">
  <div class="ckarr-lbl"><span>Getting ready · <span class="ckarr-ta">தயாராகிறது</span> <b data-k="pct">0%</b></span><span>Filling the boxes, one card at a time</span></div>
  <div class="ckarr-sc" aria-hidden="true">
   <div class="ckarr-floor"></div><div data-k="boxes"></div>
   <div class="ckarr-pile"><i style="bottom:0;transform:rotate(-4deg)"></i><i style="bottom:4px;transform:rotate(3deg)"></i><i style="bottom:8px;transform:rotate(-2deg)"></i></div>
   <svg class="ckarr-flag" viewBox="0 0 34 56"><rect x="3" y="2" width="2.5" height="54" fill="#8A8A8A"/><path d="M5.5 3h24l-5 7 5 7h-24z" fill="#E36C09"/><text x="16" y="13.5" font-size="7.5" font-weight="700" fill="#fff" text-anchor="middle" font-family="Arial, sans-serif">9:30</text></svg>
   <div data-k="people"></div><div class="ckarr-ticks" data-k="ticks"></div>
  </div>
  <div class="ckarr-steps"><span>One card, one job</span><span>Cards checked</span><span>Help manual ready</span><span>MIS coordinators testing</span></div>
 </div>
 <div class="ckarr-bi">
  <div class="ckarr-col" lang="en"><div class="ckarr-lang">English</div>
   <h3>What matters to you<span class="ckarr-phase">PHASE 1</span></h3><ol>${li(s.en)}</ol>
   <div class="ckarr-note">We ask for your support. Use it every day and tell us what is not working. This will help us do our work efficiently, stay informed, and measure what we do.</div>
   <div class="ckarr-warn">This is the first phase. There may be bugs and glitches. Your feedback will make it stronger. Use <b>Report an Issue</b> or tell your MIS coordinator.</div>
   <p class="ckarr-thanks">All the best. Thank you.</p></div>
  <div class="ckarr-col ckarr-ta" lang="ta"><div class="ckarr-lang">தமிழ்</div>
   <h3>உங்களுக்கு முக்கியமானவை<span class="ckarr-phase">முதல் கட்டம்</span></h3><ol>${li(s.ta)}</ol>
   <div class="ckarr-note">உங்கள் ஆதரவைக் கேட்கிறோம். தினமும் பயன்படுத்துங்கள்; எது சரியாக வேலை செய்யவில்லை என்று சொல்லுங்கள். இது நம் வேலையைத் திறமையாகச் செய்யவும், தகவலுடன் இருக்கவும், நம் பணியை அளவிடவும் உதவும்.</div>
   <div class="ckarr-warn">இது முதல் கட்டம். சில பிழைகளும் சிக்கல்களும் இருக்கலாம். உங்கள் கருத்துகள் இதை வலுப்படுத்தும். <b>Report an Issue</b> பக்கத்தில் பதிவு செய்யுங்கள் அல்லது உங்கள் MIS ஒருங்கிணைப்பாளரிடம் சொல்லுங்கள்.</div>
   <p class="ckarr-thanks">வாழ்த்துகள். நன்றி.</p></div>
 </div>
 <footer class="ckarr-foot"><button class="ckarr-exit" type="button">Got it, close · <span class="ckarr-ta">சரி, மூடு</span></button></footer>
</section>`;
		const q = (k) => ov.querySelector('[data-k="' + k + '"]');

		// scene: 10 boxes of 3 cards from 4% to 80%; four people (two women, two men)
		const X0 = 4, X1 = 80, NB = 10, PER = 3;
		const COLOURS = ["ckarr-gold", "ckarr-gold", "ckarr-orange", "ckarr-gold", "ckarr-green", "ckarr-gold", "ckarr-rose", "ckarr-gold", "ckarr-blue"];
		const xAt = (t) => X0 + (t - START) / SPAN * (X1 - X0);
		[["Tue", "2026-09-29T00:00:00+05:30"], ["Wed", "2026-09-30T00:00:00+05:30"]].forEach((t) => {
			const el = document.createElement("span"); el.className = "ckarr-tick"; el.textContent = t[0];
			el.style.left = xAt(Date.parse(t[1])) + "%"; q("ticks").appendChild(el);
		});
		const boxes = [];
		for (let i = 0; i < NB; i++) {
			const b = document.createElement("div"); b.className = "ckarr-box";
			b.style.left = (X0 + i * ((X1 - X0) / (NB - 1))) + "%";
			b.innerHTML = '<div class="ckarr-tray"></div>'; q("boxes").appendChild(b); boxes.push({ el: b, n: -1 });
		}
		const people = q("people");
		const add = (cls, html) => { const d = document.createElement("div"); d.className = cls; d.innerHTML = html || ""; people.appendChild(d); return d; };
		const tosser = add("ckarr-p ckarr-tosser", figure("w", "#8D5524", "#E36C09", "#1B1B1B", true, false));
		const fly = add("ckarr-fly");
		const sparks = [[-2, 34], [14, 40], [26, 32], [8, 24]].map((p, i) => { const s = add("ckarr-spark"); s.style.animationDelay = (i * 0.05) + "s"; s.dx = p[0]; s.dy = p[1]; return s; });
		const carrier = add("ckarr-lane", '<div class="ckarr-p">' + figure("m", "#C68642", "#1F6FB2", "#2B2B2B", true, true) + "</div>");
		carrier.style.setProperty("--dur", "5s");
		const org = add("ckarr-lane", '<div class="ckarr-p">' + figure("w", "#A0663B", "#3C8D3F", "#2A1A10", true, true) + "</div>");
		org.style.setProperty("--dur", "4.4s");
		const lift = add("ckarr-lift ckarr-gold"); lift.style.setProperty("--dur", "4.4s");
		const checker = add("ckarr-p ckarr-checker", figure("m", "#7A4A2A", "#6D6D6D", "#151515", false, false,
			'<rect x="23" y="17" width="6" height="8" rx="1" fill="#fff" stroke="#8A8A8A" stroke-width=".8"/><path d="M24.5 21 l1.2 1.3 2-2.6" stroke="#3C8D3F" stroke-width="1" fill="none"/>'));
		checker.style.left = "calc(90% - 30px)";

		draw = function () {
			const l = left();
			q("d").textContent = Math.floor(l / 864e5); q("h").textContent = pad(Math.floor(l % 864e5 / 36e5));
			q("m").textContent = pad(Math.floor(l % 36e5 / 6e4)); q("s").textContent = pad(Math.floor(l % 6e4 / 1e3));
			const p = progress();
			q("pct").textContent = Math.floor(p * 100) + "%";
			const total = Math.floor(p * NB * PER), cur = Math.min(NB - 1, Math.floor(total / PER));
			boxes.forEach((bx, i) => {
				const n = Math.max(0, Math.min(PER, total - i * PER));
				if (n !== bx.n) {
					const old = bx.n; bx.n = n;
					bx.el.querySelectorAll(".ckarr-card").forEach((c) => c.remove());
					for (let k = 0; k < n; k++) {
						const c = document.createElement("span");
						c.className = "ckarr-card " + COLOURS[(i * PER + k) % COLOURS.length] + (old >= 0 && k >= old ? " new" : "");
						c.style.bottom = (12 + k * 5) + "px"; c.style.transform = "rotate(" + ((k % 2 ? 1 : -1) * (3 + k * 2)) + "deg)";
						bx.el.appendChild(c);
					}
				}
				bx.el.classList.toggle("full", n === PER);
				bx.el.classList.toggle("now", i === cur && n < PER);
			});
			const at = parseFloat(boxes[cur].el.style.left);
			tosser.style.left = "calc(" + at + "% - 15px)";
			fly.style.left = "calc(" + at + "% - 18px)"; fly.style.bottom = "54px";
			sparks.forEach((s) => { s.style.left = "calc(" + at + "% + " + (s.dx - 12) + "px)"; s.style.bottom = (19 + s.dy) + "px"; });
			// carrier brings cards from the pile near the flag to the woman placing them
			const cl = at + 3, cw = 84 - cl;
			carrier.style.display = cw < 8 ? "none" : "";
			carrier.style.left = "calc(" + cl + "% + 10px)"; carrier.style.width = "calc(" + cw + "% - 10px)";
			// organiser lifts a card from one full box and sets it right in the box before it
			if (cur >= 2) {
				const a = parseFloat(boxes[cur - 2].el.style.left), b2 = parseFloat(boxes[cur - 1].el.style.left);
				org.style.display = lift.style.display = "";
				org.style.left = "calc(" + a + "% - 4px)"; org.style.width = "calc(" + (b2 - a) + "% - 24px)";
				lift.style.left = "calc(" + b2 + "% - 8px)"; lift.style.bottom = "44px";
			} else { org.style.display = lift.style.display = "none"; }
		};

		ov.querySelector(".ckarr-exit").addEventListener("click", close);
		ov.addEventListener("click", (e) => { if (e.target === ov) close(); });
		document.body.appendChild(ov);
		close();
	}

	function open() {
		if (!ov || left() === 0) return;
		ov.hidden = false; ov.style.display = "";
		draw();
		const b = ov.querySelector(".ckarr-exit"); if (b) b.focus({ preventScroll: true });
	}
	function close() { if (ov) { ov.hidden = true; ov.style.display = "none"; } }
	function isOpen() { return ov && !ov.hidden; }

	// ---------- sidebar row ----------
	function sideRow() {
		const sb = document.querySelector(".body-sidebar");
		if (!sb || sb.querySelector(".ckarr-side")) return;
		const el = document.createElement("button");
		el.type = "button"; el.className = "ckarr-side";
		el.innerHTML = '<svg class="ckarr-ring" viewBox="0 0 30 30" aria-hidden="true"><circle cx="15" cy="15" r="12" stroke="#F7C9A0"/>' +
			'<circle class="fg" cx="15" cy="15" r="12" stroke="#E36C09" stroke-linecap="round" stroke-dasharray="75.4" transform="rotate(-90 15 15)"/></svg>' +
			'<span class="ckarr-stxt"><small></small><strong></strong></span>';
		el.addEventListener("click", () => { if (left() > 0) open(); else location.href = COCKPIT_URL; });
		const top = sb.querySelector(".body-sidebar-top");
		if (top && top.parentNode) top.parentNode.insertBefore(el, top); else sb.prepend(el);
	}
	function drawSide() {
		const el = document.querySelector(".ckarr-side");
		if (!el) return;
		const sb = el.closest(".body-sidebar");
		el.classList.toggle("mini", !!sb && sb.getBoundingClientRect().width < 120);
		const l = left();
		el.querySelector(".fg").setAttribute("stroke-dashoffset", (75.4 * (1 - progress())).toFixed(1));
		if (l > 0) {
			const d = Math.floor(l / 864e5);
			el.querySelector("small").innerHTML = 'Cockpit arrives · <span class="ckarr-ta">காக்பிட் வருகிறது</span>';
			el.querySelector("strong").textContent = (d ? d + "d " : "") + pad(Math.floor(l % 864e5 / 36e5)) + "h " + pad(Math.floor(l % 36e5 / 6e4)) + "m " + pad(Math.floor(l % 6e4 / 1e3)) + "s";
			el.setAttribute("aria-label", "Cockpit countdown. Open the banner");
		} else {
			el.querySelector("small").innerHTML = 'Your Cockpit is open · <span class="ckarr-ta">திறந்துவிட்டது</span>';
			el.querySelector("strong").textContent = "Open My Cockpit ›";
			el.setAttribute("aria-label", "Open My Cockpit");
		}
	}

	// ---------- show rule: every 3rd fresh visit, or 2 h since last shown ----------
	function shouldShow() {
		if (/[?&]ck_arriving=/.test(location.search)) return true;
		const key = "ckarr_" + frappe.session.user;
		let st = {};
		try { st = JSON.parse(ls(key) || "{}") || {}; } catch (e) { st = {}; }
		if (ss("ckarr_seen")) return false; // already counted in this browser session
		ss("ckarr_seen", "1");
		st.n = (st.n || 0) + 1;
		const now = Date.now();
		const show = (st.n - 1) % 3 === 0 || !st.last || now - st.last >= 2 * 36e5;
		if (show) st.last = now;
		ls(key, JSON.stringify(st));
		return show;
	}

	function start() {
		if (Date.now() >= STOP) return;
		const kind = audience();
		if (!kind) return;
		const st = document.createElement("style"); st.textContent = CSS; document.head.appendChild(st);
		const f = document.createElement("link"); f.rel = "stylesheet";
		f.href = "https://fonts.googleapis.com/css2?family=Hind+Madurai:wght@400;600;700&display=swap";
		document.head.appendChild(f);
		if (left() > 0) {
			build(kind);
			if (shouldShow()) open();
		}
		document.addEventListener("keydown", (e) => { if (e.key === "Escape" && isOpen()) close(); });
		const tick = () => {
			if (Date.now() >= STOP) { const el = document.querySelector(".ckarr-side"); if (el) el.remove(); return; }
			sideRow(); drawSide();
			if (isOpen()) { if (left() === 0) close(); else draw(); }
		};
		tick();
		setInterval(tick, 1000);
	}

	// wait for the desk to boot (user roles known, body present)
	let tries = 0;
	(function wait() {
		if (window.frappe && frappe.session && frappe.session.user && frappe.session.user !== "Guest" && frappe.user_roles && document.body) {
			try { start(); } catch (e) { console.warn("cockpit_arriving", e); }
			return;
		}
		if (++tries < 120) setTimeout(wait, 500);
	})();
})();
