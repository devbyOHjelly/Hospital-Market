"""Hospital Market — Dash UI.

Run from repository root::

    python frontend/dash_app.py

Uses ``PORT`` or ``HM_PORT`` (default 8050) and ``FLASK_DEBUG`` (1/true/yes) like a typical Flask/Dash app.
"""

from __future__ import annotations

import html as html_lib
import json
import os
import re
import sys
from copy import deepcopy
from typing import Any

import pandas as pd
from dash import Dash, Input, Output, State, callback, ctx, html, no_update
from dash.exceptions import PreventUpdate
import dash.dcc as dcc
from flask import send_from_directory

_FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_FRONTEND_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from backend.agent.agent_config import DEFAULT_SCORE_COLUMN
from frontend.config import WWW_DIR, score_fill_color, score_legend_gradient_css, ui_chrome_background
from frontend.modules.agent_chat import run_agent_turn
from frontend.modules.dashboard import MAX_SELECTED, market_tab_html, normalize_zip
from frontend.modules.data.loader import ENTITIES_DF, gdf as initial_gdf
from frontend.modules.definitions_html import build_definitions_html, wrap_definitions_srcdoc
from frontend.modules.dash_css import get_dash_css
from frontend.modules.map.builder import build_map
from frontend.modules.scoring_core import (
    DIMENSION_META,
    SCORE_OPTION_CHOICES,
    apply_settings_weights,
    default_construct_component_weights,
    default_weight_state,
)

_STATE_TO_ABBR = {"Alabama": "AL", "Florida": "FL", "Georgia": "GA"}
MAP_PREFIX = "/hm_map_assets"
OPT2 = "attractiveness_score_opt2"

# Dash 2.18 RadioItems: each option is `<label><input /> text</label>` (no .form-check-label).
_SETTINGS_SCORE_OPTION_LABEL_STYLE: dict[str, str | int] = {
    "fontSize": "0.62rem",
    "fontWeight": "600",
    "lineHeight": "1.3",
    "color": "#ffffff",
    "marginRight": "14px",
    "cursor": "pointer",
}


def _construct_slider_id(dim: str, indicator: str) -> str:
    return f"w_c_{OPT2}_{dim}_{indicator}"


def _opt2_slider_specs() -> list[tuple[str, str, str, float]]:
    """Order matches approve callback (dimension order × indicators)."""
    d = default_construct_component_weights()[OPT2]
    out: list[tuple[str, str, str, float]] = []
    for dim, _label in DIMENSION_META:
        for ind, v in d.get(dim, {}).items():
            out.append((_construct_slider_id(dim, ind), dim, ind, float(v)))
    return out


OPT2_SLIDER_SPECS = _opt2_slider_specs()

_SLIDER_DISABLED_OUTPUTS = [Output(sid, "disabled") for sid, _, _, _ in OPT2_SLIDER_SPECS]


def _tier_placeholder_body(text: str) -> html.Div:
    return html.Div(
        html.Div(text, className="settings-note hm-settings-note"),
        className="settings-tier-details-body settings-tier-empty-body",
    )


def _build_construct_weights_panel() -> html.Div:
    """Four constructs, each with Tier 1/2/3 disclosures; Tier 1 holds indicator sliders (Tier 2–3 TBD)."""
    d = default_construct_component_weights()[OPT2]
    groups: list[Any] = []
    for dim, label in DIMENSION_META:
        block = d.get(dim, {})
        cards: list[Any] = []
        for ind, v in block.items():
            sid = _construct_slider_id(dim, ind)
            cards.append(
                html.Div(
                    [
                        dcc.Slider(
                            id=sid,
                            min=0,
                            max=100,
                            step=1,
                            value=int(round(float(v))),
                            marks={0: "0", 50: "50", 100: "100"},
                            tooltip={"placement": "bottom"},
                            className="hm-weight-slider",
                        ),
                        html.Div(
                            ind.replace("_", " ").title(),
                            className="settings-note hm-settings-note",
                            style={"marginTop": 4},
                        ),
                    ],
                    className="settings-tier-component-card",
                )
            )
        tier1_body = (
            html.Div(cards, className="settings-tier-details-body")
            if cards
            else _tier_placeholder_body("No indicators for this construct.")
        )
        groups.append(
            html.Div(
                [
                    html.Div(label, className="settings-construct-mini-title"),
                    html.Details(
                        [
                            html.Summary(
                                "Tier 1",
                                className="settings-tier-summary settings-tier-summary--construct",
                            ),
                            tier1_body,
                        ],
                        open=False,
                        className="settings-tier-dropdown hm-construct-tier settings-tier-dropdown--in-construct",
                    ),
                    html.Details(
                        [
                            html.Summary(
                                "Tier 2",
                                className="settings-tier-summary settings-tier-summary--construct",
                            ),
                            _tier_placeholder_body("Not available yet."),
                        ],
                        open=False,
                        className="settings-tier-dropdown hm-construct-tier settings-tier-dropdown--in-construct",
                    ),
                    html.Details(
                        [
                            html.Summary(
                                "Tier 3",
                                className="settings-tier-summary settings-tier-summary--construct",
                            ),
                            _tier_placeholder_body("Not available yet."),
                        ],
                        open=False,
                        className="settings-tier-dropdown hm-construct-tier settings-tier-dropdown--in-construct",
                    ),
                ],
                className="settings-construct-group settings-construct-group--tiered",
            )
        )
    return html.Div(groups, className="settings-construct-section hm-construct-weights")

app = Dash(__name__, assets_folder="assets", suppress_callback_exceptions=True)
server = app.server


@server.route(f"{MAP_PREFIX}/<path:fname>")
def _serve_map_assets(fname: str):
    return send_from_directory(str(WWW_DIR), fname)


_css_injected = get_dash_css()
app.index_string = app.index_string.replace(
    "{%css%}",
    "{%css%}<style>" + _css_injected + "</style>",
    1,
).replace(
    "<body>",
    f'<body style="margin:0;padding:0;height:100vh;overflow:hidden;background:{ui_chrome_background()};">',
    1,
)


def _install_map_postmessage_bridge():
    """After renderer loads, wire iframe postMessage → Stores (avoids race with static assets)."""
    app.clientside_callback(
        """
        function(children) {
            if (!window.__hmPostMessageBridge) {
            window.__hmPostMessageBridge = true;
            function sp(id, props) {
                try {
                    var dc = window.dash_clientside;
                    if (dc && typeof dc.set_props === "function") {
                        dc.set_props(id, props);
                    }
                } catch (e) {
                    console.warn("hm map bridge", e);
                }
            }
            window.addEventListener("message", function(event) {
                if (!event.data || !event.data.type) return;
                if (event.data.type === "zip_click") {
                    sp("bridge-map-click", { data: event.data });
                }
                if (event.data.type === "opacity_save") {
                    sp("bridge-map-opacity", { data: event.data.value });
                }
                if (event.data.type === "state_change") {
                    sp("bridge-map-state", { data: event.data.state });
                }
                if (event.data.type === "blink_ack") {
                    window._focusBlinkDone = true;
                }
            });
            }
            return 1;
        }
        """,
        Output("_bridge-boot", "data"),
        Input("map-slot", "children"),
        prevent_initial_call=False,
    )


_install_map_postmessage_bridge()


def _map_opacity_slider_value(op: Any) -> int:
    try:
        x = float(op if op is not None else 1.0)
    except (TypeError, ValueError):
        x = 1.0
    x = max(0.0, min(1.0, x))
    return int(round(x * 100))


def _map_refresh_is_selection_only() -> bool:
    """ZIP pick/limit updates Stores only — avoid iframe reload (map visuals stay in the iframe)."""
    trig = getattr(ctx, "triggered", None) or []
    if not trig:
        return False
    allowed = {"selected-zips", "zip-limit-msg"}
    seen: list[str] = []
    for t in trig:
        pid = str(t.get("prop_id") or "")
        if pid == ".":
            return False
        seen.append(pid.split(".")[0])
    return bool(seen) and all(x in allowed for x in seen)


def _refresh_is_zip_search_only() -> bool:
    """Leaderboard filter only — skip map iframe, definitions iframe, and other heavy outputs."""
    tid = getattr(ctx, "triggered_id", None)
    if tid == "zip-search":
        return True
    trig = getattr(ctx, "triggered", None) or []
    if len(trig) != 1:
        return False
    pid = str(trig[0].get("prop_id") or "")
    return pid.startswith("zip-search")


def _refresh_is_focus_zip_only() -> bool:
    """Leaderboard / map navigation to a ZIP — dash_bridge posts focus_blink; do not reload map iframe."""
    tid = getattr(ctx, "triggered_id", None)
    if tid != "focus-zip":
        return False
    trig = getattr(ctx, "triggered", None) or []
    return len(trig) == 1


def _skip_map_rebuild_for_zip_focus_nav() -> bool:
    """Leaderboard click sets `focus-zip` and often `state-current` together; iframe handles focus via postMessage.

    Rebuilding `map-slot` wipes the iframe and loses zoom — skip iframe when only focus/state/selection
    side-effects fire, not weights, map version, filters, or agent.
    """
    trig = getattr(ctx, "triggered", None) or []
    ids: set[str] = set()
    for t in trig:
        pid = str(t.get("prop_id") or "")
        if not pid or pid == ".":
            continue
        ids.add(pid.split(".")[0])
    ids.discard(".")
    if "focus-zip" not in ids:
        return False
    heavy = {
        "weight-store",
        "map-version",
        "zip-search",
        "settings-show-market",
        "settings-show-entities",
        "agent-messages",
    }
    return not bool(ids & heavy)


def _map_slot_has_iframe(map_children: Any) -> bool:
    """First layout pass leaves `map-slot` empty; never skip map output until iframe is mounted."""
    if map_children is None:
        return False
    if isinstance(map_children, list):
        return len(map_children) > 0
    if isinstance(map_children, dict):
        return bool(map_children)
    return bool(map_children)


app.clientside_callback(
    """
    function(v) {
        var iframe = document.getElementById("map_frame");
        if (iframe && iframe.contentWindow && v != null && v !== undefined) {
            iframe.contentWindow.postMessage({type: "hm_set_opacity", value: v / 100}, "*");
        }
        return window.dash_clientside.no_update;
    }
    """,
    Output("_noop-clientside", "data"),
    Input("map-opacity-slider", "value"),
)


def _weight_store_key(w: dict[str, Any] | None) -> tuple[Any, ...]:
    w = w or _w0
    return (
        str(w.get("approved_score_option") or ""),
        json.dumps(w.get("approved_option_component_weights") or {}, sort_keys=True, default=str),
        json.dumps(w.get("approved_construct_component_weights") or {}, sort_keys=True, default=str),
        json.dumps(w.get("approved_tier_weights") or {}, sort_keys=True, default=str),
    )


_GDF_CACHE: dict[tuple[Any, ...], pd.DataFrame] = {}
_GDF_CACHE_ORDER: list[tuple[Any, ...]] = []
_GDF_CACHE_MAX = 8


def _compute_gdf(w: dict[str, Any]) -> pd.DataFrame:
    key = _weight_store_key(w)
    hit = _GDF_CACHE.get(key)
    if hit is not None:
        return hit
    data = initial_gdf.copy()
    if "hospital_potential" not in data.columns:
        data["hospital_potential"] = 0.0
    out = apply_settings_weights(
        data,
        approved_option_component_weights=w["approved_option_component_weights"],
        approved_construct_component_weights=w["approved_construct_component_weights"],
        approved_score_option=str(w["approved_score_option"]),
        approved_tier_weights=w["approved_tier_weights"],
    )
    _GDF_CACHE[key] = out
    _GDF_CACHE_ORDER.append(key)
    while len(_GDF_CACHE_ORDER) > _GDF_CACHE_MAX:
        old = _GDF_CACHE_ORDER.pop(0)
        _GDF_CACHE.pop(old, None)
    return out


def _state_list(gdf: pd.DataFrame) -> list[str]:
    return sorted(gdf["state"].dropna().unique().tolist())


def _leaderboard_content(gdf: pd.DataFrame, state_val: str | None, zip_query: str):
    """Native Dash table so score colors are real CSS (dcc.Markdown strips inline styles)."""
    empty_p = {"color": "#c8c8c8", "fontSize": "0.8rem", "textAlign": "center"}
    if gdf is None or len(gdf) == 0:
        return html.P("No data available.", style=empty_p)
    ranked = gdf[["zipcode", "state", "hospital_potential"]].copy()
    ranked["zip_key"] = ranked["zipcode"].map(normalize_zip)
    ranked["hospital_potential"] = pd.to_numeric(ranked.get("hospital_potential"), errors="coerce").fillna(0.0)
    if state_val:
        ranked = ranked[ranked["state"] == state_val]
    ranked = ranked.sort_values("hospital_potential", ascending=False).reset_index(drop=True)
    ranked["rank"] = ranked.index + 1
    query = (zip_query or "").strip()
    if query:
        ranked = ranked[ranked["zip_key"].str.startswith(query)]
    ranked = ranked.sort_values("hospital_potential", ascending=False).reset_index(drop=True)
    if len(ranked) == 0:
        msg = f'No ZIP codes matching "{query}"' if query else "No scored ZIP codes for this filter."
        return html.P(msg, style=empty_p)

    th_bg = {"background": "#000000"}
    th_common = {
        **th_bg,
        "color": "#ffffff",
        "fontWeight": 600,
        "fontSize": "0.72rem",
        "borderBottom": "1px solid #ffffff",
        "padding": "4px 10px",
    }
    thead = html.Thead(
        html.Tr(
            [
                html.Th("#", style={**th_common, "textAlign": "center"}),
                html.Th("ZIP", style={**th_common, "textAlign": "left"}),
                html.Th("State", style={**th_common, "textAlign": "left"}),
                html.Th(
                    "Market Score",
                    style={**th_common, "textAlign": "right", "padding": "4px 25px 4px 10px"},
                ),
            ],
            style={"position": "sticky", "top": 0, "zIndex": 2},
        )
    )
    badge_style = {
        "display": "inline-flex",
        "alignItems": "center",
        "justifyContent": "center",
        "width": "22px",
        "height": "22px",
        "borderRadius": "50%",
        "background": "#000000",
        "border": "1px solid #ffffff",
        "color": "#ffffff",
        "fontSize": "0.6rem",
        "fontWeight": 700,
    }
    rows: list[html.Tr] = []
    for disp_i, (_, row) in enumerate(ranked.iterrows()):
        rank = int(row["rank"])
        zc = str(row["zip_key"])
        st = str(row["state"])
        score = float(row["hospital_potential"])
        score_color = score_fill_color(score)
        border_top = "1px solid #ffffff" if disp_i > 0 else None
        td0 = {"padding": "6px 16px 10px 10px", "lineHeight": 1, "textAlign": "center"}
        td_zip = {
            "padding": "6px 10px 10px 14px",
            "fontWeight": 600,
            "color": "#ffffff",
        }
        td_state = {"padding": "6px 10px 10px 10px", "color": "#ffffff", "fontSize": "0.72rem"}
        td_score = {
            "padding": "6px 25px 10px 10px",
            "textAlign": "right",
            "fontWeight": 700,
            "--score-color": score_color,
        }
        if border_top:
            for d in (td0, td_zip, td_state, td_score):
                d["borderTop"] = border_top
        rows.append(
            html.Tr(
                [
                    html.Td(html.Span(str(rank), style=badge_style), style=td0),
                    html.Td(zc, className="rank-zip-cell", style=td_zip),
                    html.Td(st, className="rank-state-cell", style=td_state),
                    html.Td(
                        html.Span(
                            f"{score:.1f}",
                            className="rank-score-numeric",
                            style={"color": score_color, "fontWeight": 700},
                        ),
                        className="rank-score-cell",
                        style=td_score,
                    ),
                ],
                className="leaderboard-zip",
                style={"cursor": "pointer"},
                title=f"Go to {zc}",
                **{"data-zip": zc, "data-state": st},
            )
        )
    return html.Table(
        [thead, html.Tbody(rows)],
        style={
            "width": "96%",
            "margin": "0 auto",
            "fontSize": "0.78rem",
            "color": "#ffffff",
            "borderCollapse": "collapse",
        },
    )


def _settings_formula_block(selected_option: str) -> html.Div:
    """Structured markup for settings (Dash 2.18 `html.Div` has no `dangerously_allow_html`)."""
    o = str(selected_option or OPT2).strip()
    wrap = "settings-formula-block settings-note settings-equation"
    if o == "attractiveness_score_opt1":
        line = html.Div(
            [
                "z",
                html.Sub("i"),
                " = (x",
                html.Sub("i"),
                " − μ",
                html.Sub("i"),
                ") / σ",
                html.Sub("i"),
                " …",
            ],
            className="settings-equation-line",
        )
        title = html.Div(html.B("Option 1 (Z-score model)"), className="settings-equation-title")
        return html.Div([title, line], className=wrap)
    if o == "attractiveness_score_opt4":
        return html.Div(
            [
                html.Div(html.B("Option 4 (Weighted percentile)"), className="settings-equation-title"),
                html.Div("A = Σ(w×p) / Σw", className="settings-equation-line"),
            ],
            className=wrap,
        )
    return html.Div(
        [
            html.Div(html.B("Option 2 (Expert-weight percentile)"), className="settings-equation-title"),
            html.Div("A = Σ(w×p), Σw = 1", className="settings-equation-line"),
        ],
        className=wrap,
    )


_w0 = default_weight_state()
_g0 = _compute_gdf(_w0)
_st0 = _state_list(_g0)
_pref = "Florida" if "Florida" in _st0 else (_st0[0] if _st0 else None)
_state_opts = [{"label": s, "value": s} for s in _st0]

_DEFAULT_SIDEBAR_TAB = "market"
_TAB_PANEL_HIDE = {"display": "none"}
_TAB_PANEL_SHOW = {
    "display": "flex",
    "flexDirection": "column",
    "flex": "1 1 auto",
    "minHeight": 0,
    "overflowY": "auto",
    "overflowX": "hidden",
    "boxSizing": "border-box",
}
# Agent: single scroll in thread; outer panel must not scroll (avoids layout bleed).
_TAB_PANEL_SHOW_AGENT = {
    **_TAB_PANEL_SHOW,
    "overflowY": "hidden",
    "overflow": "hidden",
}

app.layout = html.Div(
    [
        dcc.Store(id="state-current", data=_pref),
        dcc.Store(id="weight-store", data=_w0),
        dcc.Store(id="selected-zips", data=[]),
        dcc.Store(id="zip-limit-msg", data=""),
        dcc.Store(id="opacity-store", data=1.0),
        dcc.Store(id="focus-zip", data=None),
        dcc.Store(id="map-version", data=0),
        dcc.Store(
            id="agent-messages",
            data=[{"role": "assistant", "text": "Hi, I'm your market strategy assistant."}],
        ),
        dcc.Store(id="bridge-map-click", data=None),
        dcc.Store(id="bridge-map-opacity", data=None),
        dcc.Store(id="bridge-map-state", data=None),
        dcc.Store(id="bridge-leaderboard-click", data=None),
        dcc.Store(id="bridge-chip-remove", data=None),
        dcc.Store(id="_bridge-boot", data=0),
        dcc.Store(id="_noop-clientside", data=None),
        html.Div(
            [
                html.Div(
                    [
                        html.Div(
                            [
                                html.Div(className="hm-sidebar-top-spacer"),
                                dcc.Tabs(
                                    id="sidebar-tabs",
                                    value=_DEFAULT_SIDEBAR_TAB,
                                    vertical=False,
                                    className="hm-tabs hm-tabs--topbar",
                                    colors={
                                        "border": "#333333",
                                        "primary": "#ff7f00",
                                        "background": ui_chrome_background(),
                                    },
                                    children=[
                                        dcc.Tab(
                                            label="Reference",
                                            value="ref",
                                            children=html.Div(
                                                className="hm-tab-placeholder",
                                                style={"display": "none"},
                                            ),
                                        ),
                                        dcc.Tab(
                                            label="Market Scores",
                                            value="zip",
                                            children=html.Div(
                                                className="hm-tab-placeholder",
                                                style={"display": "none"},
                                            ),
                                        ),
                                        dcc.Tab(
                                            label="Agent",
                                            value="agent",
                                            children=html.Div(
                                                className="hm-tab-placeholder",
                                                style={"display": "none"},
                                            ),
                                        ),
                                        dcc.Tab(
                                            label="Selection",
                                            value="market",
                                            children=html.Div(
                                                className="hm-tab-placeholder",
                                                style={"display": "none"},
                                            ),
                                        ),
                                        dcc.Tab(
                                            label="Settings",
                                            value="settings",
                                            children=html.Div(
                                                className="hm-tab-placeholder",
                                                style={"display": "none"},
                                            ),
                                        ),
                                    ],
                                ),
                                html.Div(
                                    [
                                        html.Div(
                                            id="panel-ref",
                                            style=_TAB_PANEL_HIDE,
                                            hidden=True,
                                            className="hm-sidebar-panel hm-tab-panel",
                                            children=[
                                                html.Iframe(
                                                    id="definitions-md",
                                                    className="definitions-section definitions-mount hm-definitions-frame",
                                                    title="Market framework reference",
                                                    srcDoc=wrap_definitions_srcdoc(
                                                        '<p class="def-empty-msg">Loading reference…</p>'
                                                    ),
                                                    style={
                                                        "width": "100%",
                                                        "flex": "1 1 auto",
                                                        "minHeight": "min(520px, 58vh)",
                                                        "border": "none",
                                                        "background": "#000",
                                                        "display": "block",
                                                    },
                                                )
                                            ],
                                        ),
                                html.Div(
                                    id="panel-zip",
                                    style=_TAB_PANEL_HIDE,
                                    hidden=True,
                                    className="hm-sidebar-panel hm-tab-panel ranks-section",
                                    children=[
                                        html.Div(
                                            [
                                                dcc.Input(
                                                    id="zip-search",
                                                    type="text",
                                                    placeholder="Search ZIP...",
                                                    className="hm-dash-input",
                                                    style={"marginBottom": 0},
                                                ),
                                                dcc.Dropdown(
                                                    id="rank-state-dd",
                                                    options=_state_opts,
                                                    value=_pref,
                                                    clearable=False,
                                                    className="hm-dash-dropdown",
                                                ),
                                            ],
                                            className="ranks-controls hm-form-stack",
                                        ),
                                        html.Div(
                                            id="leaderboard-md",
                                            className="ranks-scroll hm-leaderboard-root",
                                            children=[],
                                        ),
                                    ],
                                ),
                                html.Div(
                                    id="panel-market",
                                    style=_TAB_PANEL_SHOW,
                                    hidden=False,
                                    className="hm-sidebar-panel market-section",
                                    children=[
                                        html.Div(
                                            [
                                                html.Div(
                                                    "Market Score Selection",
                                                    className="market-selection-heading settings-title",
                                                ),
                                                html.Button(
                                                    "Reset",
                                                    id="selection-clear-zips",
                                                    n_clicks=0,
                                                    className="hm-selection-reset-btn",
                                                    type="button",
                                                ),
                                            ],
                                            id="market-selection-header",
                                            className="market-selection-header-wrap",
                                            style={"display": "none"},
                                        ),
                                        dcc.Markdown(
                                            id="market-md",
                                            dangerously_allow_html=True,
                                        ),
                                    ],
                                ),
                                html.Div(
                                    id="panel-agent",
                                    style=_TAB_PANEL_HIDE,
                                    hidden=True,
                                    className="hm-sidebar-panel settings-section agent-tab-section",
                                    children=[
                                        html.Div(
                                            [
                                                dcc.Markdown(
                                                    id="agent-thread-md",
                                                    dangerously_allow_html=True,
                                                    className="agent-thread-scroll agent-thread-panel-body",
                                                ),
                                                html.Div(
                                                    html.Div(
                                                        [
                                                            dcc.Input(
                                                                id="agent-message",
                                                                type="text",
                                                                placeholder="Ask Agent about this market...",
                                                                className="hm-dash-input agent-prompt-input",
                                                            ),
                                                            html.Button(
                                                                "Send",
                                                                id="agent-send",
                                                                n_clicks=0,
                                                                className="hm-agent-btn hm-agent-send",
                                                            ),
                                                            html.Button(
                                                                "Reset",
                                                                id="agent-clear",
                                                                n_clicks=0,
                                                                className="hm-agent-btn hm-agent-reset",
                                                            ),
                                                        ],
                                                        className="agent-prompt-bar",
                                                    ),
                                                    className="agent-prompt-outer",
                                                ),
                                            ],
                                            className="agent-shell",
                                        ),
                                    ],
                                ),
                                html.Div(
                                    id="panel-settings",
                                    style=_TAB_PANEL_HIDE,
                                    hidden=True,
                                    className="hm-sidebar-panel settings-section",
                                    children=[
                                        html.Div(
                                            [
                                                html.Div("Map Filters", className="settings-title"),
                                                html.Div(
                                                    "Map opacity",
                                                    className="settings-map-subtitle settings-map-opacity-label",
                                                ),
                                                html.Div(
                                                    dcc.Slider(
                                                        id="map-opacity-slider",
                                                        min=0,
                                                        max=100,
                                                        step=1,
                                                        value=100,
                                                        marks={0: "0%", 50: "50%", 100: "100%"},
                                                        tooltip={"placement": "bottom"},
                                                        className="hm-settings-opacity-slider",
                                                    ),
                                                    className="settings-opacity-slider-wrap",
                                                ),
                                                html.Div(
                                                    "State selection",
                                                    className="settings-map-subtitle",
                                                    style={"marginTop": 14},
                                                ),
                                                dcc.Dropdown(
                                                    id="settings-state-dd",
                                                    options=_state_opts,
                                                    value=_pref,
                                                    clearable=False,
                                                    className="settings-map-state-wrap hm-dash-dropdown",
                                                ),
                                                html.Div(
                                                    [
                                                        dcc.Checklist(
                                                            id="settings-show-market",
                                                            options=[{"label": " Market Score", "value": "m"}],
                                                            value=["m"],
                                                            inline=True,
                                                        ),
                                                        dcc.Checklist(
                                                            id="settings-show-entities",
                                                            options=[{"label": " Entities", "value": "e"}],
                                                            value=[],
                                                            inline=True,
                                                        ),
                                                        dcc.Markdown(
                                                            id="settings-selected-md",
                                                            dangerously_allow_html=True,
                                                            className="settings-selected-md",
                                                        ),
                                                    ],
                                                    style={"display": "none"},
                                                ),
                                            ],
                                            className="settings-map-filters-shell hm-form-stack",
                                        ),
                                        html.Div(
                                            [
                                                html.Div(
                                                    [
                                                        html.Div("Framework Weights", className="settings-title"),
                                                        html.Div(
                                                            [
                                                                html.Button(
                                                                    "Approve",
                                                                    id="btn-approve-weights",
                                                                    n_clicks=0,
                                                                    className="hm-settings-weights-btn hm-settings-weights-btn--approve",
                                                                ),
                                                                html.Button(
                                                                    "Reset",
                                                                    id="btn-reset-weights",
                                                                    n_clicks=0,
                                                                    className="hm-settings-weights-btn hm-settings-weights-btn--reset",
                                                                ),
                                                            ],
                                                            className="settings-actions settings-actions--weights",
                                                        ),
                                                    ],
                                                    className="settings-head",
                                                ),
                                                html.Div(id="settings-feedback"),
                                                html.Div(
                                                    [
                                                        html.Div(
                                                            "Tier 1 Options",
                                                            className="settings-map-subtitle",
                                                            style={"textAlign": "center"},
                                                        ),
                                                        html.Div(
                                                            id="settings-formula-md",
                                                            className="settings-tier-options-formula",
                                                            children=_settings_formula_block(
                                                                str(_w0["approved_score_option"])
                                                            ),
                                                        ),
                                                        dcc.RadioItems(
                                                            id="settings-score-option",
                                                            options=[
                                                                {"label": f" {v}", "value": k}
                                                                for k, v in SCORE_OPTION_CHOICES.items()
                                                            ],
                                                            value=_w0["approved_score_option"],
                                                            inline=True,
                                                            className="settings-score-option-wrap",
                                                            labelClassName="settings-score-option-label",
                                                            labelStyle=_SETTINGS_SCORE_OPTION_LABEL_STYLE,
                                                            inputClassName="settings-score-option-input",
                                                            inputStyle={
                                                                "width": "12px",
                                                                "height": "12px",
                                                                "marginRight": "6px",
                                                                "verticalAlign": "middle",
                                                                "cursor": "pointer",
                                                            },
                                                        ),
                                                    ],
                                                    className="settings-tier-details-body settings-tier-options-block",
                                                ),
                                                _build_construct_weights_panel(),
                                            ],
                                            className="settings-shell settings-shell--weights hm-form-stack",
                                        ),
                                    ],
                                ),
                                    ],
                                    className="hm-sidebar-panels",
                                ),
                            ],
                            className="hm-sidebar hm-sidebar-column",
                        ),
                        html.Div(
                            [
                                html.Div(
                                    html.Div(
                                        [
                                            html.Div(
                                                id="map-slot",
                                                style={
                                                    "position": "relative",
                                                    "width": "100%",
                                                    "flex": "1",
                                                    "minHeight": 0,
                                                },
                                            ),
                                            html.Div(
                                                html.Div(
                                                    [
                                                        html.Div(
                                                            "Market Score",
                                                            className="hm-map-legend-h-title hm-map-overlay-font",
                                                        ),
                                                        html.Div(
                                                            className="hm-map-legend-h-strip",
                                                            style={
                                                                "background": score_legend_gradient_css()
                                                            },
                                                        ),
                                                        html.Div(
                                                            [
                                                                html.Span(
                                                                    "LOW",
                                                                    className="hm-map-legend-h-end hm-map-overlay-font",
                                                                ),
                                                                html.Span(
                                                                    "HIGH",
                                                                    className="hm-map-legend-h-end hm-map-overlay-font",
                                                                ),
                                                            ],
                                                            className="hm-map-legend-h-labels hm-map-overlay-font",
                                                        ),
                                                    ],
                                                    className="hm-map-legend-h-panel",
                                                ),
                                                className="hm-map-legend-overlay hm-map-overlay-font",
                                            ),
                                        ],
                                        className="hm-map-area",
                                    ),
                                    className="hm-map-stack",
                                ),
                            ],
                            className="hm-main",
                        ),
                    ],
                    className="hm-layout",
                ),
            ],
            className="hm-app",
        ),
    ]
)


@callback(
    Output("panel-ref", "style"),
    Output("panel-ref", "hidden"),
    Output("panel-zip", "style"),
    Output("panel-zip", "hidden"),
    Output("panel-market", "style"),
    Output("panel-market", "hidden"),
    Output("panel-agent", "style"),
    Output("panel-agent", "hidden"),
    Output("panel-settings", "style"),
    Output("panel-settings", "hidden"),
    Input("sidebar-tabs", "value"),
)
def _sync_tab_panels(tab: str | None):
    t = (tab or _DEFAULT_SIDEBAR_TAB).strip()
    keys = ("ref", "zip", "market", "agent", "settings")
    styles: list = []
    hiddens: list[bool] = []
    for k in keys:
        if t == k:
            styles.append(_TAB_PANEL_SHOW_AGENT if k == "agent" else _TAB_PANEL_SHOW)
            hiddens.append(False)
        else:
            styles.append(_TAB_PANEL_HIDE)
            hiddens.append(True)
    # Outputs are interleaved: ref style, ref hidden, zip style, zip hidden, …
    return tuple(x for pair in zip(styles, hiddens) for x in pair)


def _strip_geo(d: dict) -> dict:
    o = dict(d)
    for k in ("geometry", "__geo_interface__", "__ord"):
        o.pop(k, None)
    return o


def _enrich_selected(sel: list[dict], live: pd.DataFrame) -> list[dict]:
    if not sel or live is None or len(live) == 0 or "zipcode" not in live.columns:
        return list(sel)
    live = live.copy()
    live["zipcode"] = live["zipcode"].astype(str).str.zfill(5)
    live_rows = live.drop_duplicates(subset=["zipcode"]).set_index("zipcode")
    out: list[dict] = []
    for rec in sel:
        z = str(rec.get("zipcode", "")).zfill(5)
        if z in live_rows.index:
            merged = dict(rec)
            merged.update(live_rows.loc[z].to_dict())
            merged = _strip_geo(merged)
            merged["zipcode"] = z
            out.append(merged)
        else:
            out.append(rec)
    return out


def _settings_selected_block(sel: list[dict]) -> str:
    if not sel:
        return '<div class="settings-selected-zips">None</div>'
    rows = []
    for z in sel:
        zr = str(z.get("zipcode", "")).strip()
        if not zr:
            continue
        zc = normalize_zip(zr)
        st = str(z.get("state", "")).strip()
        row = f"{html_lib.escape(zc)}{(' - ' + html_lib.escape(st)) if st else ''}"
        rows.append(row)
    if not rows:
        return '<div class="settings-selected-zips">None</div>'
    lines = "".join(f'<div class="settings-selected-zips-line">{r}</div>' for r in rows)
    return f'<div class="settings-selected-zips">{lines}</div>'


def _agent_thread_html(msgs: list) -> str:
    rows = []
    for m in msgs:
        role = str(m.get("role", "assistant"))
        text = html_lib.escape(str(m.get("text", ""))).replace("\n", "<br>")
        bubble_cls = "agent-msg-user" if role == "user" else "agent-msg-assistant"
        label = "You" if role == "user" else "Agent"
        rows.append(
            f'<div class="agent-msg {bubble_cls}">'
            f'<div class="agent-msg-label">{label}</div>'
            f'<div class="agent-msg-text">{text}</div></div>'
        )
    return '<div class="agent-thread">' + "".join(rows) + "</div>"


@callback(
    Output("state-current", "data"),
    Output("rank-state-dd", "value"),
    Output("settings-state-dd", "value"),
    Output("focus-zip", "data"),
    Output("bridge-leaderboard-click", "data"),
    Input("rank-state-dd", "value"),
    Input("settings-state-dd", "value"),
    Input("bridge-map-state", "data"),
    Input("bridge-leaderboard-click", "data"),
    State("state-current", "data"),
)
def _sync_state(rnk, stg, mbridge, lb, cur):
    cur = cur or _pref
    tid = ctx.triggered_id
    if tid == "bridge-leaderboard-click" and lb and isinstance(lb, dict):
        st = str(lb.get("state") or "").strip()
        z = lb.get("zipcode")
        if st:
            return st, st, st, z, None
        return no_update, no_update, no_update, no_update, None
    if tid == "bridge-map-state" and mbridge:
        return mbridge, mbridge, mbridge, no_update, no_update
    if tid == "rank-state-dd" and rnk:
        return rnk, no_update, rnk, no_update, no_update
    if tid == "settings-state-dd" and stg:
        return stg, stg, no_update, no_update, no_update
    return cur, cur, cur, no_update, no_update


@callback(
    Output("definitions-md", "srcDoc"),
    Output("leaderboard-md", "children"),
    Output("market-md", "children"),
    Output("map-slot", "children"),
    Output("map-opacity-slider", "value"),
    Output("settings-selected-md", "children"),
    Output("agent-thread-md", "children"),
    Input("weight-store", "data"),
    Input("state-current", "data"),
    Input("zip-search", "value"),
    Input("settings-show-market", "value"),
    Input("settings-show-entities", "value"),
    Input("map-version", "data"),
    Input("selected-zips", "data"),
    Input("zip-limit-msg", "data"),
    Input("focus-zip", "data"),
    Input("agent-messages", "data"),
    State("opacity-store", "data"),
    State("map-slot", "children"),
)
def _refresh_main(
    w,
    state_val,
    zip_q,
    show_m,
    show_e,
    _mv,
    selected,
    lim_msg,
    fz,
    agent_msgs,
    opacity,
    map_slot_children,
):
    w = w or _w0
    skip_map = _map_refresh_is_selection_only() and _map_slot_has_iframe(map_slot_children)
    gdf = _compute_gdf(w)
    st = state_val or _pref
    sel = list(selected or [])
    live_df = pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore"))
    sel_live = _enrich_selected(sel, live_df)
    ents = None
    if ENTITIES_DF is not None and sel_live:
        zips = [str(z.get("zipcode", "")) for z in sel_live]
        mask = ENTITIES_DF["zip"].astype(str).str.zfill(5).isin(zips)
        if mask.any():
            ents = ENTITIES_DF[mask]
    mk = market_tab_html(sel_live, ents, selected_option=str(w.get("approved_score_option") or OPT2))
    sel_html = _settings_selected_block(sel)

    if skip_map:
        return (
            no_update,
            no_update,
            mk,
            no_update,
            no_update,
            sel_html,
            no_update,
        )

    if _refresh_is_focus_zip_only() and _map_slot_has_iframe(map_slot_children):
        return (no_update, no_update, no_update, no_update, no_update, no_update, no_update)

    if _skip_map_rebuild_for_zip_focus_nav() and _map_slot_has_iframe(map_slot_children):
        defs = build_definitions_html(
            pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore")),
            st,
            w.get("approved_dim_weights") or {dim: 25.0 for dim in _w0["approved_dim_weights"]},
            w["approved_construct_component_weights"],
            default_construct_component_weights(),
        )
        defs_doc = wrap_definitions_srcdoc(defs) if isinstance(defs, str) else wrap_definitions_srcdoc("")
        lb = _leaderboard_content(gdf, st, zip_q or "")
        ag_html = _agent_thread_html(agent_msgs or [])
        return defs_doc, lb, mk, no_update, no_update, sel_html, ag_html

    if _refresh_is_zip_search_only():
        gdf = _compute_gdf(w)
        st = state_val or _pref
        lb = _leaderboard_content(gdf, st, zip_q or "")
        return no_update, lb, no_update, no_update, no_update, no_update, no_update

    defs = build_definitions_html(
        pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore")),
        st,
        w.get("approved_dim_weights") or {dim: 25.0 for dim in _w0["approved_dim_weights"]},
        w["approved_construct_component_weights"],
        default_construct_component_weights(),
    )
    defs_doc = wrap_definitions_srcdoc(defs) if isinstance(defs, str) else wrap_definitions_srcdoc("")
    lb = _leaderboard_content(gdf, st, zip_q or "")
    filtered = gdf[gdf["state"] == st] if st else gdf
    if len(filtered) == 0:
        map_el = html.P("No data.", style={"color": "#888", "textAlign": "center", "padding": 40})
    else:
        op = float(opacity if opacity is not None else 1.0)
        fz_use = fz
        zs = set(filtered["zipcode"].map(normalize_zip).tolist())
        if fz_use and normalize_zip(str(fz_use)) in zs:
            fz_use = None
        sel_z = [str(z.get("zipcode", "")) for z in sel]
        st_ents = None
        if ENTITIES_DF is not None:
            ab = _STATE_TO_ABBR.get(st, st)
            m = ENTITIES_DF["state"].isin([st, ab])
            if m.any():
                st_ents = ENTITIES_DF[m]
        html_s = build_map(
            filtered,
            op,
            focus_zip=fz_use,
            selected_zips=sel_z,
            entities=st_ents,
            all_states=_state_list(gdf),
            current_state=st,
            show_market_layer=bool(show_m and "m" in show_m),
            show_entities_layer=bool(show_e and "e" in show_e),
            iframe_src_prefix=MAP_PREFIX,
        )
        mch = re.search(r'src="([^"]+)"', html_s)
        src = mch.group(1) if mch else "map.html"
        map_el = html.Iframe(
            src=src,
            id="map_frame",
            style={"width": "100%", "height": "100%", "border": "none", "display": "block"},
        )
    ag_html = _agent_thread_html(agent_msgs or [])
    op_slider = _map_opacity_slider_value(opacity)
    return defs_doc, lb, mk, map_el, op_slider, sel_html, ag_html


@callback(
    Output("settings-formula-md", "children"),
    Input("settings-score-option", "value"),
)
def _formula(opt):
    return _settings_formula_block(str(opt or OPT2))


@callback(
    Output("selected-zips", "data", allow_duplicate=True),
    Output("zip-limit-msg", "data", allow_duplicate=True),
    Output("bridge-map-click", "data"),
    Input("bridge-map-click", "data"),
    State("selected-zips", "data"),
    prevent_initial_call=True,
)
def _map_click(data, sel):
    if not data:
        raise PreventUpdate
    d = _strip_geo(dict(data) if isinstance(data, dict) else {})
    z = normalize_zip(str(d.get("zipcode") or d.get("zip_code") or d.get("ZIP") or ""))
    if not z:
        raise PreventUpdate
    d["zipcode"] = z
    action = d.get("action", "select")
    cur = list(sel or [])
    if action == "deselect":
        cur = [x for x in cur if normalize_zip(str(x.get("zipcode", ""))) != z]
        return cur, "", None
    if action == "limit_reached":
        return no_update, "Limit reached", None
    if len(cur) >= MAX_SELECTED:
        return no_update, "Limit reached", None
    if not any(normalize_zip(str(x.get("zipcode", ""))) == z for x in cur):
        cur.append(d)
    return cur, "", None


@callback(
    Output("selected-zips", "data", allow_duplicate=True),
    Output("bridge-chip-remove", "data"),
    Input("bridge-chip-remove", "data"),
    State("selected-zips", "data"),
    prevent_initial_call=True,
)
def _chip_remove(data, sel):
    if not data or not isinstance(data, dict):
        raise PreventUpdate
    z = normalize_zip(str(data.get("zipcode", "")))
    cur = [x for x in (sel or []) if normalize_zip(str(x.get("zipcode", ""))) != z]
    return cur, None


@callback(
    Output("opacity-store", "data", allow_duplicate=True),
    Output("bridge-map-opacity", "data"),
    Input("bridge-map-opacity", "data"),
    prevent_initial_call=True,
)
def _opacity(v):
    if v is None:
        raise PreventUpdate
    try:
        return float(v), None
    except (TypeError, ValueError):
        raise PreventUpdate


@callback(
    Output("opacity-store", "data", allow_duplicate=True),
    Input("map-opacity-slider", "value"),
    prevent_initial_call=True,
)
def _opacity_from_dash_slider(v):
    if v is None:
        raise PreventUpdate
    try:
        return max(0.0, min(1.0, float(v) / 100.0))
    except (TypeError, ValueError):
        raise PreventUpdate


@callback(
    Output("selected-zips", "data", allow_duplicate=True),
    Output("focus-zip", "data", allow_duplicate=True),
    Output("map-version", "data", allow_duplicate=True),
    Input("selection-clear-zips", "n_clicks"),
    State("map-version", "data"),
    prevent_initial_call=True,
)
def _clear_zips(n_selection, mv):
    if not n_selection:
        raise PreventUpdate
    mv = int(mv or 0) + 1
    return [], None, mv


@callback(
    Output("market-selection-header", "style"),
    Input("selected-zips", "data"),
)
def _market_selection_header_visibility(zips):
    zips = zips or []
    if len(zips) == 0:
        return {"display": "none"}
    return {"display": "block"}


_slider_outputs = [Output(sid, "value") for sid, _, _, _ in OPT2_SLIDER_SPECS]


@callback(_SLIDER_DISABLED_OUTPUTS, Input("settings-score-option", "value"))
def _construct_sliders_editable(opt: str | None):
    """Option 2 only: construct indicator sliders are editable. Options 1 and 4 use fixed stored weights."""
    o = str(opt or "").strip()
    locked = o != OPT2
    return [locked] * len(OPT2_SLIDER_SPECS)


@callback(_slider_outputs, Input("weight-store", "data"))
def _sliders_from_store(w):
    w = w or _w0
    ccw = w.get("approved_construct_component_weights") or {}
    block = ccw.get(OPT2) or {}
    out = []
    for sid, dim, ind, _ in OPT2_SLIDER_SPECS:
        v = float(block.get(dim, {}).get(ind, 0.0))
        out.append(int(round(v)))
    return out


@callback(
    Output("weight-store", "data", allow_duplicate=True),
    Output("settings-feedback", "children", allow_duplicate=True),
    Input("btn-approve-weights", "n_clicks"),
    State("weight-store", "data"),
    State("settings-score-option", "value"),
    *[State(sid, "value") for sid, _, _, _ in OPT2_SLIDER_SPECS],
    prevent_initial_call=True,
)
def _approve_weights(n, w, opt, *slider_vals):
    if not n:
        raise PreventUpdate
    w = deepcopy(w or _w0)
    opt = str(opt or "").strip()
    if opt not in SCORE_OPTION_CHOICES:
        opt = DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in SCORE_OPTION_CHOICES else OPT2
    w["approved_score_option"] = opt
    ocw = w.get("approved_option_component_weights") or {}
    ov = ocw.get(opt, {})
    if opt == OPT2 and ov and int(round(sum(float(x) for x in ov.values()))) != 100:
        return no_update, html.Div(
            f"Tier 1 option weights must total 100 (stored). Current: {int(round(sum(float(x) for x in ov.values())))}.",
            className="settings-note settings-weights-feedback",
        )
    if opt == OPT2:
        construct_defaults = default_construct_component_weights()[OPT2]
        new_block: dict[str, dict[str, float]] = {}
        bad: list[str] = []
        idx = 0
        for dim, _label in DIMENSION_META:
            dim_def = construct_defaults.get(dim, {})
            dim_vals: dict[str, float] = {}
            for ind in dim_def:
                val = max(0.0, float(slider_vals[idx]))
                idx += 1
                dim_vals[ind] = val
            tot = sum(dim_vals.values())
            if abs(tot - 100.0) > 1e-6:
                bad.append(dim)
            new_block[dim] = dim_vals
        if bad:
            return no_update, html.Div(
                "Each construct's indicators must total 100% before approval.",
                className="settings-note settings-weights-feedback",
            )
        acc = w.setdefault("approved_construct_component_weights", {})
        acc[OPT2] = new_block
    return w, ""


@callback(
    Output("weight-store", "data", allow_duplicate=True),
    Output("settings-score-option", "value", allow_duplicate=True),
    Input("btn-reset-weights", "n_clicks"),
    prevent_initial_call=True,
)
def _reset_weights(n):
    if not n:
        raise PreventUpdate
    d = default_weight_state()
    return d, d["approved_score_option"]


@callback(
    Output("agent-messages", "data", allow_duplicate=True),
    Output("agent-message", "value"),
    Input("agent-send", "n_clicks"),
    State("agent-message", "value"),
    State("agent-messages", "data"),
    State("selected-zips", "data"),
    State("weight-store", "data"),
    State("state-current", "data"),
    prevent_initial_call=True,
)
def _agent_send(n, msg, hist, sel, w, st):
    if not n:
        raise PreventUpdate
    msg = (msg or "").strip()
    if not msg:
        raise PreventUpdate
    w = w or _w0
    gdf = _compute_gdf(w)
    df = pd.DataFrame(gdf.drop(columns=["geometry"], errors="ignore"))
    if st:
        df = df[df["state"] == st]
    sel_live = _enrich_selected(list(sel or []), df)
    new_hist = run_agent_turn(
        msg,
        list(hist or []),
        sel_live,
        df,
        w.get("approved_tier_weights") or _w0["approved_tier_weights"],
        str(w.get("approved_score_option") or OPT2),
    )
    return new_hist, ""


@callback(
    Output("agent-messages", "data", allow_duplicate=True),
    Input("agent-clear", "n_clicks"),
    prevent_initial_call=True,
)
def _agent_clear(n):
    if not n:
        raise PreventUpdate
    return [{"role": "assistant", "text": "Hi, I'm your market strategy assistant."}]


if __name__ == "__main__":
    import os as _os

    _port = int(_os.environ.get("PORT", _os.environ.get("HM_PORT", "8050")))
    _debug = str(_os.environ.get("FLASK_DEBUG", "0")).strip().lower() in {"1", "true", "yes"}
    app.run_server(debug=_debug, host="0.0.0.0", port=_port)
