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
$(document).on('click', '.chip-remove', function() {
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

/* Sidebar — slightly darker orange background, wider layout */
.bslib-sidebar-layout > .sidebar {
    background:#ffe9cf !important;
    border-right:3px solid #ffcf99 !important;
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
    scrollbar-color: #e0d0c0 transparent;
}
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar { width: 4px; }
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar-track { background: transparent; }
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar-thumb { background: #e0d0c0; border-radius: 2px; }
.bslib-sidebar-layout > .sidebar > .sidebar-content::-webkit-scrollbar-thumb:hover { background: #cbb8a0; }

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
    color: #1a1a1a !important;
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
    border-bottom-color: #ffd699 !important;
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
    background: #ffe9cf !important;
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
    background: #ffe9cf;
}

/* Definitions section */
.definitions-section {
    padding: 16px 12px 8px 22px;
    overflow-y: auto;
    max-height: calc(100vh - 96px);
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif;
    background: #ffffff;
    border: 1px solid #ffe0b2;
    border-radius: 10px;
    margin: 8px;
}
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
    font-size: 0.98rem;
    font-weight: 700;
    color: #1a1a1a;
    margin-bottom: 22px;
}
.def-title-lg {
    font-size: 0.98rem;
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
.def-dim {
    margin-bottom: 14px;
}
.def-dim:last-child {
    margin-bottom: 6px;
}
.definitions-section .def-body b {
    text-decoration: underline;
    text-underline-offset: 2px;
}
.def-formula {
    border: 1px solid #ffcf99;
    border-radius: 8px;
    background: #ffe9cf;
    padding: 8px 10px;
    margin-bottom: 8px;
}
.def-card .def-formula {
    margin-top: 10px;
    margin-bottom: 12px;
}
.def-formula-eq {
    font-size: 0.72rem;
    font-weight: 700;
    color: #1f2937;
    margin-bottom: 6px;
}
.def-formula-row {
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 0.72rem;
    color: #1a1a1a;
    margin-bottom: 4px;
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
.def-ui-banner {
    border: 1px solid #ffcf99;
    border-radius: 8px;
    background: #ffe9cf;
    padding: 8px 10px;
    margin-bottom: 8px;
    font-family: inherit;
}
.def-card .def-ui-banner {
    margin-top: 10px;
    margin-bottom: 12px;
}
.def-card-formula .def-formula {
    margin-top: 20px;
    margin-bottom: 26px;
    padding-top: 12px;
    padding-bottom: 12px;
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
    border: 2px solid #ffcf99;
    border-radius: 4px;
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
    background: #ffe9cf;
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
    border: 1px solid #ffe0b2;
    border-radius: 10px;
    margin: 8px;
}
.ranks-section .ranks-scroll {
    flex: 1;
    overflow-y: auto;
    min-height: 0;
    padding: 0 4px 8px 14px;
}
.ranks-section .ranks-scroll::-webkit-scrollbar {
    width: 4px;
}
.ranks-section .ranks-scroll::-webkit-scrollbar-track {
    background: transparent;
}
.ranks-section .ranks-scroll::-webkit-scrollbar-thumb {
    background: #e0d0c0;
    border-radius: 2px;
}
.ranks-section .ranks-scroll::-webkit-scrollbar-thumb:hover {
    background: #cbb8a0;
}
.ranks-section .ranks-scroll { scrollbar-width: thin; scrollbar-color: #e0d0c0 transparent; }
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
    border: 1px solid #ffe0b2 !important;
    border-radius: 6px !important;
    background: #fff !important;
    color: #1a1a1a !important;
}
.ranks-section #zip_search::placeholder {
    color: #1a1a1a !important;
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
    border: 1px solid #ffe0b2 !important;
    border-radius: 6px !important;
    background: #fff !important;
    color: #1a1a1a !important;
}
.ranks-section #rank_filter:focus {
    border-color: #ff7f00 !important;
    outline: none !important;
    box-shadow: 0 0 0 2px rgba(255,127,0,0.15) !important;
}
.leaderboard-zip:hover td {
    background: #fff0d4 !important;
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
    align-items: flex-start;
    gap: 10px;
    background: #ffe9cf;
    border-radius: 8px;
    padding: 8px 14px;
    border: 2px solid #ffcf99;
    white-space: normal;
    max-width: min(960px, calc(100vw - 110px));
    font-family: "Open Sans", "Segoe UI", Tahoma, Arial, sans-serif;
}
.map-chips-count {
    font-size: 0.76rem;
    font-weight: 600;
    letter-spacing: 0.03em;
    flex-shrink: 0;
    padding-top: 3px;
}
.map-chips-items {
    display: grid;
    grid-template-columns: repeat(5, max-content);
    gap: 6px 8px;
    align-items: center;
}
.map-chip {
    display: inline-flex;
    align-items: center;
    gap: 2px;
    background: #ff7f00;
    border: 1px solid #ff7f00;
    border-radius: 12px;
    padding: 3px 9px;
    font-size: 0.68rem;
    font-weight: 600;
    color: #fff;
    cursor: default;
    transition: background 0.15s, border-color 0.15s;
    flex-shrink: 0;
}
.map-chip:hover {
    background: #ff9b1a;
    border-color: #ff9b1a;
}
.map-chip .chip-remove {
    display: inline-flex;
    align-items: center;
    justify-content: center;
    width: 16px;
    height: 16px;
    border-radius: 50%;
    font-size: 0.55rem;
    color: #fff;
    cursor: pointer;
    transition: background 0.15s, color 0.15s;
}
.map-chip .chip-remove:hover {
    background: #ffd8ac;
    color: #fff;
}

@media (max-width: 1200px) {
    .map-chips-items { grid-template-columns: repeat(4, max-content); }
}

/* ── Market tab ─────────────────────────────────────────────── */
.market-section {
    overflow-y: auto;
    padding: 16px 12px 12px 22px;
    scrollbar-width: thin;
    scrollbar-color: #e0d0c0 transparent;
    background: #ffffff;
    border: 1px solid #ffe0b2;
    border-radius: 10px;
    margin: 8px;
    max-height: calc(100vh - 96px);
}
.market-section:has(.market-empty-msg) {
    background: transparent;
    border: none;
    margin: 0;
    padding: 12px 0 0 10px;
    max-height: none;
}
.market-section::-webkit-scrollbar { width: 4px; }
.market-section::-webkit-scrollbar-track { background: transparent; }
.market-section::-webkit-scrollbar-thumb { background: #e0d0c0; border-radius: 2px; }
.market-section::-webkit-scrollbar-thumb:hover { background: #cbb8a0; }

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
    border-radius: 6px;
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
.tier-dropdown-content {
    padding: 4px 10px 6px;
}

/* Fade-out animation for notifications */
@keyframes fadeOut {
    from { opacity:1; }
    to   { opacity:0; height:0; margin:0; padding:0; border:none; overflow:hidden; }
}
"""
