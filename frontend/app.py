from shiny import App, ui, render, reactive
import html
import os
import re
import sys
import time
import pandas as pd

_FRONTEND_DIR = os.path.dirname(os.path.abspath(__file__))
_PROJECT_ROOT = os.path.abspath(os.path.join(_FRONTEND_DIR, ".."))
if _PROJECT_ROOT not in sys.path:
    sys.path.insert(0, _PROJECT_ROOT)

from config import WWW_DIR, COLORMAP
from modules.data.loader import gdf as initial_gdf, ENTITIES_DF
from modules.map.builder import build_map
from modules.dashboard import (
    APP_CSS,
    PARENT_JS,
    MAX_SELECTED,
    entity_count_html,
    map_chips_html,
    market_tab_html,
    normalize_zip,
    selected_zip_set,
    prioritize_selected_rows,
)
from backend.agent import query_agent, try_handle_query
from backend.agent.agent_config import SCORE_DEFINITIONS, DEFAULT_SCORE_COLUMN, RAW_TO_PCTILE

_STATE_TO_ABBR = {
    "Alabama": "AL", "Florida": "FL", "Georgia": "GA",
}

_DIMENSION_META = [
    ("attractiveness", "Market Attractiveness"),
    ("ability_to_win", "Ability to Succeed"),
    ("ripeness", "Ripeness"),
    ("economic_significance", "Economic Significance"),
]

_TIER_META = [
    ("tier1", "Tier 1"),
    ("tier2", "Tier 2"),
    ("tier3", "Tier 3"),
]
_DEFAULT_TIER_WEIGHTS = {"tier1": 100.0, "tier2": 0.0, "tier3": 0.0}
_SCORE_OPTION_CHOICES = {
    "attractiveness_score_opt1": "Option 1",
    "attractiveness_score_opt2": "Option 2",
    "attractiveness_score_opt4": "Option 4",
}

_TIER1_NUMERIC_INDICATORS = [
    "total_population", "population_growth_rate_2yr", "net_population_change_2yr",
    "population_growth_5yr_pct", "age_0_17", "age_18_44", "age_45_64", "age_65_plus",
    "age_0_17_pct", "age_18_44_pct", "age_45_64_pct", "age_65_plus_pct", "median_age",
    "white_alone", "black_alone", "asian_alone", "hispanic_latino", "white_pct",
    "black_pct", "asian_pct", "hispanic_pct", "pct_white", "pct_black", "pct_asian",
    "pct_hispanic", "median_household_income", "bachelors_or_higher",
    "bachelors_or_higher_pct", "birth_rate_per_1000", "in_migration_from_other_state",
    "in_migration_rate", "in_migration_pct", "unemployed", "unemployment_rate",
    "per_capita_income", "per_capita_income_growth_2yr", "top_industry_employment",
    "industry_agriculture", "industry_construction", "industry_manufacturing",
    "industry_retail", "industry_finance", "industry_professional_tech",
    "industry_education_and_health", "industry_arts_entertainment",
    "industry_other_services", "industry_public_administration",
    "county_level_gdp_thousands", "county_level_gdp_growth_5yr",
    "msa_level_gdp_millions", "msa_gdp_growth_5yr", "pct_under_18",
    "pct_18_44", "pct_45_64", "pct_18_64", "pct_65_plus",
]

_DIMENSION_RULES = {
    "attractiveness": {
        "keywords": ("growth", "income", "migration", "gdp", "birth", "unemploy"),
        "invert_keywords": ("unemploy",),
    },
    "ability_to_win": {
        "keywords": ("industry", "employment", "18_44", "45_64", "18_64", "bachelors"),
        "invert_keywords": (),
    },
    "ripeness": {
        "keywords": ("65_plus", "median_age", "hispanic", "black", "asian", "white", "pct_"),
        "invert_keywords": (),
    },
    "economic_significance": {
        "keywords": ("total_population", "gdp", "income", "count", "age_"),
        "invert_keywords": (),
    },
}


def _pretty_indicator_name(ind: str) -> str:
    return ind.replace("_", " ").title()


def _dim_weight_id(dim: str) -> str:
    return f"w_dim_{dim}"


def _tier_weight_id(tier: str) -> str:
    return f"w_{tier}"


def _option_component_slider_id(score_col: str, component_col: str) -> str:
    return f"w_opt_{score_col}_{component_col}"


def _ind_weight_id(ind: str) -> str:
    return f"w_ind_{ind}"


def _safe_slider_input(input_obj, input_id: str, default: float) -> float:
    try:
        v = getattr(input_obj, input_id)()
        return default if v is None else float(v)
    except Exception:
        return default


def _default_option_component_weights() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for score_col, score_def in SCORE_DEFINITIONS.items():
        weights: dict[str, float] = {}
        for component_col, meta in (score_def.get("components") or {}).items():
            weights[component_col] = float(meta.get("weight", 0.0)) * 100.0
        out[score_col] = weights
    return out


def _build_dimension_indicator_config():
    dim_map = {k: [] for k, _ in _DIMENSION_META}
    inverted = set()
    auto_to_attr = []
    for col in _TIER1_NUMERIC_INDICATORS:
        col_l = col.lower()
        best_dim = None
        best_score = 0
        for dim, cfg in _DIMENSION_RULES.items():
            score = sum(1 for kw in cfg["keywords"] if kw in col_l)
            if score > best_score:
                best_score = score
                best_dim = dim
        if not best_dim or best_score == 0:
            best_dim = "attractiveness"
            auto_to_attr.append(col)
        dim_map[best_dim].append(col)
        if any(kw in col_l for kw in _DIMENSION_RULES[best_dim]["invert_keywords"]):
            inverted.add(col)
    return dim_map, inverted, auto_to_attr


_DIMENSION_INDICATORS, _INVERTED_INDICATORS, _AUTO_TO_ATTR = _build_dimension_indicator_config()


def _settings_weights_panel():
    details_body = ui.div(
        ui.div(
            ui.output_ui("settings_option_weight_summary"),
            ui.div(
                ui.input_radio_buttons(
                    "settings_score_option",
                    None,
                    choices=_SCORE_OPTION_CHOICES,
                    selected=DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in _SCORE_OPTION_CHOICES else "attractiveness_score_opt2",
                    inline=True,
                ),
                class_="settings-score-option-wrap",
            ),
            class_="settings-option-stack",
        ),
        ui.output_ui("settings_tier1_component_sliders"),
        class_="settings-tier-details-body",
    )
    return ui.div(
        ui.div(
            ui.div("Framework Weights", class_="settings-title"),
            ui.div(
                ui.input_action_button("settings_approve_weights", "Approve"),
                ui.input_action_button("settings_reset_weights", "Reset"),
                class_="settings-actions",
            ),
            class_="settings-head",
        ),
        ui.output_ui("settings_weights_feedback"),
        ui.div(
            ui.div(
                ui.tags.details(
                    ui.tags.summary("Tier 1 Weights", class_="settings-tier-summary"),
                    details_body,
                    class_="settings-tier-dropdown",
                ),
                class_="settings-dim-card",
            ),
            ui.div(
                ui.tags.details(
                    ui.tags.summary("Tier 2 Weights", class_="settings-tier-summary"),
                    ui.div("", class_="settings-tier-details-body settings-tier-empty-body"),
                    class_="settings-tier-dropdown",
                ),
                class_="settings-dim-card",
            ),
            ui.div(
                ui.tags.details(
                    ui.tags.summary("Tier 3 Weights", class_="settings-tier-summary"),
                    ui.div("", class_="settings-tier-details-body settings-tier-empty-body"),
                    class_="settings-tier-dropdown",
                ),
                class_="settings-dim-card",
            ),
            class_="settings-weight-grid",
        ),
        class_="settings-shell",
    )


def _settings_map_filters_panel():
    return ui.div(
        ui.div(
            ui.div("Map Filters", class_="settings-title"),
            class_="settings-map-head",
        ),
        ui.div(
            ui.div("Data Layers", class_="settings-map-subtitle"),
            ui.input_checkbox("settings_show_market_layer", "Market Score", value=True),
            ui.input_checkbox("settings_show_entities_layer", "Entities", value=False),
            ui.div(
                ui.div(
                    ui.div("Selected ZIPs", class_="settings-map-subtitle"),
                    ui.input_action_button("settings_clear_selected_zips", "Clear"),
                    class_="settings-selected-zips-head",
                ),
                ui.output_ui("settings_selected_zips"),
                class_="settings-selected-zips-wrap",
            ),
            ui.div(
                ui.input_select(
                    "settings_map_state",
                    "State",
                    choices={},
                    selected=None,
                ),
                class_="settings-map-state-wrap",
            ),
            class_="settings-map-filters-body",
        ),
        class_="settings-map-filters-shell",
    )

# UI
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.navset_underline(
            # Definitions tab
            ui.nav_panel(
                "Reference",
                ui.div(
                    ui.output_ui("definitions_panel"),
                    class_="definitions-section",
                ),
                value="Reference",
            ),
            # Ranks tab
            ui.nav_panel(
                "ZIPs",
                ui.div(
                    ui.output_ui("rank_count_title"),
                    ui.div(
                        ui.input_text("zip_search", None, placeholder="Search ZIP..."),
                        ui.input_select(
                            "rank_filter", None,
                            choices={},
                            selected=None,
                        ),
                        class_="ranks-controls",
                    ),
                    ui.div(
                        ui.output_ui("leaderboard"),
                        class_="ranks-scroll",
                    ),
                    class_="ranks-section",
                ),
                value="ZIPs",
            ),
            # myMarket tab
            ui.nav_panel(
                "Market",
                ui.div(
                    ui.output_ui("market_panel"),
                    class_="market-section",
                ),
                value="Market",
            ),
            # myAgent tab
            ui.nav_panel(
                "Agent",
                ui.div(
                    ui.div(
                        ui.div("Belfort", class_="agent-title"),
                        ui.div(
                            ui.div(ui.output_ui("agent_thread"), class_="agent-thread-wrap"),
                            ui.div(
                                ui.input_text(
                                    "agent_message",
                                    None,
                                    value="",
                                    placeholder="Ask Belfort about this market...",
                                ),
                                ui.input_action_button("agent_send", "Send"),
                                ui.input_action_button("agent_clear", "Reset"),
                                class_="agent-compose",
                            ),
                            class_="agent-chat-block",
                        ),
                        class_="agent-shell",
                    ),
                    class_="settings-section",
                ),
                value="Agent",
            ),
            # Settings tab
            ui.nav_panel(
                "Settings",
                ui.div(
                    _settings_map_filters_panel(),
                    ui.hr(class_="def-section-divider"),
                    _settings_weights_panel(),
                    class_="settings-section",
                ),
                value="Settings",
            ),
            id="sidebar_tabs",
            selected="Market",
        ),
        ui.div(
            ui.input_select("state", None, choices={}, selected=None),
            style="display:none;",
        ),
        width="635px",
        open="always",
    ),
    ui.tags.style(APP_CSS),
    ui.tags.script(PARENT_JS),
    ui.div(
        ui.output_ui("map_chips_bar"),
        ui.output_ui("map_container"),
        style="position:relative;width:100%;height:100vh;overflow:hidden;",
    ),
    fillable=True,
    window_title="Hospital Market Demo",
    title=None,
)

# Server 
def server(input, output, session):
    r_raw_gdf = reactive.value(initial_gdf.copy())

    clicked_zip = reactive.value(None)
    selected_zips = reactive.value([])
    zip_limit_msg = reactive.value("")
    r_opacity = reactive.value(1.0)
    skip_reset = reactive.value(False)
    focus_zip = reactive.value(None)
    map_version = reactive.value(0)
    _settings_adjusting = reactive.value(False)
    _approved_dim_weights = reactive.value({dim: 25.0 for dim, _ in _DIMENSION_META})
    _approved_tier_weights = reactive.value(dict(_DEFAULT_TIER_WEIGHTS))
    _approved_option_component_weights = reactive.value(_default_option_component_weights())
    _approved_score_option = reactive.value(
        DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in _SCORE_OPTION_CHOICES else "attractiveness_score_opt2"
    )
    _settings_weights_feedback = reactive.value("")
    _settings_feedback_set_at = reactive.value(0.0)
    agent_messages = reactive.value([
        {
            "role": "assistant",
            "text": "Hi I’m Belfort, your market strategy assistant.",
        }
    ])

    def _norm_series(frame: pd.DataFrame, series: str, invert: bool = False):
        if series not in frame.columns:
            return None
        s = pd.to_numeric(frame[series], errors="coerce")
        valid = s.dropna()
        if len(valid) == 0:
            return None
        mn, mx = valid.min(), valid.max()
        out = (s * 0 + 50.0) if mx <= mn else ((s - mn) / (mx - mn) * 100.0)
        return (100.0 - out) if invert else out

    def _apply_settings_weights(frame: pd.DataFrame) -> pd.DataFrame:
        data = frame.copy()
        if data is None or len(data) == 0:
            return data

        fallback = pd.to_numeric(data.get("hospital_potential", 0), errors="coerce").fillna(0.0).clip(0, 100)
        if not isinstance(fallback, pd.Series):
            fallback = pd.Series([float(fallback)] * len(data), index=data.index, dtype=float).clip(0, 100)

        def _series_or_default(col: str, default: float = 0.0) -> pd.Series:
            if col in data.columns:
                s = pd.to_numeric(data[col], errors="coerce")
                return s.fillna(default).astype(float)
            return pd.Series([float(default)] * len(data), index=data.index, dtype=float)

        pct_to_raw = {pct: raw for raw, pct in RAW_TO_PCTILE.items()}
        approved_option_component_weights = _approved_option_component_weights()
        for score_col, score_def in SCORE_DEFINITIONS.items():
            if score_col in data.columns:
                data[score_col] = pd.to_numeric(data[score_col], errors="coerce").fillna(fallback).clip(0, 100)
                continue
            option_weights_pct = approved_option_component_weights.get(score_col, {})
            comp_cols = list((score_def.get("components") or {}).keys())
            pct_sum = sum(float(option_weights_pct.get(c, 0.0)) for c in comp_cols)
            if pct_sum <= 0:
                pct_sum = 100.0
            weighted = None
            valid = True
            for pct_col, meta in (score_def.get("components") or {}).items():
                s = None
                if pct_col in data.columns:
                    s = pd.to_numeric(data[pct_col], errors="coerce")
                else:
                    raw_col = pct_to_raw.get(pct_col)
                    if raw_col and raw_col in data.columns:
                        raw = pd.to_numeric(data[raw_col], errors="coerce")
                        rank_pct = raw.rank(pct=True, method="average")
                        if str(meta.get("direction", "higher_is_better")) == "lower_is_better":
                            rank_pct = 1.0 - rank_pct
                        s = (rank_pct * 99.0).clip(0.0, 99.0)
                if s is None:
                    valid = False
                    break
                approved_pct = approved_option_component_weights.get(score_col, {}).get(
                    pct_col,
                    float(meta.get("weight", 0.0)) * 100.0,
                )
                contrib = s.fillna(0.0) * (float(approved_pct) / float(pct_sum))
                weighted = contrib if weighted is None else (weighted + contrib)
            if valid and weighted is not None:
                data[score_col] = pd.to_numeric(weighted, errors="coerce").fillna(0.0).clip(0.0, 99.0).round(2)

        selected_option = str(_approved_score_option() or DEFAULT_SCORE_COLUMN).strip()
        if selected_option not in data.columns:
            selected_option = DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in data.columns else "hospital_potential"
        tier1_base = _series_or_default(selected_option, default=0.0).fillna(fallback).clip(0, 100)
        tier_series = {
            "tier1": tier1_base,
            "tier2": _series_or_default("tier2_score", default=0.0).clip(0, 100),
            "tier3": _series_or_default("tier3_score", default=0.0).clip(0, 100),
        }
        for tier, _ in _TIER_META:
            data[tier] = tier_series[tier]

        tier_weights = {
            tier: max(0.0, float(_approved_tier_weights().get(tier, _DEFAULT_TIER_WEIGHTS.get(tier, 0.0))))
            for tier, _ in _TIER_META
        }
        w_total = sum(tier_weights.values())
        if w_total <= 0:
            w_total = 1.0
            tier_weights = {"tier1": 1.0, "tier2": 0.0, "tier3": 0.0}
        score = None
        for tier, _ in _TIER_META:
            contrib = pd.to_numeric(tier_series[tier], errors="coerce").fillna(0.0) * float(tier_weights[tier])
            score = contrib if score is None else (score + contrib)
        data["hospital_potential"] = (score / float(w_total)).clip(0, 100)
        return data

    @reactive.calc
    def r_gdf():
        data = r_raw_gdf().copy()
        if "hospital_potential" not in data.columns:
            data["hospital_potential"] = 0.0
        return _apply_settings_weights(data)

    @reactive.calc
    def current_states():
        return sorted(r_gdf()["state"].unique().tolist())

    @reactive.effect
    def _sync_state_dropdown():
        states = current_states()
        choices = {s: s for s in states}
        with reactive.isolate():
            current = input.state()
        preferred = "Florida"
        if current in states:
            selected = current
        elif preferred in states:
            selected = preferred
        else:
            selected = states[0] if states else None
        ui.update_select("state", choices=choices, selected=selected)
        ui.update_select("settings_map_state", choices=choices, selected=selected)
        rank_choices = choices
        ui.update_select("rank_filter", choices=rank_choices, selected=selected)

    @reactive.effect
    @reactive.event(input.rank_filter)
    def _sync_state_from_rank_filter():
        rf = input.rank_filter()
        if not rf:
            return
        with reactive.isolate():
            cur_state = input.state()
        if rf != cur_state:
            skip_reset.set(True)
            ui.update_select("state", selected=rf)

    @reactive.effect
    @reactive.event(input.settings_map_state)
    def _sync_state_from_settings_filter():
        sf = input.settings_map_state()
        if not sf:
            return
        with reactive.isolate():
            cur_state = input.state()
        if sf != cur_state:
            skip_reset.set(True)
            ui.update_select("state", selected=sf)

    @reactive.effect
    @reactive.event(input.state)
    def _reset():
        if skip_reset():
            skip_reset.set(False)
            return
        clicked_zip.set(None)

    @reactive.effect
    @reactive.event(input.map_click)
    def _on_click():
        data = input.map_click()
        if not data:
            return

        zipcode = str(data.get("zipcode", ""))
        action = data.get("action", "select")
        current = list(selected_zips())

        if action == "deselect":
            current = [z for z in current if z.get("zipcode") != zipcode]
            selected_zips.set(current)
            zip_limit_msg.set("")
            if clicked_zip() and clicked_zip().get("zipcode") == zipcode:
                clicked_zip.set(current[-1] if current else None)
        elif action == "limit_reached":
            zip_limit_msg.set("Limit reached")
        else:
            if len(current) >= MAX_SELECTED:
                zip_limit_msg.set("Limit reached")
                return
            if not any(z.get("zipcode") == zipcode for z in current):
                current.append(data)
                selected_zips.set(current)
            clicked_zip.set(data)
            zip_limit_msg.set("")

    @reactive.effect
    @reactive.event(input.map_state_change)
    def _on_map_state_change():
        new_state = input.map_state_change()
        if new_state:
            skip_reset.set(True)
            ui.update_select("state", selected=new_state)

    @reactive.effect
    @reactive.event(input.map_opacity)
    def _save_opacity():
        val = input.map_opacity()
        if val is not None:
            r_opacity.set(float(val))

    @reactive.effect
    @reactive.event(input.chip_remove)
    def _on_chip_remove():
        info = input.chip_remove()
        if not info:
            return
        zipcode = str(info.get("zipcode", ""))
        current = [z for z in selected_zips() if z.get("zipcode") != zipcode]
        selected_zips.set(current)
        zip_limit_msg.set("")
        if clicked_zip() and clicked_zip().get("zipcode") == zipcode:
            clicked_zip.set(current[-1] if current else None)

    @reactive.effect
    @reactive.event(input.settings_clear_selected_zips)
    def _clear_selected_zips_from_settings():
        selected_zips.set([])
        clicked_zip.set(None)
        focus_zip.set(None)
        zip_limit_msg.set("")
        map_version.set(map_version() + 1)

    @reactive.effect
    @reactive.event(input.leaderboard_click)
    def _on_leaderboard_click():
        info = input.leaderboard_click()
        if not info:
            return
        zipcode = str(info.get("zipcode", ""))
        state = str(info.get("state", ""))

        if state and state != input.state():
            focus_zip.set(zipcode)
            skip_reset.set(True)
            ui.update_select("state", selected=state)

    @render.ui
    def definitions_panel():
        data = r_gdf().copy()
        state_val = input.state()
        if state_val:
            data = data[data["state"] == state_val].copy()

        if data is None or len(data) == 0:
            return ui.HTML(
                '<p style="color:#1a1a1a;font-size:0.82rem;padding:10px 0;text-align:center;">'
                "No ZIP data available for definitions view.</p>"
            )

        data = data[data["hospital_potential"].fillna(0) > 0].copy()
        if len(data) == 0:
            return ui.HTML(
                '<p style="color:#1a1a1a;font-size:0.82rem;padding:10px 0;text-align:center;">'
                "No scored ZIP data available for definitions view.</p>"
            )

        def _norm(series, invert=False):
            s = pd.to_numeric(data[series], errors="coerce") if series in data.columns else None
            if s is None:
                return None
            valid = s.dropna()
            if len(valid) == 0:
                return None
            mn, mx = valid.min(), valid.max()
            if mx <= mn:
                out = s * 0 + 50.0
            else:
                out = (s - mn) / (mx - mn) * 100.0
            if invert:
                out = 100.0 - out
            return out

        dim_series = {}
        for dim, _ in _DIMENSION_META:
            numer = None
            denom = 0.0
            for col in _DIMENSION_INDICATORS.get(dim, []):
                if col not in data.columns:
                    continue
                v = _norm(col, invert=(col in _INVERTED_INDICATORS))
                if v is None:
                    continue
                numer = v if numer is None else numer + v
                denom += 1.0
            dim_series[dim] = (numer / denom) if numer is not None and denom > 0 else None

        fallback = pd.to_numeric(data["hospital_potential"], errors="coerce").fillna(0)
        data["attractiveness"] = dim_series["attractiveness"] if dim_series["attractiveness"] is not None else fallback
        data["ability_to_win"] = dim_series["ability_to_win"] if dim_series["ability_to_win"] is not None else fallback
        data["ripeness"] = dim_series["ripeness"] if dim_series["ripeness"] is not None else fallback
        data["economic_significance"] = (
            dim_series["economic_significance"] if dim_series["economic_significance"] is not None else fallback
        )

        # Apply dimension-level weighting (25 each keeps dimensions unchanged).
        dim_weights = {
            dim: max(0.0, float(_approved_dim_weights().get(dim, 25.0)))
            for dim, _ in _DIMENSION_META
        }
        avg_w = (sum(dim_weights.values()) / len(_DIMENSION_META)) if _DIMENSION_META else 25.0
        if avg_w <= 0:
            avg_w = 25.0
        for dim, _ in _DIMENSION_META:
            factor = dim_weights[dim] / avg_w
            data[dim] = (pd.to_numeric(data[dim], errors="coerce").fillna(0) * factor).clip(0, 100)

        w, h = 360, 268
        ml, mr, mt, mb = 44, 14, 16, 54
        pw, ph = w - ml - mr, h - mt - mb
        cell_w, cell_h = pw / 3.0, ph / 3.0

        bg_rects = (
            # High attractiveness row
            f'<rect x="{ml:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd08a"/>'
            f'<rect x="{ml+cell_w:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffab4a"/>'
            f'<rect x="{ml+2*cell_w:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ff7f00"/>'
            # Medium attractiveness row
            f'<rect x="{ml:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffe8c0"/>'
            f'<rect x="{ml+cell_w:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd08a"/>'
            f'<rect x="{ml+2*cell_w:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffab4a"/>'
            # Low attractiveness row
            f'<rect x="{ml:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffffff"/>'
            f'<rect x="{ml+cell_w:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffe8c0"/>'
            f'<rect x="{ml+2*cell_w:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd08a"/>'
        )

        def _x(v):
            return ml + (max(0.0, min(100.0, float(v))) / 100.0) * pw

        def _y(v):
            return mt + (1.0 - (max(0.0, min(100.0, float(v))) / 100.0)) * ph

        def _r(v):
            return 5.5 + (max(0.0, min(100.0, float(v))) / 100.0) * 12.5

        # Single framework point for the selected state (aggregate position).
        # Round aggregate coordinates to keep framework point visually stable across reloads.
        agg_attr = round(float(data["attractiveness"].fillna(0).mean()), 2)
        agg_win = round(float(data["ability_to_win"].fillna(0).mean()), 2)
        agg_ripe = round(float(data["ripeness"].fillna(0).mean()), 2)
        agg_econ = round(float(data["economic_significance"].fillna(0).mean()), 2)
        agg_score = round(float(data["hospital_potential"].fillna(0).mean()), 2)

        # Keep framework bubble aligned with the ripeness UI green.
        bubble_fill = "#22c55e"
        bubble_stroke = "#000000"

        cx, cy, rr = _x(agg_win), _y(agg_attr), _r(agg_econ)
        tip = html.escape(
            f"{state_val or 'Market'} | Attractiveness {agg_attr:.1f} | Ability to Win {agg_win:.1f} | "
            f"Ripeness {agg_ripe:.1f} | Economic Significance {agg_econ:.1f} | Avg Score {agg_score:.1f}"
        )
        circle = (
            f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr:.1f}" '
            f'fill="{bubble_fill}" stroke="{bubble_stroke}" stroke-width="1.2">'
            f"<title>{tip}</title></circle>"
        )

        svg = (
            f'<svg viewBox="0 0 {w} {h}" width="100%" height="250" role="img" '
            f'aria-label="Attractiveness vs Ability to Win bubble chart">'
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="#000000"/>'
            + bg_rects
            + f'<rect x="{ml}" y="{mt}" width="{pw:.1f}" height="{ph:.1f}" fill="none" stroke="#9ca3af" stroke-width="1"/>'
            f'<line x1="{ml+pw/3:.1f}" y1="{mt}" x2="{ml+pw/3:.1f}" y2="{mt+ph}" stroke="#6b7280" stroke-width="1"/>'
            f'<line x1="{ml+2*pw/3:.1f}" y1="{mt}" x2="{ml+2*pw/3:.1f}" y2="{mt+ph}" stroke="#6b7280" stroke-width="1"/>'
            f'<line x1="{ml}" y1="{mt+ph/3:.1f}" x2="{ml+pw}" y2="{mt+ph/3:.1f}" stroke="#6b7280" stroke-width="1"/>'
            f'<line x1="{ml}" y1="{mt+2*ph/3:.1f}" x2="{ml+pw}" y2="{mt+2*ph/3:.1f}" stroke="#6b7280" stroke-width="1"/>'
            + circle
            + f'<text x="{ml+pw/2:.1f}" y="{h-8}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle">ABILITY TO SUCCEED</text>'
            + f'<text x="0" y="{mt+ph/2:.1f}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle" transform="rotate(-90 0 {mt+ph/2:.1f})">MARKET ATTRACTIVENESS</text>'
            + f'<text x="{ml}" y="{mt+ph+16}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em">LOW</text>'
            + f'<text x="{ml+pw/2:.1f}" y="{mt+ph+16}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle">MED</text>'
            + f'<text x="{ml+pw}" y="{mt+ph+16}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">HIGH</text>'
            + f'<text x="{ml-8}" y="{mt+ph}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">LOW</text>'
            + f'<text x="{ml-8}" y="{mt+ph/2:.1f}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">MED</text>'
            + f'<text x="{ml-8}" y="{mt+8}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">HIGH</text>'
            + "</svg>"
        )

        excluded_for_tier1_defs = {
            "geometry",
            "hospital_potential",
            "entity_count",
            "hospital_count",
            "avg_entity_score",
            "avg_confidence",
            "state_key",
            "type",
            "action",
            "place_name",
        }
        available_cols = [
            c for c in data.columns
            if c not in excluded_for_tier1_defs and not str(c).startswith("_")
        ]
        pref_cols = [c for c in _TIER1_NUMERIC_INDICATORS if c in available_cols]
        other_cols = sorted(c for c in available_cols if c not in set(pref_cols))
        tier1_cols = pref_cols + other_cols
        tier1_defs = [
            (
                str(col),
                "Tier 1 factor from final_tier1_percentiles.parquet used in the Market tab."
            )
            for col in tier1_cols
        ]
        tier2_defs = []
        tier3_defs = []

        def _tier_defs_dropdown(title: str, rows: list[tuple[str, str]]) -> str:
            body = "".join(
                f'<div class="def-dim"><b>{html.escape(f)}</b>: {html.escape(d)}</div>'
                for f, d in rows
            )
            return (
                f'<details class="tier-dropdown" data-tier="defs_{title.lower().replace(" ", "_")}">'
                f'<summary class="tier-dropdown-summary">{title}</summary>'
                f'<div class="tier-dropdown-content">'
                f'<div class="def-body">{body}</div>'
                f'</div></details>'
            )

        html_block = (
            '<div class="def-card">'
            '<div class="def-title-lg">Framework</div>'
            '<div class="def-body" style="margin-top:15px;">'
            '<b>Framework:</b> The chart uses a 1-to-3 construct view where the vertical axis is Market Attractiveness and the horizontal axis is Ability to Succeed. Moving higher and farther right indicates a stronger opportunity profile. Color reflects Ripeness from red to yellow to green, and bubble size reflects Economic Significance from smaller to larger impact.'
            '</div>'
            f'<div style="margin-top:30px;">{svg}</div>'
            '</div>'
            '<hr class="def-section-divider"/>'
            '<div class="def-card">'
            '<div class="def-title">Constructs</div>'
            '<div class="def-body def-constructs-body">'
            '<div class="def-dim"><b>Market Attractiveness</b>: '
            'How structurally favorable the market is to pursue growth (demand, growth, economics, access, competitive intensity). '
            '<br><i>Interpretation:</i> Is this market worth being in or expanding in?</div>'
            '<div class="def-dim"><b>Ability to Succeed</b>: '
            'Relative capability to win and sustain advantage in that market (brand/network, outcomes, referral ties, cost position, feasibility). '
            '<br><i>Interpretation:</i> Can we realistically win here versus competitors given our assets and constraints?</div>'
            '<div class="def-dim"><b>Ripeness</b>: '
            'How actionable the opportunity is now, based on stage-gate signals (timing, readiness, and execution conditions). '
            '<br><i>Interpretation:</i> Is this opportunity ready to move now?</div>'
            '<div class="def-construct-ui">'
            '<span class="def-ball def-ball-red"></span>'
            '<span class="def-ball def-ball-yellow"></span>'
            '<span class="def-ball def-ball-green"></span>'
            '</div>'
            '<div class="def-dim"><b>Economic Significance</b>: '
            'Magnitude of value at stake if pursued successfully, used to scale diligence intensity and governance attention '
            '(revenue potential, cost/capital exposure, margin quality, portfolio impact). '
            '<br><i>Interpretation:</i> How important of a decision is this, and what analysis depth is warranted?</div>'
            '<div class="def-construct-ui">'
            '<span class="def-ball def-ball-red def-ball-sm"></span>'
            '<span class="def-ball def-ball-yellow def-ball-md"></span>'
            '<span class="def-ball def-ball-green def-ball-lg"></span>'
            '</div>'
            '</div>'
            '</div>'
            '<hr class="def-section-divider"/>'
            '<div class="def-card">'
            '<div class="def-title">Sub-constructs</div>'
            + _tier_defs_dropdown("Tier 1", tier1_defs)
            + _tier_defs_dropdown("Tier 2", tier2_defs)
            + _tier_defs_dropdown("Tier 3", tier3_defs)
            + '</div>'
            '<hr class="def-section-divider"/>'
            '<div class="def-card def-card-formula">'
            '<div class="def-subtitle def-score-title">Market Score</div>'
            '<div class="def-body"><b>Market Score</b>: ZIP-level composite score used for map coloring and ranking. It combines Attractiveness, Ability to Win, Ripeness, and Economic Significance across tiers.</div>'
            '<div class="def-formula">'
            '<div class="def-formula-eq">y = w1·Tier 1 + w2·Tier 2 + w3·Tier 3</div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 1</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 2</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 3</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '</div>'
            '<div class="def-ui-banner def-ui-banner-market">'
            '<div class="def-ui-banner-title">Market Score UI</div>'
            '<div class="def-score-legend">'
            '<span class="def-score-edge">LOW</span>'
            '<span class="def-score-gradient"></span>'
            '<span class="def-score-edge">HIGH</span>'
            '</div>'
            '</div>'
            '</div>'
            '<hr class="def-section-divider"/>'
            '<div class="def-card def-card-formula">'
            '<div class="def-subtitle def-score-title">Entity Score</div>'
            '<div class="def-body"><b>Entity Score</b>: Provider-level score used to compare entities consistently within and across ZIPs using the same construct framework.</div>'
            '<div class="def-formula">'
            '<div class="def-formula-eq">y = w1·Tier 1 + w2·Tier 2 + w3·Tier 3</div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 1</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 2</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 3</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '</div>'
            '<div class="def-ui-banner">'
            '<div class="def-ui-banner-title">Entity Marker UI</div>'
            '<div class="def-marker-row">'
            '<span class="def-marker-pin">'
            '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 30 42" aria-hidden="true">'
            '<path d="M15 1C7.8 1 2 6.8 2 14c0 10.5 13 26 13 26s13-15.5 13-26C28 6.8 22.2 1 15 1z" fill="#ff7f00" stroke="#000" stroke-width="1.5"/>'
            '<circle cx="15" cy="14" r="5" fill="#ffffff"/>'
            '</svg>'
            '</span>'
            '<span class="def-marker-text">Hospital / Entity marker used on the map layer</span>'
            '</div>'
            '</div>'
            '</div>'
            '</div>'
        )
        return ui.HTML(html_block)

    @render.ui
    def map_chips_bar():
        return ui.HTML(map_chips_html(selected_zips(), zip_limit_msg()))

    @render.ui
    def market_panel():
        sel = selected_zips()
        entities_for_zips = None
        if ENTITIES_DF is not None and sel:
            zips = [str(z.get("zipcode", "")) for z in sel]
            mask = ENTITIES_DF["zip"].astype(str).str.zfill(5).isin(zips)
            if mask.any():
                entities_for_zips = ENTITIES_DF[mask]
        return ui.HTML(market_tab_html(sel, entities_for_zips))

    @reactive.effect
    @reactive.event(input.agent_clear)
    def _clear_agent_thread():
        agent_messages.set([
            {
                "role": "assistant",
                "text": "Hi I’m Belfort, your market strategy assistant.",
            }
        ])

    @reactive.effect
    @reactive.event(input.agent_send)
    def _agent_send():
        def _state_in_query(q: str) -> str | None:
            ql = (q or "").lower()
            if "florida" in ql or re.search(r"\bfl\b", ql):
                return "Florida"
            if "alabama" in ql or re.search(r"\bal\b", ql):
                return "Alabama"
            if "georgia" in ql or re.search(r"\bga\b", ql):
                return "Georgia"
            return None

        def _deterministic_agent_reply(
            user_text: str,
            zip_records: list[dict],
            top_population: dict | None,
            all_rows: pd.DataFrame,
        ) -> str | None:
            q = (user_text or "").strip().lower()
            if not q:
                return None
            asks_market_potential = any(k in q for k in ("market potential", "hospital potential", "market score"))
            asks_best = any(k in q for k in ("highest", "best", "top", "stronger", "look into"))
            asks_population = "population" in q
            asks_highest = any(k in q for k in ("highest", "largest", "max", "most"))
            asks_population_growth = ("population growth" in q) or ("growth rate" in q)
            asks_selected = ("selected" in q) or ("these zip" in q) or ("those zip" in q) or ("of the zip" in q)
            if asks_selected and asks_market_potential and asks_best:
                if not zip_records:
                    return "No selected ZIP data is available right now."
                rows = pd.DataFrame(zip_records)
                if "hospital_potential" not in rows.columns:
                    return "Market-potential values are unavailable for the selected ZIPs."
                s = pd.to_numeric(rows["hospital_potential"], errors="coerce")
                if not s.notna().any():
                    return "Market-potential values are unavailable for the selected ZIPs."
                idx = s.idxmax()
                z = normalize_zip(str(rows.loc[idx, "zipcode"])) if "zipcode" in rows.columns else "N/A"
                st = str(rows.loc[idx, "state"]) if "state" in rows.columns else ""
                val = float(s.loc[idx])
                return f"For selected ZIPs, ZIP {z}{(' (' + st + ')') if st else ''} is strongest for market potential at {val:.2f}."
            # Let population-growth questions flow to the option-aware router.
            if asks_population_growth:
                return None
            if not (asks_population and asks_highest):
                return None
            if asks_selected:
                if not zip_records:
                    return "No selected ZIP data is available right now."
                if top_population is None:
                    return "Population data is unavailable for the selected ZIPs."

                z = normalize_zip(str(top_population.get("zipcode", "")))
                st = str(top_population.get("state", "")).strip()
                pop_val = top_population.get("total_population")
                try:
                    pop_num = int(float(pop_val))
                    pop_txt = f"{pop_num:,}"
                except Exception:
                    pop_txt = str(pop_val)
                state_txt = f" ({st})" if st else ""
                return (
                    f"From the current selected ZIPs in the dashboard/parquet-backed data, "
                    f"ZIP {z}{state_txt} has the highest total population at {pop_txt}."
                )

            if "total_population" not in all_rows.columns or len(all_rows) == 0:
                return None
            scoped = all_rows.copy()
            asked_state = _state_in_query(q)
            if asked_state and "state" in scoped.columns:
                scoped = scoped[scoped["state"].astype(str).str.lower() == asked_state.lower()].copy()
                if len(scoped) == 0:
                    return f"No rows are available for {asked_state} in the dashboard data."
            pop = pd.to_numeric(scoped["total_population"], errors="coerce")
            if not pop.notna().any():
                return None
            idx = pop.idxmax()
            z = normalize_zip(str(scoped.loc[idx, "zipcode"])) if "zipcode" in scoped.columns else "N/A"
            st = str(scoped.loc[idx, "state"]) if "state" in scoped.columns else ""
            pop_val = pop.loc[idx]
            try:
                pop_num = int(float(pop_val))
                pop_txt = f"{pop_num:,}"
            except Exception:
                pop_txt = str(pop_val)
            state_txt = f" ({st})" if st else ""
            scope_txt = f"Across ZIPs in {asked_state}, " if asked_state else "Across all ZIPs in the dashboard/parquet-backed data, "
            return scope_txt + f"ZIP {z}{state_txt} has the highest total population at {pop_txt}."

        def _clean_scalar(v):
            if pd.isna(v):
                return None
            if isinstance(v, (str, bool, int)):
                return v
            if isinstance(v, float):
                return round(v, 4)
            try:
                return float(v)
            except Exception:
                return str(v)

        msg = (input.agent_message() or "").strip()
        if not msg:
            return
        history = list(agent_messages())
        history.append({"role": "user", "text": msg})
        sel = selected_zips()
        sel_zip_list = [normalize_zip(str(z.get("zipcode", ""))) for z in sel if str(z.get("zipcode", "")).strip()]
        data = r_gdf().copy()
        selected_records = []
        highest_population = None
        available_states = sorted(data["state"].dropna().astype(str).unique().tolist()) if "state" in data.columns else []
        msa_count = int(data["msa_name"].dropna().astype(str).nunique()) if "msa_name" in data.columns else 0
        global_msa_preview = []
        if "msa_name" in data.columns and "hospital_potential" in data.columns:
            m = data.copy()
            m["hospital_potential"] = pd.to_numeric(m["hospital_potential"], errors="coerce").fillna(0)
            if "total_population" in m.columns:
                m["__w"] = pd.to_numeric(m["total_population"], errors="coerce").fillna(0)
            else:
                m["__w"] = 0.0
            if "state" in m.columns:
                grouped = (
                    m.groupby(["msa_name", "state"], dropna=True)
                    .apply(lambda g: ((g["hospital_potential"] * g["__w"]).sum() / g["__w"].sum()) if g["__w"].sum() > 0 else g["hospital_potential"].mean())
                    .reset_index(name="score")
                )
            else:
                grouped = (
                    m.groupby(["msa_name"], dropna=True)
                    .apply(lambda g: ((g["hospital_potential"] * g["__w"]).sum() / g["__w"].sum()) if g["__w"].sum() > 0 else g["hospital_potential"].mean())
                    .reset_index(name="score")
                )
            grouped = grouped.sort_values("score", ascending=False).head(60)
            for _, row in grouped.iterrows():
                global_msa_preview.append({
                    "msa_name": str(row.get("msa_name", "")),
                    "state": str(row.get("state", "")) if "state" in grouped.columns else "",
                    "score": _clean_scalar(row.get("score")),
                })
        if len(data) > 0 and sel_zip_list:
            rows = data.copy()
            rows["zip_key"] = rows["zipcode"].map(normalize_zip)
            rows = rows[rows["zip_key"].isin(sel_zip_list)].copy()
            order = {z: i for i, z in enumerate(sel_zip_list)}
            rows["__ord"] = rows["zip_key"].map(lambda z: order.get(z, 9999))
            rows = rows.sort_values("__ord")
            drop_cols = {"geometry", "__ord"}
            for _, r in rows.iterrows():
                rec = {}
                for c in rows.columns:
                    if c in drop_cols:
                        continue
                    rec[c] = _clean_scalar(r[c])
                selected_records.append(rec)
            if "total_population" in rows.columns and len(rows) > 0:
                pop = pd.to_numeric(rows["total_population"], errors="coerce")
                if pop.notna().any():
                    top_idx = pop.idxmax()
                    highest_population = {
                        "zipcode": normalize_zip(str(rows.loc[top_idx, "zipcode"])),
                        "state": str(rows.loc[top_idx, "state"]) if "state" in rows.columns else "",
                        "total_population": _clean_scalar(pop.loc[top_idx]),
                    }
        context = {
            "tier1_data_source": "backend/data/raw/tier1/final_tier1_percentiles.parquet",
            "weights": {tier: float(_approved_tier_weights().get(tier, _DEFAULT_TIER_WEIGHTS.get(tier, 0.0))) for tier, _ in _TIER_META},
            "selected_option": str(_approved_score_option() or DEFAULT_SCORE_COLUMN),
            "available_states": available_states,
            "row_count": int(len(data)),
            "zip_count": int(data["zipcode"].nunique()) if "zipcode" in data.columns else int(len(data)),
            "msa_count": msa_count,
            "global_msa_preview": global_msa_preview,
        }
        prior_turns = [
            m for m in history[:-1]
            if str(m.get("role", "")).lower() in {"user", "assistant"}
        ]
        try:
            deterministic_reply = _deterministic_agent_reply(msg, selected_records, highest_population, data)
            if deterministic_reply is not None:
                reply = deterministic_reply
            else:
                routed_reply = try_handle_query(data, msg)
                if routed_reply is not None:
                    reply = routed_reply
                else:
                    reply = query_agent(
                        user_message=msg,
                        history=prior_turns,
                        context=context,
                        timeout_seconds=40,
                    )
        except Exception as e:
            reply = f"Agent connection failed: {e}"
        history.append({"role": "assistant", "text": reply})
        agent_messages.set(history)
        ui.update_text("agent_message", value="")

    @render.ui
    def settings_selected_zips():
        sel = selected_zips()
        if not sel:
            return ui.HTML('<div class="settings-selected-zips">None</div>')
        rows = []
        for z in sel:
            zip_raw = str(z.get("zipcode", "")).strip()
            if not zip_raw:
                continue
            zip_code = normalize_zip(zip_raw)
            state = str(z.get("state", "")).strip()
            row = f"{html.escape(zip_code)}{(' - ' + html.escape(state)) if state else ''}"
            rows.append(row)
        if not rows:
            return ui.HTML('<div class="settings-selected-zips">None</div>')
        lines = "".join(f'<div class="settings-selected-zips-line">{r}</div>' for r in rows)
        return ui.HTML(f'<div class="settings-selected-zips">{lines}</div>')

    @render.ui
    def agent_thread():
        rows = []
        for m in agent_messages():
            role = str(m.get("role", "assistant"))
            text = html.escape(str(m.get("text", ""))).replace("\n", "<br>")
            bubble_cls = "agent-msg-user" if role == "user" else "agent-msg-assistant"
            label = "You" if role == "user" else "Belfort"
            rows.append(
                f'<div class="agent-msg {bubble_cls}">'
                f'<div class="agent-msg-label">{label}</div>'
                f'<div class="agent-msg-text">{text}</div>'
                '</div>'
            )
        return ui.HTML('<div class="agent-thread">' + "".join(rows) + "</div>")

    @reactive.effect
    @reactive.event(input.settings_reset_weights)
    def _reset_settings_weights():
        _approved_score_option.set(DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in _SCORE_OPTION_CHOICES else "attractiveness_score_opt2")
        _approved_tier_weights.set(dict(_DEFAULT_TIER_WEIGHTS))
        _approved_option_component_weights.set(_default_option_component_weights())
        _settings_weights_feedback.set("")
        _settings_feedback_set_at.set(0.0)
        _settings_adjusting.set(True)
        ui.update_radio_buttons(
            "settings_score_option",
            selected=DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in _SCORE_OPTION_CHOICES else "attractiveness_score_opt2",
        )
        _settings_adjusting.set(False)

    @reactive.effect
    @reactive.event(input.settings_approve_weights)
    def _approve_settings_weights():
        approved = dict(_DEFAULT_TIER_WEIGHTS)
        selected_option = str(input.settings_score_option() or DEFAULT_SCORE_COLUMN).strip()
        if selected_option not in _SCORE_OPTION_CHOICES:
            selected_option = DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in _SCORE_OPTION_CHOICES else "attractiveness_score_opt2"
        component_defaults = _default_option_component_weights()
        approved_components = _approved_option_component_weights().copy()
        option_components = component_defaults.get(selected_option, {})
        option_values: dict[str, float] = {}
        for component_col, default_weight in option_components.items():
            slider_id = _option_component_slider_id(selected_option, component_col)
            option_values[component_col] = max(0.0, _safe_slider_input(input, slider_id, default_weight))
        total_weight = sum(option_values.values())
        if int(round(total_weight)) != 100:
            _settings_weights_feedback.set(
                f"Tier 1 option weights must total 100 before approval. Current total: {int(round(total_weight))}."
            )
            _settings_feedback_set_at.set(time.time())
            return
        if option_values:
            approved_components[selected_option] = option_values
            _approved_option_component_weights.set(approved_components)
        _approved_tier_weights.set(approved)
        _approved_score_option.set(selected_option)
        _settings_weights_feedback.set("")
        _settings_feedback_set_at.set(0.0)

    @render.ui
    def settings_weights_feedback():
        msg = str(_settings_weights_feedback() or "").strip()
        if not msg:
            return ui.HTML("")
        return ui.HTML(f'<div class="settings-note settings-weights-feedback">{html.escape(msg)}</div>')

    @reactive.effect
    def _clear_settings_feedback_after_delay():
        msg = str(_settings_weights_feedback() or "").strip()
        if not msg:
            return
        set_at = float(_settings_feedback_set_at() or 0.0)
        if set_at <= 0:
            return
        elapsed = max(0.0, time.time() - set_at)
        remaining = 2.0 - elapsed
        if remaining > 0:
            reactive.invalidate_later(remaining)
            return
        if str(_settings_weights_feedback() or "").strip() == msg:
            _settings_weights_feedback.set("")
            _settings_feedback_set_at.set(0.0)

    @render.ui
    def settings_assignment_note():
        auto_count = len(_AUTO_TO_ATTR)
        note = (
            f"{auto_count} indicator(s) had no direct keyword match and were auto-assigned to "
            "Market Attractiveness."
        )
        return ui.HTML(
            '<div class="settings-note">'
            '<b>Indicator assignment check:</b> all Tier 1 numeric indicators are assigned '
            f"to one of the 4 dimensions. {html.escape(note)}"
            '</div>'
        )

    @render.ui
    def settings_option_weight_summary():
        selected_option = str(input.settings_score_option() or DEFAULT_SCORE_COLUMN).strip()
        if selected_option not in SCORE_DEFINITIONS:
            selected_option = DEFAULT_SCORE_COLUMN
        score_def = SCORE_DEFINITIONS.get(selected_option, {})
        components = score_def.get("components", {})
        if not components:
            return ui.HTML("")
        approved_map = _approved_option_component_weights().get(selected_option, {})
        rows = []
        for component_col, meta in components.items():
            label = str(meta.get("label", "")).strip() or "Factor"
            w = float(approved_map.get(component_col, float(meta.get("weight", 0.0)) * 100.0))
            rows.append(f"{html.escape(label)}: {w:.0f}%")
        summary = " | ".join(rows)
        return ui.HTML(
            '<div class="settings-note settings-option-info" style="margin-top:0;margin-bottom:10px;">'
            f'<b>{html.escape(_SCORE_OPTION_CHOICES.get(selected_option, selected_option))} weights:</b> '
            f'{html.escape(summary)}'
            '</div>'
        )

    @render.ui
    def settings_tier1_component_sliders():
        selected_option = str(input.settings_score_option() or DEFAULT_SCORE_COLUMN).strip()
        if selected_option not in SCORE_DEFINITIONS:
            selected_option = DEFAULT_SCORE_COLUMN
        score_def = SCORE_DEFINITIONS.get(selected_option, {})
        components = score_def.get("components", {})
        if not components:
            return ui.HTML("")
        approved_map = _approved_option_component_weights().get(selected_option, {})
        sliders = []
        for component_col, meta in components.items():
            label = str(meta.get("label", "")).strip() or component_col
            default_v = int(round(float(approved_map.get(component_col, float(meta.get("weight", 0.0)) * 100.0))))
            sliders.append(
                ui.div(
                    ui.input_slider(
                        _option_component_slider_id(selected_option, component_col),
                        label,
                        0,
                        100,
                        default_v,
                        step=1,
                    ),
                    class_="settings-tier-component-card",
                )
            )
        return ui.div(*sliders, class_="settings-tier-component-grid")

    @render.ui
    def rank_count_title():
        data = r_gdf()
        if data is None or len(data) == 0:
            return ui.HTML("")
        ranked = data[data["hospital_potential"] > 0].copy()
        ranked["zip_key"] = ranked["zipcode"].map(normalize_zip)
        state_filter = input.rank_filter() or input.state()
        if state_filter:
            ranked = ranked[ranked["state"] == state_filter]
        total_count = len(ranked)
        query = input.zip_search().strip()
        if query:
            matched = ranked[ranked["zip_key"].str.startswith(query)]
            return ui.HTML(
                f'<p style="font-size:1.1rem;color:#ff7f00;letter-spacing:0.01em;'
                f'font-family:Open Sans,Segoe UI,Tahoma,Arial,sans-serif;'
                f'font-weight:700;margin:4px 8px 10px 18px;padding:0;">'
                f'{len(matched):,} Zip Codes</p>'
            )
        return ui.HTML(
            f'<p style="font-size:1.1rem;color:#ff7f00;letter-spacing:0.01em;'
            f'font-family:Open Sans,Segoe UI,Tahoma,Arial,sans-serif;'
            f'font-weight:700;margin:4px 8px 10px 18px;padding:0;">'
            f'{total_count:,} Zip Codes</p>'
        )

    @render.ui
    def leaderboard():
        data = r_gdf()
        if data is None or len(data) == 0:
            return ui.HTML(
                '<p style="color:#1a1a1a;font-size:0.8rem;text-align:center;">'
                'No data available.</p>'
            )

        cols = ["zipcode", "state", "hospital_potential"]
        ranked = data[cols].copy()
        ranked["zip_key"] = ranked["zipcode"].map(normalize_zip)
        ranked = ranked[ranked["hospital_potential"] > 0]
        state_filter = input.rank_filter() or input.state()
        if state_filter:
            ranked = ranked[ranked["state"] == state_filter]
        ranked = ranked.sort_values("hospital_potential", ascending=False).reset_index(drop=True)

        query = input.zip_search().strip()
        if query:
            ranked = ranked[ranked["zip_key"].str.startswith(query)]

        sel_zip_set = selected_zip_set(selected_zips())
        if len(sel_zip_set) >= 5 and len(ranked) > 0:
            ranked = prioritize_selected_rows(ranked, sel_zip_set, threshold=5)

        ranked = ranked.reset_index(drop=True)
        ranked["rank"] = ranked.index + 1

        total_count = len(ranked)
        if total_count == 0:
            msg = f'No ZIP codes matching "{query}"' if query else "No scored ZIP codes for this filter."
            return ui.HTML(
                f'<p style="color:#1a1a1a;font-size:0.8rem;text-align:center;">{msg}</p>'
            )

        show = ranked

        th_bg = "background:#000000;"
        header = (
            '<table style="width:96%;margin:0 auto;font-size:0.78rem;color:#1a1a1a;'
            'border-collapse:collapse;">'
            '<thead><tr style="position:sticky;top:0;z-index:2;">'
            f'<th style="text-align:center;padding:4px 10px;color:#ffffff;'
            f'font-weight:600;font-size:0.72rem;border-bottom:1px solid #ffffff;{th_bg}">#</th>'
            f'<th style="text-align:left;padding:4px 10px;color:#ffffff;'
            f'font-weight:600;font-size:0.72rem;border-bottom:1px solid #ffffff;{th_bg}">ZIP</th>'
            f'<th style="text-align:left;padding:4px 10px;color:#ffffff;'
            f'font-weight:600;font-size:0.72rem;border-bottom:1px solid #ffffff;{th_bg}">State</th>'
            f'<th style="text-align:right;padding:4px 25px 4px 10px;color:#ffffff;'
            f'font-weight:600;font-size:0.72rem;border-bottom:1px solid #ffffff;{th_bg}">Market Score</th>'
            '</tr></thead><tbody>'
        )

        parts = []
        for rank, zc, st, score in zip(
            show["rank"], show["zip_key"], show["state"], show["hospital_potential"]
        ):
            rank = int(rank)
            score = float(score)
            score_color = COLORMAP(score)
            border = "border-top:1px solid #ffffff;" if rank > 1 else ""
            rc = (f'<span style="display:inline-flex;align-items:center;'
                  f'justify-content:center;width:22px;height:22px;'
                  f'border-radius:50%;background:#000000;'
                  f'border:1px solid #ffffff;'
                  f'color:#ffffff;font-size:0.6rem;font-weight:700;">{rank}</span>')
            zs = "font-weight:600;color:#ffffff;"
            ss = f"font-weight:700;--score-color:{score_color};"

            parts.append(
                f'<tr class="leaderboard-zip" data-zip="{zc}" data-state="{st}"'
                f' style="cursor:pointer;" title="Go to {zc}">'
                f'<td style="padding:6px 16px 10px 10px;{border}line-height:1;text-align:center;">'
                f'{rc}</td>'
                f'<td class="rank-zip-cell" style="padding:6px 10px 10px 14px;{border}{zs}">{zc}</td>'
                f'<td class="rank-state-cell" style="padding:6px 10px 10px 10px;{border}color:#ffffff;font-size:0.72rem;">{st}</td>'
                f'<td class="rank-score-cell" style="padding:6px 25px 10px 10px;{border}text-align:right;{ss}">{score:.1f}</td>'
                f'</tr>'
            )

        return ui.HTML(f'{header}{"".join(parts)}</tbody></table>')

    @render.ui
    def map_container():
        state_val = input.state()
        _ = map_version()
        show_market_layer = bool(input.settings_show_market_layer())
        show_entities_layer = bool(input.settings_show_entities_layer())
        if not state_val:
            states = current_states()
            state_val = states[0] if states else None
        if not state_val:
            return ui.HTML("")

        with reactive.isolate():
            opacity_val = r_opacity()
            data = r_gdf()
            fz = focus_zip()

        filtered = data[data["state"] == state_val]
        if len(filtered) == 0:
            return ui.HTML(
                "<p style='color:#888;text-align:center;padding:40px;'>No data.</p>"
            )

        filtered_zip_set = set(filtered["zipcode"].map(normalize_zip).tolist())
        if fz and normalize_zip(fz) in filtered_zip_set:
            with reactive.isolate():
                focus_zip.set(None)
        else:
            fz = None

        with reactive.isolate():
            sel = [str(z.get("zipcode", "")) for z in selected_zips()]

        state_entities = None
        if ENTITIES_DF is not None:
            abbr = _STATE_TO_ABBR.get(state_val, state_val)
            mask = ENTITIES_DF["state"].isin([state_val, abbr])
            ent = ENTITIES_DF[mask]
            if len(ent) > 0:
                state_entities = ent

        return ui.HTML(build_map(
            filtered, opacity_val,
            focus_zip=fz, selected_zips=sel,
            entities=state_entities,
            all_states=current_states(),
            current_state=state_val,
            show_market_layer=show_market_layer,
            show_entities_layer=show_entities_layer,
        ))


# App
app = App(app_ui, server, static_assets=WWW_DIR)