"""Reference / definitions tab HTML for Dash."""

from __future__ import annotations

import colorsys
import html

import pandas as pd

from frontend.config import (
    BRAND_ORANGE_HEX,
    MAP_SCORE_ORANGE_RGB,
    score_legend_gradient_css,
    ui_chrome_background,
)
from frontend.modules.scoring_core import (
    DIMENSION_INDICATORS,
    DIMENSION_META,
    INVERTED_INDICATORS,
)


def _pretty_indicator_name(ind: str) -> str:
    return ind.replace("_", " ").title()


def _white_to_brand_orange_hex(t: float) -> str:
    """Interpolate white → #F37021 (HSV ramp, same hue logic as ZIP score strip)."""
    t = max(0.0, min(1.0, float(t)))
    r, g, b = (
        MAP_SCORE_ORANGE_RGB[0] / 255.0,
        MAP_SCORE_ORANGE_RGB[1] / 255.0,
        MAP_SCORE_ORANGE_RGB[2] / 255.0,
    )
    h, s_end, v_end = colorsys.rgb_to_hsv(r, g, b)
    s = t * s_end
    v = 1.0 - t * (1.0 - v_end)
    rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
    return (
        f"#{int(round(rr * 255)):02x}{int(round(gg * 255)):02x}{int(round(bb * 255)):02x}"
    )


def _framework_cell_fill_bl_to_tr(col: int, row: int) -> str:
    """3×3 grid: row 0 = top, col 0 = left; bottom-left white → top-right #F37021."""
    t = (col + (2 - row)) / 4.0
    return _white_to_brand_orange_hex(t)


REFERENCE_FRAMEWORK_INTRO_BODY = (
    "<b>Framework:</b> The framework is the end-to-end scoring pipeline used to move from raw indicators to final market decisions. "
    "Each <b>construct</b> is a top-level decision dimension (Market Attractiveness, Ability to Succeed, Ripeness, Economic Significance). "
    "Each construct is built from <b>sub-constructs</b> that are organized by tiers (Tier 1, Tier 2, Tier 3). "
    "Formulas are applied tier-by-tier to produce sub-construct scores, then construct scores, then ZIP score, and finally the population-weighted Average Market Score. "
    "The chart visualizes this pipeline summary: vertical axis is Market Attractiveness, horizontal axis is Ability to Succeed, bubble color reflects Ripeness, and bubble size reflects Economic Significance. "
    "The best scenario is a big green bubble in the top-right quadrant."
)


def render_reference_framework_chart_svg(
    attractiveness: float,
    ability_to_win: float,
    ripeness: float,
    economic_significance: float,
    *,
    tooltip: str | None = None,
    bubble_fill: str | None = None,
) -> str:
    """3×3 framework chart matching the Reference tab (gradient cells, black grid, typography).

    If ``bubble_fill`` is set (e.g. Selection tab), it overrides RYG ripeness colors for the bubble.
    """
    w, h = 304, 222
    ml, mr, mt, mb = 54, 10, 16, 58
    pw, ph = w - ml - mr, h - mt - mb
    cell_w, cell_h = pw / 3.0, ph / 3.0
    y_x_tick = mt + ph + 15
    y_bottom_title = h - 7
    lx = ml - 5

    bg_rects = "".join(
        f'<rect x="{ml + (i % 3) * cell_w:.1f}" y="{mt + (i // 3) * cell_h:.1f}" '
        f'width="{cell_w:.1f}" height="{cell_h:.1f}" '
        f'fill="{_framework_cell_fill_bl_to_tr(i % 3, i // 3)}"/>'
        for i in range(9)
    )

    def _x(v: float) -> float:
        return ml + (max(0.0, min(100.0, float(v))) / 100.0) * pw

    def _y(v: float) -> float:
        return mt + (1.0 - (max(0.0, min(100.0, float(v))) / 100.0)) * ph

    def _r(v: float) -> float:
        return 5.5 + (max(0.0, min(100.0, float(v))) / 100.0) * 12.5

    rp = max(0.0, min(100.0, float(ripeness)))
    if bubble_fill is not None and str(bubble_fill).strip():
        bubble_fill_use = str(bubble_fill).strip()
    else:
        # RYG vs ripeness score: 0–33 red, 34–66 yellow/amber, 67–100 green
        if rp >= 67:
            bubble_fill_use = "#22c55e"
        elif rp >= 34:
            bubble_fill_use = "#f59e0b"
        else:
            bubble_fill_use = "#ef4444"
    chart_bg = ui_chrome_background()
    bubble_stroke = "#000000"
    _svg_ff = "Open Sans, Segoe UI, Tahoma, Arial, sans-serif"

    cx = _x(ability_to_win)
    cy = _y(attractiveness)
    rr = min(16.0, max(10.0, _r(economic_significance) * 0.55))

    tip = html.escape(tooltip) if tooltip else ""
    circle = (
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{rr:.1f}" '
        f'fill="{bubble_fill_use}" stroke="{bubble_stroke}" stroke-width="0.65">'
        + (f"<title>{tip}</title>" if tip else "")
        + "</circle>"
    )

    _t = (
        f'fill="#ffffff" font-family="{_svg_ff}" font-size="9" font-weight="600" '
        'letter-spacing="0.03em"'
    )
    _t_y = (
        f'fill="#ffffff" font-family="{_svg_ff}" font-size="7.25" font-weight="600" '
        'letter-spacing="0.06em"'
    )
    cy_axis = mt + ph / 2.0
    return (
        f'<svg viewBox="0 0 {w} {h}" width="100%" role="img" '
        f'aria-label="Attractiveness vs Ability to Win bubble chart">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="{chart_bg}"/>'
        + bg_rects
        + f'<rect x="{ml}" y="{mt}" width="{pw:.1f}" height="{ph:.1f}" fill="none" stroke="#000000" stroke-width="0.65"/>'
        f'<line x1="{ml+pw/3:.1f}" y1="{mt}" x2="{ml+pw/3:.1f}" y2="{mt+ph}" stroke="#000000" stroke-width="0.65"/>'
        f'<line x1="{ml+2*pw/3:.1f}" y1="{mt}" x2="{ml+2*pw/3:.1f}" y2="{mt+ph}" stroke="#000000" stroke-width="0.65"/>'
        f'<line x1="{ml}" y1="{mt+ph/3:.1f}" x2="{ml+pw}" y2="{mt+ph/3:.1f}" stroke="#000000" stroke-width="0.65"/>'
        f'<line x1="{ml}" y1="{mt+2*ph/3:.1f}" x2="{ml+pw}" y2="{mt+2*ph/3:.1f}" stroke="#000000" stroke-width="0.65"/>'
        + circle
        + f'<text x="{ml+pw/2:.1f}" y="{y_bottom_title}" {_t} text-anchor="middle">ABILITY TO SUCCEED</text>'
        + f'<text x="11" y="{cy_axis:.1f}" {_t_y} text-anchor="middle" '
        f'transform="rotate(-90 11 {cy_axis:.1f})">MARKET ATTRACTIVENESS</text>'
        + f'<text x="{ml}" y="{y_x_tick}" {_t}>LOW</text>'
        + f'<text x="{ml+pw/2:.1f}" y="{y_x_tick}" {_t} text-anchor="middle">MED</text>'
        + f'<text x="{ml+pw}" y="{y_x_tick}" {_t} text-anchor="end">HIGH</text>'
        + f'<text x="{lx}" y="{mt+ph}" {_t} text-anchor="end">LOW</text>'
        + f'<text x="{lx}" y="{cy_axis:.1f}" {_t} text-anchor="end">MED</text>'
        + f'<text x="{lx}" y="{mt+10}" {_t} text-anchor="end">HIGH</text>'
        + "</svg>"
    )


def wrap_definitions_srcdoc(body_html: str) -> str:
    """Wrap Reference HTML in a minimal document for iframe srcDoc.

    dcc.Markdown + markdown-it (Dash 2.18) sanitizes away most of this markup
    (<details>, <svg>, nested blocks), so the Reference tab renders nothing.
    An iframe renders the string as real HTML.
    """
    chrome = ui_chrome_background()
    css = (
        f"html{{scrollbar-gutter:stable;overflow-y:scroll;scrollbar-width:thin;scrollbar-color:#ffffff #000000;}}"
        "html::-webkit-scrollbar{width:8px;background:#000000;}"
        "html::-webkit-scrollbar-track{background:#000000!important;}"
        "html::-webkit-scrollbar-thumb{background:#ffffff!important;border-radius:4px!important;}"
        f"body{{margin:0;padding:12px 8px 28px 14px;background:{chrome};color:#e8e8e8;"
        "font-family:'Open Sans','Segoe UI',Tahoma,Arial,sans-serif;font-size:12px;line-height:1.45;"
        "scrollbar-width:thin;scrollbar-color:#ffffff #000000;box-sizing:border-box;}}"
        "body::-webkit-scrollbar{width:8px;background:#000000;}"
        "body::-webkit-scrollbar-track{background:#000000!important;}"
        "body::-webkit-scrollbar-thumb{background:#ffffff!important;border-radius:4px!important;min-height:40px!important;}"
        "body::-webkit-scrollbar-thumb:hover{background:#f0f0f0!important;}"
        ".def-card{margin-bottom:46px;padding-bottom:4px;}"
        f".def-title,.def-title-lg,.def-subtitle,.def-ui-banner-title{{"
        f"color:{BRAND_ORANGE_HEX};font-weight:800;}}"
        ".def-score-title{color:#ffffff!important;font-weight:700!important;}"
        ".def-title,.def-title-lg{font-size:1.1rem;margin:0 0 16px;letter-spacing:0.02em;}"
        ".def-body,.def-body li,.def-tier-li{color:#e0e0e0;font-size:0.72rem;line-height:1.45;}"
        ".def-body b,.def-dim b{color:#fff;}"
        ".def-empty-msg{color:#e8e8e8;text-align:center;padding:12px 0;}"
        ".def-formula-eq{font-weight:700;margin:8px 0;color:#fff;}"
        ".def-formula-row{margin:4px 0;font-size:0.7rem;}"
        ".def-chip{display:inline-flex;align-items:center;justify-content:center;box-sizing:border-box;"
        "min-width:3.25rem;min-height:1.4rem;padding:2px 6px;margin-right:8px;background:#1a1a1a;"
        "border:1px solid #555;color:#ffab4a;font-size:0.62rem;vertical-align:middle;}"
        "details.tier-dropdown[data-tier^=\"defs_\"],details.tier-dropdown[data-tier^=\"sc_\"]{"
        "margin:12px 0 0;padding:10px 0 0;border-top:1px solid #ffffff;border-bottom:none;}"
        "details.tier-dropdown[data-tier^=\"defs_\"]:first-of-type,details.tier-dropdown[data-tier^=\"sc_\"]:first-of-type{"
        "margin-top:6px;}"
        "details.tier-dropdown[data-tier=\"tier1\"],details.tier-dropdown[data-tier=\"tier2\"],"
        "details.tier-dropdown[data-tier=\"tier3\"]{margin:8px 0 0;padding:6px 0 0;"
        "border-top:1px solid rgba(255,255,255,0.45);border-bottom:none;}"
        "summary.tier-dropdown-summary{cursor:pointer;color:#fff;padding:8px 0;font-size:0.75rem;font-weight:600;}"
        ".tier-dropdown-content{padding:4px 0 10px 8px;}"
        "hr.def-section-divider{display:none!important;margin:0!important;padding:0!important;border:none!important;}"
        ".def-constructs-body .def-dim{margin-bottom:26px;line-height:1.55;}"
        ".def-constructs-body .def-dim:last-of-type{margin-bottom:14px;}"
        ".def-construct-ui{display:flex;gap:16px;align-items:center;justify-content:center;"
        "margin:14px auto 24px;flex-wrap:wrap;width:100%;box-sizing:border-box;}"
        ".def-ball{display:inline-block;border-radius:50%;border:1px solid #000000;flex-shrink:0;"
        "box-sizing:border-box;}"
        ".def-ball-red{background:#dc2626;}.def-ball-yellow{background:#eab308;}.def-ball-green{background:#22c55e;}"
        ".def-ball-sm{width:10px;height:10px;}.def-ball-md{width:16px;height:16px;}.def-ball-lg{width:22px;height:22px;}"
        ".def-framework-chart-wrap{max-width:min(100%,288px);margin:18px auto 0;overflow:hidden;}"
        ".def-framework-chart-wrap svg{max-width:100%;height:auto;display:block;overflow:visible;}"
        ".def-ui-banner{border:1px solid #444;padding:8px;margin:8px 0;background:#111;}"
        ".def-ms-legend-title{color:#ffffff!important;font-weight:700!important;font-size:0.72rem!important;"
        "margin:24px 0 8px!important;padding:0!important;letter-spacing:0.02em!important;"
        "text-align:left!important;}"
        ".def-ms-legend-stack{display:flex!important;flex-direction:column!important;align-items:stretch!important;"
        "gap:5px!important;padding:0!important;margin:0!important;box-sizing:border-box!important;"
        "width:100%!important;max-width:min(100%,440px)!important;}"
        ".def-ms-legend-labels{display:flex!important;flex-direction:row!important;justify-content:space-between!important;"
        "align-items:center!important;width:100%!important;box-sizing:border-box!important;}"
        ".def-ms-legend-edge{color:#e0e0e0!important;font-size:0.62rem!important;font-weight:600!important;"
        "letter-spacing:0.04em!important;text-transform:uppercase!important;}"
        ".def-ms-legend-strip{height:10px!important;min-height:10px!important;width:100%!important;"
        "border:none!important;border-radius:0!important;display:block!important;box-sizing:border-box!important;}"
        ".def-score-gradient{display:inline-block;height:8px;min-width:120px;vertical-align:middle;}"
        "svg{max-width:100%;height:auto;display:block;}"
        "ul{margin:6px 0;padding-left:18px;}a{color:#ffab4a;}"
    )
    return (
        '<!DOCTYPE html><html><head><meta charset="utf-8"/>'
        f"<style>{css}</style></head><body>"
        + body_html
        + "</body></html>"
    )


def build_definitions_html(
    data: pd.DataFrame,
    state_val: str | None,
    approved_dim_weights: dict[str, float],
    approved_ccw: dict,
    default_ccw: dict,
) -> str:
    if state_val:
        data = data[data["state"] == state_val].copy()

    if data is None or len(data) == 0:
        return (
            '<p class="def-empty-msg" style="font-size:0.82rem;padding:10px 0;text-align:center;">'
            "No ZIP data available for definitions view.</p>"
        )

    if "hospital_potential" not in data.columns:
        data = data.copy()
        data["hospital_potential"] = 0.0

    hp = pd.to_numeric(data["hospital_potential"], errors="coerce").fillna(0)
    pos = data[hp > 0]
    if len(pos) > 0:
        data = pos.copy()
    # If every ZIP is unscored (0 / NaN), still show full Reference copy + chart using fallbacks.

    def _norm(series: str, invert: bool = False):
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
    for dim, _ in DIMENSION_META:
        numer = None
        denom_ch = 0.0
        for col in DIMENSION_INDICATORS.get(dim, []):
            if col not in data.columns:
                continue
            v = _norm(col, invert=(col in INVERTED_INDICATORS))
            if v is None:
                continue
            numer = v if numer is None else numer + v
            denom_ch += 1.0
        dim_series[dim] = (numer / denom_ch) if numer is not None and denom_ch > 0 else None

    fallback = pd.to_numeric(data["hospital_potential"], errors="coerce").fillna(0)
    data["attractiveness"] = dim_series["attractiveness"] if dim_series["attractiveness"] is not None else fallback
    data["ability_to_win"] = dim_series["ability_to_win"] if dim_series["ability_to_win"] is not None else fallback
    data["ripeness"] = dim_series["ripeness"] if dim_series["ripeness"] is not None else fallback
    data["economic_significance"] = (
        dim_series["economic_significance"] if dim_series["economic_significance"] is not None else fallback
    )

    dim_weights = {
        dim: max(0.0, float(approved_dim_weights.get(dim, 25.0)))
        for dim, _ in DIMENSION_META
    }
    avg_w = (sum(dim_weights.values()) / len(DIMENSION_META)) if DIMENSION_META else 25.0
    if avg_w <= 0:
        avg_w = 25.0
    for dim, _ in DIMENSION_META:
        factor = dim_weights[dim] / avg_w
        data[dim] = (pd.to_numeric(data[dim], errors="coerce").fillna(0) * factor).clip(0, 100)

    agg_attr = round(float(data["attractiveness"].fillna(0).mean()), 2)
    agg_win = round(float(data["ability_to_win"].fillna(0).mean()), 2)
    agg_ripe = round(float(data["ripeness"].fillna(0).mean()), 2)
    agg_econ = round(float(data["economic_significance"].fillna(0).mean()), 2)
    agg_score = round(float(data["hospital_potential"].fillna(0).mean()), 2)

    tip = (
        f"{state_val or 'Market'} | Attractiveness {agg_attr:.1f} | Ability to Win {agg_win:.1f} | "
        f"Ripeness {agg_ripe:.1f} | Economic Significance {agg_econ:.1f} | Avg Score {agg_score:.1f}"
    )
    # Illustrative chart: green bubble, top-right quadrant (high attractiveness + ability; high ripeness).
    svg = render_reference_framework_chart_svg(88.0, 88.0, 85.0, 78.0, tooltip=tip)

    indicator_defs = {
        "age_65_plus_pct": "Service demand signal from senior population share.",
        "population_growth_rate_2yr": "Near-term demand growth trend over two years.",
        "age_45_64_pct": "Pre-senior age segment that drives mid-term service demand.",
        "birth_rate_per_1000": "Family and pediatric demand proxy.",
        "total_population": "Total market size for the ZIP.",
        "unemployment_rate": "Market stress proxy (lower is generally better).",
        "industry_public_administration": "Employment-mix proxy for payer and service context.",
        "bachelors_or_higher_pct": "Market receptivity and care engagement profile.",
        "industry_education_and_health": "Healthcare ecosystem and infrastructure fit signal.",
        "median_household_income": "Commercial payer capacity proxy.",
        "per_capita_income_growth_2yr": "Income momentum proxy for payer quality trend.",
        "county_level_gdp_growth_5yr": "Economic foundation trend across five years.",
        "hispanic_pct": "Equity and access profile for culturally aligned planning.",
        "black_pct": "Equity and access profile for inclusion-focused strategy.",
        "median_age": "Service-line fit proxy based on age profile.",
        "industry_agriculture": "Underserved/rural workforce mix proxy.",
        "industry_manufacturing": "Employer-base service-line utilization proxy.",
    }

    def _rows_for_dim(dim_key: str, dim_label: str) -> list[tuple[str, str]]:
        rows: list[tuple[str, str]] = []
        for col in DIMENSION_INDICATORS.get(dim_key, []):
            rows.append(
                (
                    _pretty_indicator_name(col),
                    indicator_defs.get(col, f"Definition for {dim_label} Tier 1 indicator."),
                )
            )
        return rows

    def _tier_defs_dropdown(title: str, rows: list[tuple[str, str]]) -> str:
        tier1_body = (
            '<ul style="margin:0;padding-left:18px;">'
            + "".join(
                f'<li class="def-tier-li" style="margin:12px 0;line-height:1.5;">'
                f"<span>{html.escape(f)}: {html.escape(d)}</span></li>"
                for f, d in rows
            )
            + "</ul>"
        )
        return (
            f'<details class="tier-dropdown" data-tier="defs_{title.lower().replace(" ", "_")}">'
            f'<summary class="tier-dropdown-summary">{title}</summary>'
            f'<div class="tier-dropdown-content">'
            '<details class="tier-dropdown" data-tier="tier1">'
            '<summary class="tier-dropdown-summary">Tier 1</summary>'
            f'<div class="tier-dropdown-content"><div class="def-body">{tier1_body}</div></div>'
            "</details>"
            '<details class="tier-dropdown" data-tier="tier2">'
            '<summary class="tier-dropdown-summary">Tier 2</summary>'
            '<div class="tier-dropdown-content"><div class="def-body"><i>No indicators configured for Tier 2 in this release.</i></div></div>'
            "</details>"
            '<details class="tier-dropdown" data-tier="tier3">'
            '<summary class="tier-dropdown-summary">Tier 3</summary>'
            '<div class="tier-dropdown-content"><div class="def-body"><i>No indicators configured for Tier 3 in this release.</i></div></div>'
            "</details>"
            f"</div></details>"
        )

    tier1_defs_attr = _rows_for_dim("attractiveness", "Market Attractiveness")
    tier1_defs_win = _rows_for_dim("ability_to_win", "Ability to Succeed")
    tier1_defs_ripe = _rows_for_dim("ripeness", "Ripeness")
    tier1_defs_econ = _rows_for_dim("economic_significance", "Economic Significance")

    zip_score_formula_html = (
        '<div class="def-formula-eq">Market Score = (&Sigma; C<sub>i</sub>) / C<sub>n</sub></div>'
        '<div class="def-formula-row"><span class="def-chip">C<sub>i</sub></span><span>= construct score i</span></div>'
        '<div class="def-formula-row"><span class="def-chip">C<sub>n</sub></span><span>= construct count</span></div>'
    )

    market_formula_html = (
        '<div class="def-formula-eq">Average Market Score = &Sigma; (Pop<sub>z</sub> &times; ZIP<sub>z</sub>) / &Sigma; Pop<sub>z</sub></div>'
        '<div class="def-formula-row"><span class="def-chip">ZIP<sub>z</sub></span><span>= ZIP score for ZIP z</span></div>'
        '<div class="def-formula-row"><span class="def-chip">Pop<sub>z</sub></span><span>= population of ZIP z</span></div>'
    )
    option_keys = ["attractiveness_score_opt1", "attractiveness_score_opt2", "attractiveness_score_opt4"]
    option_labels = {
        "attractiveness_score_opt1": "Option 1",
        "attractiveness_score_opt2": "Option 2",
        "attractiveness_score_opt4": "Option 4",
    }

    def _weights_for(option_key: str, dim_key: str) -> dict[str, float]:
        approved = approved_ccw.get(option_key, {}).get(dim_key, {}) if isinstance(approved_ccw, dict) else {}
        default = default_ccw.get(option_key, {}).get(dim_key, {})
        out = default.copy()
        out.update({k: float(v) for k, v in approved.items()})
        return out

    def _indicator_weight_list_html(option_key: str, dim_key: str) -> str:
        wmap = _weights_for(option_key, dim_key)
        if not wmap:
            return "<li>No indicators configured</li>"
        items = []
        for ind in DIMENSION_INDICATORS.get(dim_key, []):
            if ind not in wmap:
                continue
            items.append(f"<li>{html.escape(_pretty_indicator_name(ind))}: {float(wmap[ind]):.0f}%</li>")
        return "".join(items) if items else "<li>No indicators configured</li>"

    def _sub_construct_score_dropdown(title: str, symbol: str, dim_key: str) -> str:
        tier1_body = (
            '<div class="def-construct-tier-line" style="margin-bottom:8px;"><b>Tier 1 Formulas</b></div>'
            f'<div class="def-formula-row" style="margin:6px 0;"><span class="def-chip">Option 1</span><span>{symbol}<sub>i</sub>: ((z<sub>avg</sub> - min(z<sub>avg</sub>)) / (max(z<sub>avg</sub>) - min(z<sub>avg</sub>))) &times; 100</span></div>'
            f'<div class="def-formula-row" style="margin:6px 0;"><span class="def-chip">Option 2</span><span>{symbol}<sub>i</sub>: &Sigma; (w<sub>k</sub> &times; p<sub>k</sub>)</span></div>'
            f'<div class="def-formula-row" style="margin:6px 0 12px;"><span class="def-chip">Option 4</span><span>{symbol}<sub>i</sub>: &Sigma; (w<sub>k</sub> &times; p<sub>k</sub>) / &Sigma; w<sub>k</sub></span></div>'
            '<div style="height:30px;"></div>'
            '<div class="def-body" style="display:flex;gap:18px;flex-wrap:wrap;padding-bottom:16px;">'
            + "".join(
                f'<div style="flex:1 1 240px;min-width:240px;margin:4px 0;"><b>{option_labels[ok]} Weights</b><ul style="margin:8px 0 0 18px;">{_indicator_weight_list_html(ok, dim_key)}</ul></div>'
                for ok in option_keys
            )
            + "</div>"
        )
        return (
            f'<details class="tier-dropdown" data-tier="sc_{title.lower().replace(" ", "_")}">'
            f'<summary class="tier-dropdown-summary">{title}</summary>'
            '<div class="tier-dropdown-content">'
            '<details class="tier-dropdown" data-tier="tier1">'
            '<summary class="tier-dropdown-summary">Tier 1</summary>'
            f'<div class="tier-dropdown-content"><div class="def-body">{tier1_body}</div></div>'
            "</details>"
            '<details class="tier-dropdown" data-tier="tier2">'
            '<summary class="tier-dropdown-summary">Tier 2</summary>'
            '<div class="tier-dropdown-content"><div class="def-body"><b>Tier 2 Formulas</b>: Placeholder (no formula configured yet).</div></div>'
            "</details>"
            '<details class="tier-dropdown" data-tier="tier3">'
            '<summary class="tier-dropdown-summary">Tier 3</summary>'
            '<div class="tier-dropdown-content"><div class="def-body"><b>Tier 3 Formulas</b>: Placeholder (no formula configured yet).</div></div>'
            "</details>"
            "</div></details>"
        )

    sub_construct_score_html = (
        '<div class="def-body" style="margin-top:10px;">'
        + _sub_construct_score_dropdown("Market Attractiveness", "M", "attractiveness")
        + _sub_construct_score_dropdown("Ability to Succeed", "A", "ability_to_win")
        + _sub_construct_score_dropdown("Ripeness", "R", "ripeness")
        + _sub_construct_score_dropdown("Economic Significance", "E", "economic_significance")
        + "</div>"
    )

    construct_score_html = (
        '<div class="def-formula-eq">Construct Score = &Sigma; (t<sub>i</sub> &times; T<sub>i</sub>)</div>'
        '<div class="def-formula-row"><span class="def-chip">T1</span><span>= Tier 1 score for the construct</span></div>'
        '<div class="def-formula-row"><span class="def-chip">T2</span><span>= Tier 2 score for the construct</span></div>'
        '<div class="def-formula-row"><span class="def-chip">T3</span><span>= Tier 3 score for the construct</span></div>'
        '<div class="def-formula-row"><span class="def-chip">t<sub>i</sub></span><span>= tier weight for tier i</span></div>'
        '<div style="height:24px;"></div>'
        '<div class="def-score-title def-tier-weights-title">Tier Weights</div>'
        '<ul class="def-tier-weights-list">'
        "<li>Tier 1 = 0.33</li>"
        "<li>Tier 2 = 0.33</li>"
        "<li>Tier 3 = 0.33</li>"
        "</ul>"
    )

    return (
        '<div class="def-card">'
        '<div class="def-title">Framework</div>'
        '<div class="def-body" style="margin-top:0;">'
        f"{REFERENCE_FRAMEWORK_INTRO_BODY}"
        "</div>"
        f'<div class="def-framework-chart-wrap">{svg}</div>'
        "</div>"
        '<div class="def-card">'
        '<div class="def-title">Constructs</div>'
        '<div class="def-body def-constructs-body">'
        '<div class="def-dim"><b>Market Attractiveness</b>: '
        "How structurally favorable the market is to pursue growth (demand, growth, economics, access, competitive intensity). "
        "<br><i>Interpretation:</i> Is this market worth being in or expanding in?</div>"
        '<div class="def-dim"><b>Ability to Succeed</b>: '
        "Relative capability to win and sustain advantage in that market (brand/network, outcomes, referral ties, cost position, feasibility). "
        "<br><i>Interpretation:</i> Can we realistically win here versus competitors given our assets and constraints?</div>"
        '<div class="def-dim"><b>Ripeness</b>: '
        "How actionable the opportunity is now, based on stage-gate signals (timing, readiness, and execution conditions). "
        "<br><i>Interpretation:</i> Is this opportunity ready to move now? Ball color indicates ripeness level: red (low), yellow (medium), green (high).</div>"
        '<div class="def-construct-ui">'
        '<span class="def-ball def-ball-red def-ball-md"></span>'
        '<span class="def-ball def-ball-yellow def-ball-md"></span>'
        '<span class="def-ball def-ball-green def-ball-md"></span>'
        "</div>"
        '<div class="def-dim"><b>Economic Significance</b>: '
        "Magnitude of value at stake if pursued successfully, used to scale diligence intensity and governance attention "
        "(revenue potential, cost/capital exposure, margin quality, portfolio impact). "
        "<br><i>Interpretation:</i> How important of a decision is this, and what analysis depth is warranted? Ball size indicates significance (small to large impact).</div>"
        '<div class="def-construct-ui">'
        '<span class="def-ball def-ball-green def-ball-sm"></span>'
        '<span class="def-ball def-ball-green def-ball-md"></span>'
        '<span class="def-ball def-ball-green def-ball-lg"></span>'
        "</div>"
        "</div>"
        "</div>"
        '<div class="def-card def-card-formula">'
        '<div class="def-title">Construct Score</div>'
        '<div class="def-formula">'
        f"{construct_score_html}"
        "</div>"
        "</div>"
        '<div class="def-card">'
        '<div class="def-title">Sub-constructs</div>'
        + _tier_defs_dropdown("Market Attractiveness", tier1_defs_attr)
        + _tier_defs_dropdown("Ability to Succeed", tier1_defs_win)
        + _tier_defs_dropdown("Ripeness", tier1_defs_ripe)
        + _tier_defs_dropdown("Economic Significance", tier1_defs_econ)
        + "</div>"
        '<div class="def-card">'
        '<div class="def-title">Sub-construct Score</div>'
        f"{sub_construct_score_html}"
        "</div>"
        '<div class="def-card def-card-formula">'
        '<div class="def-title">Market Score</div>'
        '<div class="def-formula">'
        f"{zip_score_formula_html}"
        '<div class="def-ms-legend-title">Market Score Legend</div>'
        '<div class="def-ms-legend-stack">'
        f'<div class="def-ms-legend-strip" style="background:{score_legend_gradient_css()};"></div>'
        '<div class="def-ms-legend-labels">'
        '<span class="def-ms-legend-edge">LOW</span>'
        '<span class="def-ms-legend-edge">HIGH</span>'
        "</div>"
        "</div>"
        "</div>"
        "</div>"
        '<div class="def-card def-card-formula">'
        '<div class="def-title">Average Market Score</div>'
        '<div class="def-formula">'
        f"{market_formula_html}"
        "</div>"
        "</div>"
    )
