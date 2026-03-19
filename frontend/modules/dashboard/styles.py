PARENT_JS = """
// Relay messages from the map iframe back to Shiny
window.addEventListener('message', function(event) {
    if (!event.data || !event.data.type) return;
    if (event.data.type === 'zip_click') {
        Shiny.setInputValue('map_click', event.data, {priority: 'event'});
    }
    if (event.data.type === 'opacity_save') {
        Shiny.setInputValue('map_opacity', event.data.value, {priority: 'event'});
    }
    if (event.data.type === 'state_change') {
        Shiny.setInputValue('map_state_change', event.data.state, {priority: 'event'});
    }
});

// Handle leaderboard ZIP click — navigate to ZIP and highlight
$(document).on('click', '.leaderboard-zip', function() {
    var zip = $(this).data('zip');
    var state = $(this).data('state');
    Shiny.setInputValue('leaderboard_click', {zipcode: zip, state: state}, {priority: 'event'});
    window._pendingFocusZip = String(zip);
    window._focusBlinkDone = false;
    var attempts = 0;
    function tryFocus() {
        if (window._focusBlinkDone || attempts >= 24) return;
        var iframe = document.getElementById('map_frame');
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage({type: 'focus_blink', zipcode: window._pendingFocusZip}, '*');
        }
        attempts++;
        setTimeout(tryFocus, 500);
    }
    tryFocus();
});

// Clear transient map highlight when switching tabs.
$(document).on('click', '.sidebar .nav-underline .nav-link', function() {
    setTimeout(function() {
        var iframe = document.getElementById('map_frame');
        if (iframe && iframe.contentWindow) {
            iframe.contentWindow.postMessage({type: 'clear_focus_highlight'}, '*');
        }
    }, 50);
});

// Listen for blink acknowledgement from iframe
window.addEventListener('message', function(event) {
    if (event.data && event.data.type === 'blink_ack') {
        window._focusBlinkDone = true;
    }
});

// Handle chip remove button — deselect a ZIP
$(document).on('click', '.chip-remove', function(e) {
    if (e) {
        e.preventDefault();
        e.stopPropagation();
    }
    var zip = $(this).data('zip');
    Shiny.setInputValue('chip_remove', {zipcode: String(zip)}, {priority: 'event'});
    var iframe = document.getElementById('map_frame');
    if (iframe && iframe.contentWindow) {
        iframe.contentWindow.postMessage({type: 'deselect_zip', zipcode: String(zip)}, '*');
    }
});

// Auto-clear the file name text after upload completes
setInterval(function() {
    var inputs = document.querySelectorAll('.sidebar .form-control[readonly]');
    inputs.forEach(function(el) {
        if (el.value && el.value.trim() !== '') {
            var container = el.closest('.shiny-input-container');
            if (container) {
                var progress = container.querySelector('.progress');
                var done = progress && (progress.style.display === 'none' ||
                    progress.querySelector('.progress-bar[style*="100"]'));
                if (done || !progress) {
                    setTimeout(function() { el.value = ''; }, 1500);
                }
            }
        }
    });
}, 1000);
"""

APP_CSS = """
html, body { margin:0; padding:0; overflow:hidden; height:100vh; }

/* Remove page padding */
.bslib-page-fill, .bslib-page-sidebar { padding:0 !important; }
.bslib-sidebar-layout > .main { padding:0 !important; overflow:hidden !important; }

/* Map background */
.bslib-sidebar-layout > .main { background:#000 !important; }

/* Sidebar — white dashboard surface with orange accents */
.bslib-sidebar-layout > .sidebar {
    background:#ffffff !important;
    border-right:3px solid #ffffff !important;
    color:#1a1a1a !important;
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif !important;
    overflow:visible !important;
    max-height:100vh;
    width: 635px !important;
    min-width: 635px !important;
    max-width: 635px !important;
    resize: none !important;
}
.bslib-sidebar-layout > .sidebar > .sidebar-content {
    overflow-y:auto !important;
    overflow-x:hidden !important;
    max-height:100vh;
    padding: 0 2px;
    scrollbar-width: thin;
    scrollbar-color: #ff7f00 transparent;
}
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar { width: 1px; }
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar-track { background: transparent; }
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar-thumb { background: #ff7f00; border-radius: 2px; }
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar-thumb:hover { background: #e56f00; }

/* Disable sidebar resizing entirely */
.bslib-sidebar-layout > .collapse-toggle,
.bslib-sidebar-layout > .sidebar-resizer,
.bslib-sidebar-layout > [class*="resize"],
.bslib-sidebar-layout > .bslib-sidebar-resize-handle {
    display: none !important;
    pointer-events: none !important;
    width: 0 !important;
}
.bslib-sidebar-layout {
    grid-template-columns: 635px 1fr !important;
}

/* Dark mode overrides */
:root[data-theme="dark"] .bslib-sidebar-layout > .sidebar {
    background: #111827 !important;
    border-right: 1px solid #374151 !important;
    color: #e5e7eb !important;
}
:root[data-theme="dark"] .sidebar h5,
:root[data-theme="dark"] .sidebar label,
:root[data-theme="dark"] .sidebar .control-label,
:root[data-theme="dark"] .sidebar,
:root[data-theme="dark"] .sidebar .nav-underline .nav-link,
:root[data-theme="dark"] .sidebar .nav-underline .nav-link.active {
    color: #e5e7eb !important;
}
:root[data-theme="dark"] .sidebar .nav-underline .nav-link.active {
    border-bottom-color: #f59e0b !important;
}
:root[data-theme="dark"] .sidebar .form-select,
:root[data-theme="dark"] .sidebar select,
:root[data-theme="dark"] .sidebar input[type="text"],
:root[data-theme="dark"] .sidebar .form-control {
    background: #1f2937 !important;
    color: #e5e7eb !important;
    border-color: #4b5563 !important;
}
:root[data-theme="dark"] .market-detail-block,
:root[data-theme="dark"] .market-zip-item,
:root[data-theme="dark"] .def-card,
:root[data-theme="dark"] .def-formula,
:root[data-theme="dark"] .def-ui-banner {
    background: #1f2937 !important;
    border-color: #374151 !important;
}
:root[data-theme="dark"] .def-title,
:root[data-theme="dark"] .def-title-lg,
:root[data-theme="dark"] .def-formula-eq,
:root[data-theme="dark"] .def-body,
:root[data-theme="dark"] .def-marker-text,
:root[data-theme="dark"] .def-ui-banner-title {
    color: #e5e7eb !important;
}
:root[data-theme="dark"] .tier-dropdown {
    border-top-color: #374151 !important;
}
:root[data-theme="dark"] .tier-dropdown-summary:hover,
:root[data-theme="dark"] .zip-detail-summary:hover,
:root[data-theme="dark"] .leaderboard-zip:hover td {
    background: #243041 !important;
}
:root[data-theme="dark"] .zip-detail-content,
:root[data-theme="dark"] .market-detail-content {
    border-top-color: #374151 !important;
}
:root[data-theme="dark"] .map-chip {
    background: #ff7f00 !important;
    border-color: #ff7f00 !important;
    color: #fff !important;
}
:root[data-theme="dark"] .map-chip .chip-remove:hover {
    background: #ff9b1a !important;
    color: #fff !important;
}

/* Hide shiny chrome */
.navbar, nav, .bslib-page-sidebar > nav { display:none !important; }
#MainMenu, footer, header { visibility:hidden; display:none !important; }
button[data-testid="collapsedControl"] { display:none !important; }

/* Sidebar text */
.sidebar h5, .sidebar label, .sidebar .control-label { color:#1a1a1a !important; }

/* ── Tab styling ─────────────────────────────────────────────────────── */

/* Tab bar */
.sidebar .nav-underline {
    border-bottom: none !important;
    gap: 0 !important;
    padding: 0 2px;
    flex-wrap: nowrap !important;
    justify-content: center !important;
    margin-bottom: 4px;
}

/* Tab items */
.sidebar .nav-underline .nav-link {
    color: #ffffff !important;
    font-size: 0.8rem !important;
    font-weight: 500 !important;
    padding: 12px 10px 6px !important;
    border-bottom: 2px solid transparent !important;
    background: transparent !important;
    transition: color 0.15s, border-color 0.15s;
    white-space: nowrap;
}
.sidebar .nav-underline .nav-link:hover {
    color: #ff7f00 !important;
    border-bottom-color: #ff7f00 !important;
}
.sidebar .nav-underline .nav-link.active {
    color: #ff7f00 !important;
    font-weight: 600 !important;
    border-bottom-color: #ff7f00 !important;
    background: transparent !important;
}

/* Tab content panels */
.sidebar .tab-content {
    padding-top: 6px;
    padding-left: 4px;
    padding-right: 4px;
    background: #ffffff !important;
}

/* Prevent focus outlines from being clipped by overflow:hidden */
.sidebar *:focus {
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(255,127,0,0.3) !important;
    border-color: #ff7f00 !important;
}
.sidebar *:focus:not(:focus-visible) {
    box-shadow: none !important;
}

/* ── Section containers ──────────────────────────────────────────────── */

/* Settings section */
.settings-section {
    padding-top: 4px;
    overflow-y: auto;
    background: #ffffff;
    scrollbar-width: thin;
    scrollbar-color: #ff7f00 transparent;
}
.settings-section::-webkit-scrollbar { width: 1px; }
.settings-section::-webkit-scrollbar-track { background: transparent; }
.settings-section::-webkit-scrollbar-thumb { background: #ff7f00; border-radius: 2px; }
.settings-section::-webkit-scrollbar-thumb:hover { background: #e56f00; }

/* Definitions section */
.definitions-section {
    padding: 16px 12px 8px 18px;
    overflow-y: auto;
    max-height: calc(100vh - 96px);
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif;
    background: #ffffff;
    border: none;
    border-radius: 0;
    margin: 0;
    scrollbar-width: thin;
    scrollbar-color: #ff7f00 transparent;
}
.definitions-section::-webkit-scrollbar { width: 1px; }
.definitions-section::-webkit-scrollbar-track { background: transparent; }
.definitions-section::-webkit-scrollbar-thumb { background: #ff7f00; border-radius: 2px; }
.definitions-section::-webkit-scrollbar-thumb:hover { background: #e56f00; }
.def-card {
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0 0 8px;
    margin-bottom: 34px;
}
.definitions-section .def-card:last-child {
    margin-bottom: 6px;
    padding-bottom: 2px;
}
.def-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 22px;
}
.def-title-lg {
    font-size: 1.1rem;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 24px;
}
.def-subtitle {
    font-size: 0.68rem;
    color: #1a1a1a;
    margin-bottom: 8px;
    line-height: 1.35;
}
.def-note {
    font-size: 0.64rem;
    color: #1a1a1a;
    margin-top: 6px;
}
.def-body {
    font-size: 0.72rem;
    color: #1a1a1a;
    line-height: 1.45;
}
.def-card .def-body {
    margin-top: 10px;
}
.def-section-divider,
.definitions-section hr.def-section-divider {
    border: none;
    border-top: 2px solid #ff7f00 !important;
    margin: 14px 0 22px;
    opacity: 1 !important;
    height: 0 !important;
    border-color: #ff7f00 !important;
}
.def-constructs-body .def-dim {
    margin-bottom: 21px;
}
.def-constructs-body .def-dim:nth-of-type(1),
.def-constructs-body .def-dim:nth-of-type(2) {
    margin-bottom: 32px;
}
.def-constructs-body .def-dim:last-of-type {
    margin-bottom: 8px;
}
.def-dim {
    margin-bottom: 18px;
}
.def-bullet {
    display: inline-block;
    width: 5px;
    height: 5px;
    border-radius: 50%;
    background: #ffffff;
    margin-right: 8px;
    vertical-align: middle;
}
.def-dim:last-child {
    margin-bottom: 8px;
}
.def-construct-ui {
    display: flex;
    align-items: center;
    justify-content: center;
    gap: 10px;
    margin: 2px 0 18px;
}
.def-ball {
    display: inline-block;
    border-radius: 999px;
    border: 1px solid #1a1a1a;
    width: 14px;
    height: 14px;
}
.def-ball-red { background: #dc2626; }
.def-ball-yellow { background: #f59e0b; }
.def-ball-green { background: #22c55e; }
.def-ball-sm { width: 10px; height: 10px; }
.def-ball-md { width: 14px; height: 14px; }
.def-ball-lg { width: 20px; height: 20px; }
.definitions-section .def-body b {
    text-decoration: none;
    text-underline-offset: 0;
}
/* Only tier dropdown definition labels should be underlined */
.definitions-section .tier-dropdown-content .def-dim b {
    text-decoration: underline;
    text-underline-offset: 2px;
}
.def-formula {
    border: 1px solid #000000;
    border-radius: 8px;
    background: #ffffff;
    padding: 10px 12px;
    margin-bottom: 10px;
    box-shadow: 0 2px 8px rgba(255, 127, 0, 0.12);
    position: relative;
}
.def-formula::before {
    content: "";
    position: absolute;
    left: 0;
    top: 0;
    bottom: 0;
    width: 4px;
    border-radius: 8px 0 0 8px;
    background: #000000;
}
.def-card .def-formula {
    margin-top: 10px;
    margin-bottom: 12px;
}
.def-score-block {
    border: none;
    border-radius: 0;
    padding: 10px 0 8px;
    margin: 8px 0;
    background: transparent;
}
.def-score-block + .def-score-block {
    margin-top: 18px;
    padding-top: 18px;
    border-top: 2px solid #ff7f00;
}
.def-score-block .def-body {
    margin-top: 0;
    font-size: 0.67rem;
    line-height: 1.35;
}
.def-score-block .def-formula,
.def-score-block .def-ui-banner {
    border: none;
    box-shadow: none;
    margin-top: 8px;
}
.def-score-block .def-formula::before {
    display: none;
}
.def-formula-eq {
    font-size: 0.74rem;
    font-weight: 700;
    color: #1f2937;
    margin-bottom: 8px;
    letter-spacing: 0.01em;
}
.def-formula-row {
    display: flex;
    align-items: center;
    gap: 10px;
    font-size: 0.72rem;
    color: #1a1a1a;
    margin-bottom: 6px;
}
.def-formula-row:last-child {
    margin-bottom: 0;
}
.def-chip {
    display: inline-block;
    min-width: 44px;
    text-align: center;
    border: 1px solid #ff7f00;
    border-radius: 10px;
    padding: 1px 8px;
    font-size: 0.68rem;
    font-weight: 600;
    color: #fff;
    background: #ff7f00;
}

/* Ensure scoring/formula text is readable in Definitions dark theme */
.def-formula-eq,
.def-formula-row,
.def-formula-row span,
.def-chip,
.def-ui-banner-title,
.def-score-edge,
.def-marker-text {
    color: #ffffff !important;
}
.def-ui-banner {
    border: 1px solid #000000;
    border-radius: 8px;
    background: #ffffff;
    padding: 8px 10px;
    margin-bottom: 8px;
    font-family: inherit;
}
.def-card .def-ui-banner {
    margin-top: 10px;
    margin-bottom: 12px;
}
.def-ui-banner-market {
    margin-bottom: 4px !important;
}
.def-card-formula .def-formula {
    margin-top: 20px;
    margin-bottom: 26px;
    padding-top: 12px;
    padding-bottom: 12px;
}
.def-card-formula .def-formula,
.def-card-formula .def-ui-banner {
    border: none !important;
    background: transparent !important;
    box-shadow: none !important;
}
.def-card-formula .def-formula-row {
    margin-bottom: 10px;
}
.def-card-formula .def-ui-banner {
    margin-top: 16px;
    margin-bottom: 26px;
    padding-top: 12px;
    padding-bottom: 12px;
}
.def-card-formula .def-body {
    margin-top: 14px;
    margin-bottom: 6px;
}
.def-score-title {
    font-size: 0.88rem !important;
    font-weight: 700 !important;
    margin-bottom: 8px !important;
}
.def-ui-banner-title {
    font-size: 0.72rem;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 12px;
    font-family: inherit;
}
.def-score-legend {
    display: flex;
    align-items: center;
    gap: 8px;
    font-family: inherit;
}
.def-score-edge {
    font-size: 0.68rem;
    font-weight: 700;
    color: #1a1a1a;
    letter-spacing: 0.03em;
    font-family: inherit;
}
.def-score-gradient {
    flex: 1;
    height: 12px;
    border: none;
    border-radius: 0;
    background: linear-gradient(to right,#ffffff,#fff0d4,#ffd699,#ffb84d,#ff9b1a,#ff7f00);
}
.def-marker-row {
    display: flex;
    align-items: center;
    gap: 10px;
}
.def-marker-pin {
    display: inline-flex;
    width: 16px;
    height: 22px;
    flex: 0 0 auto;
}
.def-marker-pin svg {
    width: 16px;
    height: 22px;
    display: block;
}
.def-marker-text {
    font-size: 0.72rem;
    color: #1a1a1a;
    line-height: 1.35;
}

/* Settings section */
.settings-section {
    padding: 4px 4px 0;
    overflow-y: auto;
    background: #ffffff;
}
.settings-section .shiny-input-container {
    max-width: none !important;
}
.settings-section .form-select, .settings-section select {
    font-size: 0.74rem !important;
    padding: 5px 8px !important;
    border: 1px solid #ffe0b2 !important;
    border-radius: 6px !important;
    background: #fff !important;
    color: #1a1a1a !important;
    height: auto !important;
}
.settings-section .form-label {
    font-size: 0.8rem !important;
}
.settings-section .shiny-input-container:has(.btn-file) {
    background: #fff;
    border: 2px dashed #ffe0b2;
    border-radius: 10px;
    padding: 14px 16px;
    margin-bottom: 10px;
    transition: border-color 0.2s, background 0.2s;
}
.settings-section .shiny-input-container:has(.btn-file):hover {
    border-color: #ff7f00;
    background: #fff8f0;
}
.settings-section > .shiny-input-container > label.control-label {
    font-size: 0.78rem !important;
    color: #1a1a1a !important;
    font-weight: 500 !important;
}

/* Settings weights */
.settings-shell {
    padding: 14px 12px 12px 18px;
    margin: 0;
    background: #ffffff;
    border: none;
    border-radius: 0;
    max-height: none;
    display: flex;
    flex-direction: column;
    gap: 10px;
    overflow: visible;
}
.settings-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
    margin-bottom: 24px;
}
.settings-map-filters-shell {
    display: flex;
    flex-direction: column;
    gap: 8px;
    padding: 14px 12px 0 18px;
}
.settings-map-head .btn,
.settings-selected-zips-head .btn {
    background: #000000 !important;
    border: 1px solid #ffffff !important;
    color: #ffffff !important;
    font-size: 0.7rem !important;
    padding: 4px 9px !important;
    border-radius: 0 !important;
}
.settings-map-filters-body {
    display: grid;
    grid-template-columns: 1fr;
    gap: 6px;
    border: none;
    border-radius: 0;
    background: transparent;
    padding: 0;
    font-size: 0.72rem;
}
.settings-map-filters-body .shiny-input-container {
    margin-bottom: 0 !important;
}
.settings-map-filters-body .control-label,
.settings-map-filters-body .form-label,
.settings-map-filters-body .form-check-label {
    color: #ffffff !important;
    font-size: 0.72rem !important;
}
.settings-map-subtitle {
    color: #ffffff !important;
    font-size: 0.72rem !important;
    font-weight: 700 !important;
    margin-bottom: 2px;
}
.settings-map-filters-body .form-select,
.settings-map-filters-body #settings_map_state {
    background: #000000 !important;
    color: #ffffff !important;
    border: 1px solid #ffffff !important;
    border-radius: 0 !important;
    font-size: 0.72rem !important;
}
.settings-map-filters-body #settings_map_state option {
    background: #000000 !important;
    color: #ffffff !important;
}
.settings-map-filters-body .form-check-input {
    appearance: none !important;
    -webkit-appearance: none !important;
    width: 16px !important;
    height: 16px !important;
    margin-top: 0 !important;
    border: 1px solid #ff7f00 !important;
    border-radius: 0 !important;
    background: #000000 !important;
    box-shadow: none !important;
    display: inline-grid !important;
    place-content: center !important;
    vertical-align: middle !important;
}
.settings-map-filters-body .form-check-input::before {
    content: "" !important;
    width: 9px !important;
    height: 9px !important;
    transform: scale(0) !important;
    transition: transform 120ms ease-in-out !important;
    box-shadow: inset 1em 1em #000000 !important;
    clip-path: polygon(14% 44%, 0 59%, 42% 100%, 100% 16%, 84% 0, 41% 62%) !important;
}
.settings-map-filters-body .form-check-input:checked {
    background: #ff7f00 !important;
    border-color: #ff7f00 !important;
}
.settings-map-filters-body .form-check-input:checked::before {
    transform: scale(1) !important;
}
.settings-map-filters-body .form-check-input:checked + .form-check-label {
    color: #ffffff !important;
}
.settings-map-filters-body .form-check:has(.form-check-input:checked) .form-check-label {
    color: #ffffff !important;
}
.settings-map-filters-body input[type="checkbox"] {
    appearance: none !important;
    -webkit-appearance: none !important;
    width: 16px !important;
    height: 16px !important;
    margin-top: 0 !important;
    border: 1px solid #ff7f00 !important;
    border-radius: 0 !important;
    background: #000000 !important;
    box-shadow: none !important;
    display: inline-grid !important;
    place-content: center !important;
    vertical-align: middle !important;
}
.settings-map-filters-body input[type="checkbox"]::before {
    content: "" !important;
    width: 9px !important;
    height: 9px !important;
    transform: scale(0) !important;
    transition: transform 120ms ease-in-out !important;
    box-shadow: inset 1em 1em #000000 !important;
    clip-path: polygon(14% 44%, 0 59%, 42% 100%, 100% 16%, 84% 0, 41% 62%) !important;
}
.settings-map-filters-body input[type="checkbox"]:checked {
    background: #ff7f00 !important;
    border-color: #ff7f00 !important;
}
.settings-map-filters-body input[type="checkbox"]:checked::before {
    transform: scale(1) !important;
}
.settings-map-filters-body input[type="checkbox"]:checked + label,
.settings-map-filters-body label:has(input[type="checkbox"]:checked) {
    color: #ffffff !important;
}
.settings-map-state-wrap {
    margin-top: 10px;
}
.settings-map-state-wrap .control-label,
.settings-map-state-wrap .form-label {
    font-weight: 700 !important;
    color: #ffffff !important;
}
.settings-selected-zips-wrap {
    margin-top: 10px;
}
.settings-selected-zips-head {
    display: flex;
    align-items: center;
    justify-content: space-between;
    gap: 8px;
}
.settings-selected-zips {
    color: #ffffff !important;
    font-size: 0.72rem !important;
    line-height: 1.35;
    word-break: break-word;
}
.settings-selected-zips-line {
    margin: 2px 0;
}
.settings-section > .def-section-divider {
    margin: 38px 0 22px !important;
}
.settings-dim-card .irs--shiny .irs-from,
.settings-dim-card .irs--shiny .irs-to,
.settings-dim-card .irs--shiny .irs-single,
.settings-dim-card .form-label,
.settings-dim-card .control-label,
.settings-dim-card label {
    font-size: 0.72rem !important;
}
.settings-dim-card .irs--shiny .irs-min,
.settings-dim-card .irs--shiny .irs-max {
    display: none !important;
}
.settings-actions {
    display: flex;
    align-items: center;
    gap: 8px;
}
.settings-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #ff7f00;
    margin: 0;
    padding: 0 0 2px;
}
.settings-construct-mini-title {
    font-size: 0.76rem;
    font-weight: 700;
    color: #ffffff;
    margin: 6px 0 8px;
    letter-spacing: 0.01em;
}
.settings-construct-group {
    display: grid;
    gap: 6px;
    margin-bottom: 22px;
}
.settings-construct-group:last-child {
    margin-bottom: 0;
}
.settings-construct-group .settings-tier-dropdown {
    margin-top: 0 !important;
    margin-bottom: 2px;
}
.settings-construct-group .settings-tier-dropdown:last-child {
    margin-bottom: 0;
}
.settings-head .btn {
    background: #ff7f00 !important;
    border: 1px solid #ff7f00 !important;
    color: #fff !important;
    font-size: 0.7rem !important;
    padding: 4px 9px !important;
    border-radius: 0 !important;
}
.settings-head #settings_reset_weights {
    background: #000000 !important;
    border: 1px solid #ffffff !important;
    color: #ffffff !important;
}
.settings-note {
    font-size: 0.67rem;
    color: #1a1a1a;
    background: #fff8f0;
    border: 1px solid #ffe0b2;
    border-radius: 8px;
    padding: 6px 8px;
    line-height: 1.35;
}
.settings-weight-grid {
    display: grid;
    grid-template-columns: 1fr;
    gap: 6px !important;
}
.settings-dim-card {
    border: 1px solid #ffe0b2;
    border-radius: 0;
    background: #000;
    padding: 4px 10px;
}
.settings-dim-card .shiny-input-container {
    margin-bottom: 0 !important;
}
.settings-dim-card .irs--shiny {
    margin: 0 4px !important;
}
.settings-dim-card .form-label {
    font-size: 0.72rem !important;
    color: #ffffff !important;
    font-weight: 600 !important;
}
.settings-shell input[type="range"] {
    appearance: none;
    -webkit-appearance: none;
    width: 100%;
    height: 8px;
    background: transparent;
    accent-color: #ff7f00;
}
.settings-shell input[type="range"]::-webkit-slider-runnable-track {
    height: 8px;
    background: #ff7f00;
    border-radius: 0;
    border: 1px solid rgba(0,0,0,0.25);
}
.settings-shell input[type="range"]::-webkit-slider-thumb {
    -webkit-appearance: none;
    width: 8px;
    height: 18px;
    border-radius: 0;
    background: #ffffff;
    border: 1px solid #ffffff;
    box-shadow: 0 0 3px rgba(0,0,0,0.35);
    margin-top: -5px;
}
.settings-shell input[type="range"]::-moz-range-track {
    height: 8px;
    background: #ff7f00;
    border-radius: 0;
    border: 1px solid rgba(0,0,0,0.25);
}
.settings-shell input[type="range"]::-moz-range-thumb {
    width: 8px;
    height: 18px;
    border-radius: 0;
    background: #ffffff;
    border: 1px solid #ffffff;
    box-shadow: 0 0 3px rgba(0,0,0,0.35);
}
/* Shiny slider widget skin (prevents default blue theme) */
.settings-shell .irs--shiny .irs-line {
    height: 8px !important;
    top: 24px !important;
    border: 1px solid rgba(0, 0, 0, 0.25) !important;
    background: #2b2b2b !important;
}
.settings-shell .irs--shiny .irs-bar {
    height: 8px !important;
    top: 24px !important;
    border: 1px solid rgba(0, 0, 0, 0.25) !important;
    background: #ff7f00 !important;
}
.settings-shell .irs--shiny .irs-handle {
    top: 19px !important;
    width: 8px !important;
    height: 18px !important;
    border-radius: 0 !important;
    border: 1px solid #ffffff !important;
    background: #ffffff !important;
    box-shadow: 0 0 3px rgba(0, 0, 0, 0.35) !important;
}
.settings-shell .irs--shiny .irs-handle > i:first-child {
    display: none !important;
}
.settings-shell .irs--shiny .irs-min,
.settings-shell .irs--shiny .irs-max,
.settings-shell .irs--shiny .irs-single {
    color: #ffffff !important;
    background: transparent !important;
    border: none !important;
    border-radius: 0 !important;
    box-shadow: none !important;
    padding: 0 !important;
}
.settings-dim-dropdown {
    margin-top: 6px;
    border-top: 1px solid #ffe0b2;
    padding-top: 6px;
}
.settings-dim-dropdown > summary {
    cursor: pointer;
    font-size: 0.74rem;
    font-weight: 600;
    color: #1a1a1a;
    list-style: none;
}
.settings-dim-dropdown > summary::-webkit-details-marker {
    display: none;
}
.settings-dim-dropdown > summary::before {
    content: '\\25B6';
    font-size: 0.5rem;
    margin-right: 8px;
    color: #1a1a1a;
    display: inline-block;
    transition: transform 0.15s;
}
.settings-dim-dropdown[open] > summary::before {
    transform: rotate(90deg);
}
.settings-indicator-grid {
    margin-top: 6px;
    display: grid;
    grid-template-columns: 1fr;
    gap: 4px;
    max-height: 280px;
    overflow-y: auto;
    padding-right: 4px;
}
.settings-indicator-grid .shiny-input-container {
    margin: 0 !important;
}
.settings-indicator-grid .form-label {
    font-size: 0.64rem !important;
    color: #1a1a1a !important;
    font-weight: 500 !important;
    margin-bottom: 2px !important;
}
.settings-indicator-grid input[type="range"] {
    accent-color: #ff7f00;
}

/* myAgent */
.agent-shell {
    padding: 14px 12px 12px 18px;
    margin: 0;
    background: #ffffff;
    border: none;
    border-radius: 0;
    max-height: calc(100vh - 96px);
    display: flex;
    flex-direction: column;
    gap: 8px;
    overflow: hidden;
}
.agent-title {
    font-size: 1.1rem;
    font-weight: 700;
    color: #1a1a1a;
    margin: 0;
    padding: 0 0 2px;
}
.agent-config {
    display: grid;
    grid-template-columns: 1fr;
    gap: 6px;
}
.agent-config .shiny-input-container {
    margin-bottom: 2px !important;
}
.agent-config .form-label {
    font-size: 0.72rem !important;
    color: #1a1a1a !important;
    font-weight: 600 !important;
}
.agent-config .form-control {
    font-size: 0.74rem !important;
    padding: 5px 8px !important;
    border: 1px solid #ffe0b2 !important;
    border-radius: 6px !important;
    background: #fff !important;
    color: #1a1a1a !important;
}
.agent-context {
    display: flex;
    flex-wrap: wrap;
    gap: 5px;
    font-size: 0.66rem;
    color: #1a1a1a;
    padding: 8px;
    border-bottom: 1px solid #ffffff;
}
.agent-context span {
    background: #000000;
    border: 1px solid #ffffff;
    border-radius: 0;
    padding: 2px 8px;
    color: #ffffff !important;
}
.agent-chat-block {
    background: #000000;
    border: 1px solid #ffffff;
    border-radius: 0;
    display: flex;
    flex-direction: column;
    /* Responsive height: slightly taller on laptops, scales on larger monitors */
    height: clamp(520px, 72vh, 920px);
    overflow: hidden;
}
.agent-thread-wrap {
    background: #000000;
    border: none;
    border-radius: 0;
    min-height: 0;
    max-height: none;
    flex: 1;
    min-width: 0;
    overflow-y: auto;
    padding: 10px;
    scrollbar-width: thin;
    scrollbar-color: #ff7f00 transparent;
}
.agent-thread-wrap::-webkit-scrollbar { width: 1px; }
.agent-thread-wrap::-webkit-scrollbar-track { background: transparent; }
.agent-thread-wrap::-webkit-scrollbar-thumb { background: #ff7f00; border-radius: 2px; }
.agent-thread-wrap::-webkit-scrollbar-thumb:hover { background: #e56f00; }
.agent-thread {
    display: flex;
    flex-direction: column;
    gap: 8px;
}
.agent-msg {
    max-width: 88%;
    border-radius: 10px;
    padding: 6px 8px;
    border: 1px solid #ffe0b2;
}
.agent-msg-user {
    align-self: flex-end;
    background: #ff7f00 !important;
    border: none !important;
}
.agent-msg-assistant {
    align-self: flex-start;
    background: #ffffff;
}
.agent-msg-label {
    font-size: 0.62rem;
    font-weight: 700;
    color: #ffffff;
    margin-bottom: 2px;
    letter-spacing: 0.02em;
}
.agent-msg-text {
    font-size: 0.72rem;
    color: #1a1a1a;
    line-height: 1.35;
}
.agent-msg-user .agent-msg-label,
.agent-msg-user .agent-msg-text,
.agent-title {
    color: #ffffff !important;
}
.agent-compose {
    display: grid;
    grid-template-columns: 1fr auto auto;
    gap: 6px;
    align-items: center;
    margin-top: 0;
    border-top: 1px solid #ffffff;
    padding: 8px;
    background: #000000;
}
.agent-compose .shiny-input-container {
    margin: 0 !important;
}
.agent-compose .form-control {
    font-size: 0.74rem !important;
    padding: 5px 8px !important;
    border: 1px solid #ffffff !important;
    border-radius: 0 !important;
    background: #000 !important;
    color: #ffffff !important;
    caret-color: #ffffff !important;
}
.agent-compose .form-control::placeholder {
    color: #ffffff !important;
    opacity: 0.75 !important;
}
.agent-compose .btn {
    background: #ff7f00 !important;
    border: 1px solid #ff7f00 !important;
    color: #fff !important;
    font-size: 0.72rem !important;
    padding: 5px 10px !important;
    border-radius: 0 !important;
}
.agent-compose #agent_clear {
    background: #000000 !important;
    border: 1px solid #ffffff !important;
    color: #ffffff !important;
}

/* Ranks section */
.ranks-section {
    padding: 16px 0 0;
    display: flex;
    flex-direction: column;
    max-height: calc(100vh - 96px);
    overflow: hidden;
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif;
    font-size: 0.72rem;
    background: #ffffff;
    border: none;
    border-radius: 0;
    margin: 0;
}
.ranks-section .ranks-scroll {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    padding: 0 4px 8px 14px;
}
.ranks-section .ranks-scroll::-webkit-scrollbar {
    width: 1px;
}
.ranks-section .ranks-scroll::-webkit-scrollbar-track {
    background: transparent;
}
.ranks-section .ranks-scroll::-webkit-scrollbar-thumb {
    background: #ff7f00;
    border-radius: 2px;
}
.ranks-section .ranks-scroll::-webkit-scrollbar-thumb:hover {
    background: #e56f00;
}
.ranks-section .ranks-scroll { scrollbar-width: thin; scrollbar-color: #ff7f00 transparent; }
.ranks-controls {
    display: flex;
    gap: 8px;
    margin-bottom: 20px;
    padding: 8px 8px 0 18px;
}
.ranks-controls .shiny-input-container {
    margin: 0 !important;
    flex: 1;
}
.ranks-section #zip_search {
    font-size: 0.72rem !important;
    padding: 5px 8px !important;
    border: 1px solid #000000 !important;
    border-radius: 0 !important;
    background: #000000 !important;
    color: #ffffff !important;
}
.ranks-section #zip_search::placeholder {
    color: #ffffff !important;
    opacity: 1 !important;
}
.ranks-section #zip_search:focus {
    border-color: #ff7f00 !important;
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(255,127,0,0.15) !important;
}
.ranks-section #rank_filter {
    font-size: 0.72rem !important;
    padding: 5px 6px !important;
    border: 1px solid #000000 !important;
    border-radius: 0 !important;
    background: #000000 !important;
    color: #ffffff !important;
}
.ranks-section #rank_filter:focus {
    border-color: #ff7f00 !important;
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(255,127,0,0.15) !important;
}
.leaderboard-zip:hover td {
    background: #ff7f00 !important;
    transition: background 0.15s;
}
.leaderboard-zip:hover td:first-child {
    border-radius: 6px 0 0 6px;
}
.leaderboard-zip:hover td:last-child {
    border-radius: 0 6px 6px 0;
}
.ranks-section table,
.ranks-section th,
.ranks-section td,
.ranks-section .leaderboard-zip {
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif !important;
}
.ranks-section .rank-score-cell {
    color: var(--score-color, #ffffff) !important;
    font-weight: 700 !important;
}

/* Hide the upload progress bar entirely */
.sidebar .progress {
    display: none !important;
}

/* File input styling */
.sidebar input[type="file"] {
    font-size: 0.75rem !important;
}
.sidebar input[type="file"]::file-selector-button {
    background: #ff7f00 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 4px;
    padding: 3px 8px;
    font-size: 0.7rem;
    cursor: pointer;
    transition: background 0.15s;
}
.sidebar input[type="file"]::file-selector-button:hover {
    background: #ff9b1a !important;
}

/* Shiny file input wrapper — styled browse button */
.sidebar .btn-file {
    background: #ff7f00 !important;
    color: #fff !important;
    border: none !important;
    border-radius: 6px !important;
    padding: 6px 16px !important;
    font-size: 0.72rem !important;
    font-weight: 600 !important;
    letter-spacing: 0.02em;
    transition: background 0.15s, box-shadow 0.15s;
    box-shadow: 0 1px 3px rgba(255,127,0,0.2);
}
.sidebar .btn-file:hover {
    background: #ff9b1a !important;
    box-shadow: 0 2px 6px rgba(255,127,0,0.3);
}
.sidebar .form-control[type="text"][readonly] {
    font-size: 0.72rem !important;
    padding: 5px 10px !important;
    background: #fff8f0 !important;
    border: 1px solid #ffe0b2 !important;
    border-radius: 6px !important;
    color: #1a1a1a !important;
}

/* Fixed divider between details and controls */
.sidebar-fixed-divider {
    border-color:#ffe0b2 !important;
    margin: 8px 0 !important;
    flex-shrink: 0;
}

/* Form controls */
.form-label { font-weight:400 !important; color:#1a1a1a !important; }

/* Selectbox */
.sidebar .form-select, .sidebar select {
    background:#ffffff !important;
    border:1px solid #ffe0b2 !important;
    color:#1a1a1a !important;
    border-radius:6px;
    font-size: 0.74rem !important;
    padding: 4px 8px !important;
    height: auto !important;
}

/* General dividers */
.sidebar hr { border-color:#ffe0b2 !important; }

/* Map iframe */
iframe { border-radius:0; }

/* Leaflet attribution */
.leaflet-control-attribution { display:none !important; }

/* ── Map chips bar (overlaid on map) ─────────────────────────── */
.map-chips-bar {
    position: absolute;
    top: 10px;
    left: 50%;
    transform: translateX(-50%);
    z-index: 1100;
    display: flex;
    align-items: center;
    gap: 4px;
    background: #000000;
    border-radius: 0;
    padding: 6px 8px;
    border: 2px solid #ffffff;
    white-space: nowrap;
    max-width: min(900px, calc(100vw - 52px));
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif;
}
.map-chips-count {
    font-size: 0.62rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    flex-shrink: 0;
    padding-top: 0;
    margin-right: 8px;
    padding-right: 8px;
    border-right: 1px solid #ffffff;
    color: #ffffff;
}
.map-chips-items {
    display: flex;
    flex-wrap: nowrap;
    gap: 4px;
    align-items: center;
    white-space: nowrap;
    overflow: hidden;
}
.map-chip {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    background: transparent;
    border: none;
    border-radius: 0;
    padding: 0 2px;
    font-size: 0.58rem;
    font-weight: 600;
    color: #ffffff;
    cursor: default;
    transition: background 0.15s, border-color 0.15s;
    flex-shrink: 0;
}
.map-chip:hover {
    background: transparent;
    border-color: transparent;
}
.market-zip-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    margin-left: 8px;
    margin-right: 0;
    font-size: 0.72rem;
    line-height: 1;
    color: #ffffff !important;
    cursor: pointer;
    border-radius: 0;
}
.market-zip-remove:hover {
    background: transparent !important;
    color: #ffffff !important;
}

.market-section .market-projection-title {
    color: #ff7f00 !important;
}

.market-section .market-score-value {
    color: var(--ms-color, #ffffff) !important;
}

@media (max-width: 1200px) {
    .map-chips-items { gap: 4px; }
}

/* ── Market tab ─────────────────────────────────────────────── */
.market-section {
    overflow-y: auto;
    padding: 16px 12px 12px 18px;
    scrollbar-width: thin;
    scrollbar-color: #ff7f00 transparent;
    background: #ffffff;
    border: none;
    border-radius: 0;
    margin: 0;
    max-height: calc(100vh - 96px);
}
.market-section:has(.market-empty-msg) {
    background: transparent;
    border: none;
    margin: 0;
    padding: 12px 0 0 10px;
    max-height: none;
}
.market-section::-webkit-scrollbar { width: 1px; }
.market-section::-webkit-scrollbar-track { background: transparent; }
.market-section::-webkit-scrollbar-thumb { background: #ff7f00; border-radius: 2px; }
.market-section::-webkit-scrollbar-thumb:hover { background: #e56f00; }
.market-section { scrollbar-color: #ff7f00 transparent; }

/* Avg score — clickable details block */
.market-detail-block {
    background: #ffffff;
    border: none;
    border-radius: 6px;
    margin-bottom: 22px;
    overflow: hidden;
}
.market-detail-content {
    border-top: 1px solid #ffe0b2;
    padding: 6px 10px;
}

/* ZIP list */
.market-zip-list {
    list-style: none;
    padding: 0;
    margin: 0;
    display: flex;
    flex-direction: column;
    gap: 6px;
}
.market-zip-item {
    background: #ffffff;
    border: 1px solid #ffe0b2;
    border-radius: 0;
    overflow: hidden;
}

/* Each ZIP — clickable details */
.zip-detail-toggle {
    width: 100%;
}
.zip-detail-summary {
    display: flex;
    align-items: center;
    padding: 6px 8px;
    cursor: pointer;
    list-style: none;
    transition: background 0.15s;
}
.zip-detail-summary::-webkit-details-marker { display: none; }
.zip-detail-summary:hover { background: #fff8f0; }
.zip-detail-content {
    border-top: 1px solid #ffe0b2;
    padding: 6px 10px;
}

/* ── Tier dropdowns (inside market container) ────────────────── */
.tier-dropdown {
    border-top: 1px solid #ffe0b2;
    overflow: hidden;
}
.tier-dropdown-summary {
    display: flex;
    align-items: center;
    padding: 7px 10px;
    cursor: pointer;
    list-style: none;
    font-size: 0.7rem;
    font-weight: 600;
    color: #1a1a1a;
    letter-spacing: 0.01em;
    transition: background 0.15s;
}
.tier-dropdown-summary::-webkit-details-marker { display: none; }
.tier-dropdown-summary::before {
    content: '\\25B6';
    font-size: 0.45rem;
    margin-right: 8px;
    color: #1a1a1a;
    transition: transform 0.15s;
}
.tier-dropdown[open] > .tier-dropdown-summary::before {
    transform: rotate(90deg);
}
.tier-dropdown-summary:hover { background: #fff0d4; }
.definitions-section .tier-dropdown {
    border-top-color: #ff7f00;
}
.definitions-section .tier-dropdown-summary::before {
    color: #ffffff;
}
.definitions-section .tier-dropdown-summary {
    color: #ffffff !important;
}
.definitions-section .tier-dropdown-summary:hover {
    background: #ff7f00;
    color: #ffffff;
}
.definitions-section .tier-dropdown-summary:hover::before {
    color: #ffffff;
}
.market-section .tier-dropdown-summary::before {
    color: #ffffff !important;
}
.tier-dropdown-content {
    padding: 4px 10px 6px;
}

/* ── Forced dark dashboard theme (user preference) ───────────────────── */
.bslib-sidebar-layout > .sidebar,
.sidebar .tab-content,
.definitions-section,
.ranks-section,
.market-section,
.settings-section,
.settings-shell,
.agent-shell {
    background: #000000 !important;
    color: #ffffff !important;
}

.sidebar h5,
.sidebar label,
.sidebar .control-label,
.sidebar,
.def-title,
.def-title-lg,
.def-body,
.def-subtitle,
.def-note,
.settings-title,
.settings-note,
.agent-title,
.agent-msg-text,
.agent-msg-label,
.ranks-section,
.ranks-section table,
.ranks-section th,
.ranks-section td,
.market-section,
.market-section * {
    color: #ffffff !important;
}

/* Catch inline black text styles that become unreadable on black tabs */
.definitions-section [style*="color:#1a1a1a"],
.definitions-section [style*="color: #1a1a1a"],
.definitions-section [style*="color:#000000"],
.definitions-section [style*="color: #000000"],
.ranks-section [style*="color:#1a1a1a"],
.ranks-section [style*="color: #1a1a1a"],
.ranks-section [style*="color:#000000"],
.ranks-section [style*="color: #000000"],
.settings-section [style*="color:#1a1a1a"],
.settings-section [style*="color: #1a1a1a"],
.settings-section [style*="color:#000000"],
.settings-section [style*="color: #000000"],
.agent-shell [style*="color:#1a1a1a"],
.agent-shell [style*="color: #1a1a1a"],
.agent-shell [style*="color:#000000"],
.agent-shell [style*="color: #000000"],
.market-section [style*="color:#1a1a1a"],
.market-section [style*="color: #1a1a1a"],
.market-section [style*="color:#000000"],
.market-section [style*="color: #000000"] {
    color: #ffffff !important;
}

/* White separators/dividers across dashboard */
.sidebar hr,
.sidebar-fixed-divider,
.def-section-divider,
.definitions-section hr.def-section-divider,
.tier-dropdown,
.tier-dropdown-summary,
.tier-dropdown-content,
.settings-dim-card,
.settings-dim-dropdown,
.settings-note,
.agent-thread-wrap,
.agent-msg,
.market-zip-item,
.zip-detail-content,
.market-detail-content,
.def-score-block,
.def-formula,
.def-ui-banner,
.ranks-section #zip_search,
.ranks-section #rank_filter,
.sidebar .form-select,
.sidebar select,
.sidebar .form-control {
    border-color: #ffffff !important;
}

.def-formula,
.def-ui-banner,
.def-score-block,
.agent-thread-wrap,
.agent-msg,
.settings-dim-card,
.settings-note,
.ranks-section #zip_search,
.ranks-section #rank_filter,
.sidebar .form-select,
.sidebar select,
.sidebar .form-control {
    background: #000000 !important;
}

/* Ensure dark surfaces in myMarket and ZIP List content blocks */
.market-detail-block,
.market-detail-content,
.market-zip-item,
.zip-detail-summary,
.zip-detail-content,
.tier-dropdown-content,
.tier-dropdown-summary,
.market-zip-list,
.ranks-section table,
.ranks-section thead,
.ranks-section tbody,
.ranks-section tr,
.ranks-section td,
.ranks-section th {
    background: #000000 !important;
}

.zip-detail-summary:hover,
.tier-dropdown-summary:hover {
    background: #111111 !important;
}

.leaderboard-zip:hover td {
    background: #1a1a1a !important;
}

/* White scrollbars in dark mode */
.bslib-sidebar-layout > .sidebar > .sidebar-content,
.definitions-section,
.settings-section,
.agent-thread-wrap,
.ranks-section .ranks-scroll,
.market-section {
    scrollbar-color: #ffffff transparent !important;
}
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar-thumb,
.definitions-section::-webkit-scrollbar-thumb,
.settings-section::-webkit-scrollbar-thumb,
.agent-thread-wrap::-webkit-scrollbar-thumb,
.ranks-section .ranks-scroll::-webkit-scrollbar-thumb,
.market-section::-webkit-scrollbar-thumb {
    background: #ffffff !important;
}

/* Final myAgent visual overrides (after dark-theme block) */
.agent-msg-label,
.agent-msg-assistant .agent-msg-text,
.agent-context,
.agent-context span {
    color: #ffffff !important;
}
.agent-title {
    color: #ff7f00 !important;
}
.agent-msg-user {
    background: #ff7f00 !important;
    border: none !important;
}
.agent-msg,
.agent-msg-user,
.agent-msg-assistant {
    border-radius: 0 !important;
}
.agent-msg-user .agent-msg-label,
.agent-msg-user .agent-msg-text {
    color: #ffffff !important;
}

/* Settings: single-select option pills (Option 1/2/4) */
.settings-score-option-wrap .shiny-input-radiogroup {
    margin: 0 0 12px 0 !important;
}
.settings-score-option-wrap .control-label {
    color: #ffffff !important;
    font-size: 0.72rem !important;
}
.settings-score-option-wrap .radio-inline,
.settings-score-option-wrap .form-check-label {
    color: #ffffff !important;
    margin-right: 16px !important;
    font-size: 0.72rem !important;
}
.settings-score-option-wrap .form-check-input,
.settings-score-option-wrap input[type="radio"] {
    accent-color: #ff7f00 !important;
    appearance: none !important;
    -webkit-appearance: none !important;
    width: 14px !important;
    height: 14px !important;
    border: 1px solid #ff7f00 !important;
    border-radius: 0 !important;
    background: #000000 !important;
    display: inline-grid !important;
    place-content: center !important;
    margin-right: 6px !important;
    vertical-align: middle !important;
}
.settings-score-option-wrap .form-check-input::before,
.settings-score-option-wrap input[type="radio"]::before {
    content: "" !important;
    width: 8px !important;
    height: 8px !important;
    transform: scale(0) !important;
    transition: transform 120ms ease-in-out !important;
    background: #ff7f00 !important;
}
.settings-score-option-wrap input[type="radio"]:checked + label,
.settings-score-option-wrap .form-check-input:checked + .form-check-label {
    color: #ff7f00 !important;
}
.settings-score-option-wrap .form-check-input:checked,
.settings-score-option-wrap input[type="radio"]:checked {
    border-color: #ff7f00 !important;
    background: #000000 !important;
}
.settings-score-option-wrap .form-check-input:checked::before,
.settings-score-option-wrap input[type="radio"]:checked::before {
    transform: scale(1) !important;
}
.settings-score-option-wrap .btn-check:checked + .btn,
.settings-score-option-wrap .btn.active,
.settings-score-option-wrap .btn:active {
    background: #ff7f00 !important;
    border-color: #ff7f00 !important;
    color: #ffffff !important;
}
.settings-score-option-wrap .btn {
    border-radius: 0 !important;
    background: #000000 !important;
    border: 1px solid #ffffff !important;
    color: #ffffff !important;
}
.settings-option-info {
    border-radius: 0 !important;
    border: 1px solid #ffffff !important;
    background: #000000 !important;
}
.settings-tier-dropdown {
    margin-top: 8px;
    border: 1px solid #ffffff;
    border-radius: 0;
    background: #000000;
}
.settings-tier-summary {
    list-style: none;
    cursor: pointer;
    padding: 6px 8px;
    color: #ffffff;
    font-size: 0.72rem;
    border-radius: 0;
}
.settings-tier-summary::-webkit-details-marker { display: none; }
.settings-tier-summary::before {
    content: "▸";
    color: #ffffff;
    margin-right: 6px;
}
.settings-tier-dropdown[open] > .settings-tier-summary::before {
    content: "▾";
}
.settings-tier-details-body {
    border-top: none;
    padding: 8px 10px 12px;
    border-radius: 0;
}
.settings-tier-details-body > * {
    margin-left: 4px;
    margin-right: 4px;
}
.settings-tier-details-body .settings-note {
    border-radius: 0 !important;
    background: transparent !important;
    border: none !important;
    color: #ffffff !important;
    padding: 2px 0 !important;
}
.settings-tier-component-card {
    border: none !important;
    border-radius: 0 !important;
    background: transparent !important;
    padding: 2px 0 !important;
    margin-bottom: 8px;
}
.settings-dim-card {
    border: none !important;
    background: transparent !important;
    padding: 0 !important;
    margin: 0 !important;
}
.settings-dim-card .settings-tier-dropdown {
    margin: 0 !important;
}
.settings-option-info {
    border: none !important;
    background: transparent !important;
    padding: 2px 0 !important;
}
.settings-option-stack {
    border: 1px solid #ffffff !important;
    border-radius: 0 !important;
    background: #000000 !important;
    padding: 8px 10px 6px !important;
    margin-bottom: 12px !important;
}
.settings-option-stack .settings-option-info {
    margin-bottom: 12px !important;
}
.settings-option-stack .settings-option-formula {
    margin-bottom: 10px !important;
    color: #ffffff !important;
}
.settings-equation {
    font-family: "Segoe UI", "Open Sans", Arial, sans-serif !important;
    line-height: 1.35 !important;
}
.settings-equation-line {
    margin: 2px 0 !important;
}
.settings-tier-component-card .control-label,
.settings-tier-component-card .form-label,
.settings-tier-component-card label {
    margin-bottom: 2px !important;
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif !important;
    font-size: 0.68rem !important;
    font-weight: 600 !important;
    color: #ffffff !important;
}
.settings-tier-component-card .irs--shiny {
    margin-top: -6px !important;
    margin-bottom: -2px !important;
}
.settings-tier-component-card .irs--shiny .irs-single,
.settings-tier-component-card .irs--shiny .irs-from,
.settings-tier-component-card .irs--shiny .irs-to {
    font-size: 0.66rem !important;
    top: 1px !important;
    z-index: 3 !important;
}
.settings-tier-component-card .irs--shiny .irs-from,
.settings-tier-component-card .irs--shiny .irs-to {
    display: none !important;
}
.settings-tier-component-card div,
.settings-tier-component-card span,
.settings-tier-component-card b {
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif !important;
    font-size: 0.68rem !important;
}
.settings-construct-section {
    border-top: 1px solid #ffffff;
    padding-top: 18px;
    margin-top: 22px;
    margin-bottom: 18px;
}
.settings-construct-section .settings-construct-mini-title {
    margin-bottom: 10px;
}
.settings-construct-section .settings-tier-dropdown {
    margin-top: 0 !important;
}
.settings-construct-section .settings-tier-details-body {
    /* Keep compact layout but avoid edge-clipping */
    padding-left: 8px !important;
    padding-right: 8px !important;
}
.settings-construct-section .settings-tier-details-body > * {
    margin-left: 2px !important;
    margin-right: 2px !important;
}
.settings-tier-empty-body {
    min-height: 26px;
}
.settings-weights-feedback {
    margin: 2px 0 8px !important;
    border-radius: 0 !important;
    border: 1px solid #ff7f00 !important;
    background: #000000 !important;
    color: #ff7f00 !important;
}
.agent-compose .form-control {
    background: #000000 !important;
    color: #ffffff !important;
    caret-color: #ffffff !important;
}
.agent-compose .form-control::placeholder {
    color: #ffffff !important;
    opacity: 0.75 !important;
}

/* Definitions tab: make all titles active-header orange */
.definitions-section .def-title,
.definitions-section .def-title-lg,
.definitions-section .def-subtitle,
.definitions-section .def-score-title,
.definitions-section .def-ui-banner-title {
    color: #ff7f00 !important;
}

/* Sub-construct tier titles should be white */
.definitions-section .tier-dropdown-summary {
    color: #ffffff !important;
}

/* Score UI titles should be white */
.definitions-section .def-card-formula .def-ui-banner-title {
    color: #ffffff !important;
}

/* Market score UI should be blocky with no white border */
.definitions-section .def-card-formula .def-ui-banner {
    border: none !important;
    border-radius: 0 !important;
    background: #000000 !important;
    box-shadow: none !important;
}

/* References -> Construct Score spacing */
.def-construct-score-group {
    margin-bottom: 20px;
    border: 1px solid #ffffff;
    border-radius: 0;
    padding: 10px 12px;
    background: #000000;
}
.def-construct-score-group:last-child {
    margin-bottom: 0;
}
.def-construct-score-group .def-dim {
    margin-bottom: 8px;
}
.def-construct-score-group .def-formula-row {
    margin-bottom: 8px;
}
.def-construct-score-group .def-construct-tier-line {
    margin-bottom: 8px;
    font-size: 0.72rem;
    line-height: 1.4;
}

/* Keep Settings title as active orange in dark-theme global overrides */
.settings-section .settings-title,
.settings-shell .settings-title {
    color: #ff7f00 !important;
}

/* Fade-out animation for notifications */
@keyframes fadeOut {
    from { opacity:1; }
    to   { opacity:0; height:0; margin:0; padding:0; border:none; overflow:hidden; }
}
"""
