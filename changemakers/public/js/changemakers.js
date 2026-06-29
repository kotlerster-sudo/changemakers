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

// ── APF sidebar: inject the "Operational Programs · Chennai" caption ──────────
// The desk sidebar header has a fixed height + truncate(), which clips any CSS
// ::after, so we add the caption as a real DOM element. Idempotent; re-applies
// when the sidebar re-renders on navigation. Styled via .apf-prog-caption.
(function () {
    var CAPTION = "Operational Programmes";
    function ensureCaption() {
        var tc = document.querySelector(".body-sidebar .sidebar-header .title-container");
        if (!tc || tc.querySelector(".apf-prog-caption")) return;
        var el = document.createElement("div");
        el.className = "apf-prog-caption";
        el.textContent = CAPTION;
        tc.appendChild(el);
    }
    function start() {
        ensureCaption();
        new MutationObserver(ensureCaption).observe(document.body, {
            childList: true,
            subtree: true,
        });
    }
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", start);
    } else {
        start();
    }
})();

