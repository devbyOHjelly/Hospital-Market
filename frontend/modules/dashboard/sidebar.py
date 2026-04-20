import html
import pandas as pd
from frontend.config import score_fill_color
from frontend.modules.definitions_html import render_reference_framework_chart_svg

MAX_SELECTED = 10


def _score_bucket_index(score: float | None) -> int:
    """0–19 bucket for market score legend (5-point bands on 0–100)."""
    try:
        x = float(score if score is not None else 0)
    except (TypeError, ValueError):
        x = 0.0
    x = max(0.0, min(100.0, x))
    return min(19, max(0, int(x // 5)))


def _score_span_html(score: float | None, display: str, extra_classes: str = "") -> str:
    """Bucket class + CSS var so colors survive dcc.Markdown; matches map legend ramp."""
    bi = _score_bucket_index(score)
    hc = score_fill_color(score)
    extra = f" {extra_classes.strip()}" if extra_classes.strip() else ""
    return (
        f'<span class="market-score-value market-ms-bkt-{bi}{extra}" '
        f'style="--ms-color:{hc};">{display}</span>'
    )


def entity_count_html(count: int | None) -> str:
    if count is None or count == 0:
        return ""
    return (
        f'<div style="font-size:0.65rem;color:#1a1a1a;letter-spacing:0.03em;'
        f'text-transform:uppercase;margin-top:8px;margin-bottom:2px;">'
        f'Entities on Map: <b style="color:#22c55e;">{count:,}</b></div>'
    )

def map_chips_html(selected: list[dict], limit_msg: str = "") -> str:
    if not selected:
        return ""

    count = len(selected)
    counter_color = "#F37021" if count >= MAX_SELECTED else "#ffffff"

    chips = ""
    for zd in selected:
        zc = zd.get("zipcode", "")
        chips += f'<span class="map-chip">{zc}</span>'

    return (
        f'<div class="map-chips-bar">'
        f'<div class="map-chips-row">'
        f'<span class="map-chips-count" style="color:{counter_color};">'
        f"{count} / {MAX_SELECTED}</span>"
        f'<div class="map-chips-items">{chips}</div>'
        f"</div></div>"
    )


def _weighted_avg_from_selected(
    selected: list[dict],
    key: str,
    weight_key: str = "total_population",
) -> float | None:
    vals = []
    for z in selected:
        v = pd.to_numeric(pd.Series([z.get(key)]), errors="coerce").iloc[0]
        if pd.notna(v):
            vals.append(float(v))
        else:
            vals.append(None)
    if not vals:
        return None

    weights = []
    for z in selected:
        w = pd.to_numeric(pd.Series([z.get(weight_key)]), errors="coerce").iloc[0]
        if pd.notna(w) and float(w) > 0:
            weights.append(float(w))
        else:
            weights.append(0.0)

    weighted_num = 0.0
    weighted_den = 0.0
    for v, w in zip(vals, weights):
        if v is None:
            continue
        if w > 0:
            weighted_num += v * w
            weighted_den += w
    if weighted_den > 0:
        return weighted_num / weighted_den

    plain = [v for v in vals if v is not None]
    if not plain:
        return None
    return sum(plain) / len(plain)


def _market_framework_html(
    selected: list[dict],
    selected_option: str = "attractiveness_score_opt2",
) -> str:
    """Reference-style framework chart only (selection-weighted bubble); no Framework title/copy."""
    if not selected:
        return ""
    option_col = str(selected_option or "").strip() or "attractiveness_score_opt2"
    opt_suffix = option_col.split("_")[-1] if "_" in option_col else "opt2"
    if opt_suffix not in {"opt1", "opt2", "opt4"}:
        opt_suffix = "opt2"

    attr = _weighted_avg_from_selected(selected, "attractiveness")
    ability = _weighted_avg_from_selected(selected, "ability_to_win")
    ripe = _weighted_avg_from_selected(selected, "ripeness")
    econ = _weighted_avg_from_selected(selected, "economic_significance")

    # Fallback to option-specific columns if normalized construct aliases are absent.
    if attr is None:
        attr = _weighted_avg_from_selected(selected, f"attractiveness_score_{opt_suffix}")
    if ability is None:
        ability = _weighted_avg_from_selected(selected, f"win_score_{opt_suffix}")
    if ripe is None:
        ripe = _weighted_avg_from_selected(selected, f"strength_score_{opt_suffix}")
    if econ is None:
        econ = _weighted_avg_from_selected(selected, f"rightness_score_{opt_suffix}")

    # Population-weighted ripeness only (no hospital_potential) for bubble RYG: 0–33 red, 34–66 yellow, 67–100 green.
    ripe_pop = _weighted_avg_from_selected(selected, "ripeness")
    if ripe_pop is None:
        ripe_pop = _weighted_avg_from_selected(selected, f"strength_score_{opt_suffix}")
    ripe_bubble = float(ripe_pop if ripe_pop is not None else 0.0)

    # Final fallback to market score for axis positioning / display (not for bubble color).
    market_fallback = _weighted_avg_from_selected(selected, "hospital_potential")
    attr = float(attr if attr is not None else (market_fallback or 0.0))
    ability = float(ability if ability is not None else (market_fallback or 0.0))
    econ = float(econ if econ is not None else (market_fallback or 0.0))

    n = len(selected)
    tip = (
        f"Selection ({n} ZIP{'s' if n != 1 else ''}) | Attractiveness {attr:.1f} | Ability to Win {ability:.1f} | "
        f"Ripeness (pop.-wt. avg) {ripe_bubble:.1f} | Economic Significance {econ:.1f}"
    )
    svg = render_reference_framework_chart_svg(
        attr, ability, ripe_bubble, econ, tooltip=tip
    )
    return f'<div class="def-framework-chart-wrap market-framework-selection-wrap">{svg}</div>'


# Column order for ZIP factor rows (merged from parquet + gpkg); extras append sorted.
_ZIP_FACTOR_PREFERRED_KEYS = [
    "zip_code",
    "data_year",
    "total_population",
    "population_growth_rate_2yr",
    "net_population_change_2yr",
    "historical_year",
    "age_0_17",
    "age_18_44",
    "age_45_64",
    "age_65_plus",
    "age_0_17_pct",
    "age_18_44_pct",
    "age_45_64_pct",
    "age_65_plus_pct",
    "median_age",
    "white_alone",
    "black_alone",
    "asian_alone",
    "hispanic_latino",
    "white_pct",
    "black_pct",
    "asian_pct",
    "hispanic_pct",
    "median_household_income",
    "bachelors_or_higher",
    "bachelors_or_higher_pct",
    "birth_rate_per_1000",
    "in_migration_from_other_state",
    "in_migration_rate",
    "unemployed",
    "unemployment_rate",
    "per_capita_income",
    "per_capita_income_growth_2yr",
    "top_industry",
    "top_industry_employment",
    "industry_agriculture",
    "industry_construction",
    "industry_manufacturing",
    "industry_retail",
    "industry_finance",
    "industry_professional_tech",
    "industry_education_and_health",
    "industry_arts_entertainment",
    "industry_other_services",
    "industry_public_administration",
    "county_name",
    "county_flips",
    "state_fips",
    "state_name",
    "msa",
    "msa_name",
    "county_level_gdp_thousands",
    "county_level_gdp_growth_5yr",
    "gdp_year",
    "msa_level_gdp_millions",
    "msa_gdp_growth_5yr",
    "msa_gdp_year",
]


def market_tab_html(
    selected: list[dict],
    entities_df=None,
    selected_option: str = "attractiveness_score_opt2",
) -> str:
    """Render the Selection tab with framework chart, scores, and tier indicators per ZIP."""
    _ = entities_df  # API compatibility with dash_app; entities list not shown in Selection tab.
    count = len(selected)

    if count == 0:
        return (
            '<p class="market-empty-msg" style="color:#ffffff;font-size:0.82rem;padding:10px 0;text-align:center;">'
            "Click a ZIP CODE on the map to add it here</p>"
        )

    avg_score = _weighted_avg_from_selected(selected, "hospital_potential")
    if avg_score is None:
        avg_score = 0.0
    avg_score_span = _score_span_html(
        avg_score, f"{avg_score:.1f}", "market-selection-avg-value"
    )

    score_box = (
        '<div class="market-detail-block">'
        '<div class="market-selection-chart-column">'
        '<div class="market-framework-chart-holder">'
        f"{_market_framework_html(selected, selected_option=selected_option)}"
        "</div>"
        '<div class="market-selection-avg-score">'
        '<div class="market-selection-avg-label">Average Market Score</div>'
        f'<div class="market-selection-avg-value-wrap">{avg_score_span}</div>'
        '<div class="market-selection-avg-sublabel">out of 100</div>'
        "</div>"
        "</div>"
        "</div>"
    )

    na = '<span style="color:#c8c8c8;">N/A</span>'

    def _is_missing(v):
        if v is None:
            return True
        s = str(v).strip()
        return s == "" or s.lower() in {"nan", "none", "null", "na", "n/a"}

    def _is_factor_key(k):
        k = str(k)
        excluded = {
            "type",
            "action",
            "geometry",
            "zipcode",
            "zip_code",
            "zip",
            "state",
            "state_abbr",
            "state_key",
            "place_name",
            "entity_count",
            "hospital_count",
            "avg_entity_score",
            "avg_confidence",
            "hospital_potential",
            "tier1",
        }
        if k in excluded:
            return False
        if k.startswith("_"):
            return False
        return True

    def _pretty_col(k):
        return str(k).replace("_", " ").strip().title()

    def _to_num(v):
        if v is None:
            return None
        if isinstance(v, (int, float)):
            return float(v) if v == v else None
        s = str(v).strip()
        if not s or s.lower() in {"nan", "none", "null", "na", "n/a"}:
            return None
        s = s.replace("$", "").replace(",", "").replace("%", "")
        s = s.replace("/1000", "").replace("/1,000", "")
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    def _fmt_dynamic(key, raw):
        if raw is None:
            return na
        num = _to_num(raw)
        if num is None:
            return html.escape(str(raw))
        key_l = str(key).lower()
        if "pct" in key_l or "percent" in key_l or "penetration" in key_l or "rate" in key_l:
            return f"{num:.1f}%"
        if "income" in key_l or "revenue" in key_l or "gdp" in key_l:
            return f"${int(round(num)):,}"
        if "year" in key_l:
            return f"{int(round(num))}"
        if abs(num) >= 1000:
            return f"{int(round(num)):,}"
        return f"{num:.1f}"

    preferred = _ZIP_FACTOR_PREFERRED_KEYS
    key_union = []
    seen = set()
    for row in selected:
        for k, v in row.items():
            if not _is_factor_key(k):
                continue
            if _is_missing(v):
                continue
            if k not in seen:
                seen.add(k)
                key_union.append(k)

    ordered_keys = [k for k in preferred if k in seen] + sorted(
        [k for k in key_union if k not in set(preferred)]
    )

    def _factor_dropdown(title, rows, open_default=False):
        tid = title.lower().replace(" ", "_")
        open_attr = " open" if open_default else ""
        frag = (
            f'<details class="tier-dropdown" data-tier="{tid}"{open_attr}>'
            f'<summary class="tier-dropdown-summary">{title}</summary>'
            f'<div class="tier-dropdown-content">'
            f'<table style="width:100%;font-size:0.7rem;border-collapse:collapse;table-layout:fixed;">'
        )
        for label, val in rows:
            frag += _row(label, val)
        frag += "</table></div></details>"
        return frag

    def _tier_score_cell(val: float | None) -> str:
        if val is None:
            return na
        return _score_span_html(val, f"{val:.1f}")

    items = ""
    for zd in selected:
        zc = zd.get("zipcode", "")
        st = zd.get("state", "")
        sc = float(zd.get("hospital_potential", 0) or 0)
        row_pairs = [(_pretty_col(k), _fmt_dynamic(k, zd.get(k))) for k in ordered_keys]
        factors_dd = _factor_dropdown(
            "Tier Information",
            row_pairs if row_pairs else [("No parquet factors found", na)],
        )

        opt_suffix = str(selected_option or "").strip().split("_")[-1] if selected_option else "opt2"
        if opt_suffix not in {"opt1", "opt2", "opt4"}:
            opt_suffix = "opt2"

        def _score_for(row: dict, base: str, fallback: str | None = None):
            v = pd.to_numeric(pd.Series([row.get(base)]), errors="coerce").iloc[0]
            if pd.notna(v):
                return float(v)
            if fallback:
                vf = pd.to_numeric(pd.Series([row.get(fallback)]), errors="coerce").iloc[0]
                if pd.notna(vf):
                    return float(vf)
            return None

        z_attr = _score_for(zd, "attractiveness", f"attractiveness_score_{opt_suffix}")
        z_ability = _score_for(zd, "ability_to_win", f"win_score_{opt_suffix}")
        z_ripe = _score_for(zd, "ripeness", f"strength_score_{opt_suffix}")
        z_econ = _score_for(zd, "economic_significance", f"rightness_score_{opt_suffix}")

        score_html = _score_span_html(sc, f"{sc:.1f}")
        zip_score_span = _score_span_html(sc, f"{sc:.1f}", "market-zip-score-value")

        items += (
            f'<li class="market-zip-item">'
            f'<details class="zip-detail-toggle" data-zip="{zc}">'
            f'<summary class="zip-detail-summary">'
            f'<span style="font-size:0.8rem;color:#ff7f00;">{zc}</span>'
            f'<span style="font-size:0.72rem;color:#e8e8e8;margin-left:6px;">{st}</span>'
            f'{zip_score_span}'
            f'<span class="market-zip-remove chip-remove" data-zip="{zc}" title="Remove ZIP">&times;</span>'
            f"</summary>"
            f'<div class="zip-detail-content">'
            f'<table style="width:100%;font-size:0.7rem;border-collapse:collapse;table-layout:fixed;">'
            f'{_row("Score", score_html, value_color=None)}'
            f'{_row("Attractiveness", _tier_score_cell(z_attr), value_color=None)}'
            f'{_row("Ability to Succeed", _tier_score_cell(z_ability), value_color=None)}'
            f'{_row("Ripeness", _tier_score_cell(z_ripe), value_color=None)}'
            f'{_row("Economic Significance", _tier_score_cell(z_econ), value_color=None)}'
            f"</table>"
            f'<div style="margin-top:6px;"></div>'
            f"{factors_dd}"
            f"</div></details></li>"
        )

    # Inline <script> was removed: dcc.Markdown often strips or breaks on script tags,
    # which left the Market tab blank after ZIP selection.
    n_sel = len(selected) if selected else 0
    max_note = (
        f'<div class="market-selection-max-zips-note">'
        f"The maximum selection is {MAX_SELECTED} ZIP codes. "
        f'<span class="market-selection-zip-count">({n_sel}/{MAX_SELECTED})</span>'
        f"</div>"
    )
    return (
        f"{score_box}"
        f'<div class="market-zip-list-section">{max_note}<ul class="market-zip-list">{items}</ul></div>'
    )


def _row(label: str, value: str, *, value_color: str | None = "#ffffff") -> str:
    vc = f"color:{value_color};" if value_color else ""
    return (
        f'<tr><td style="color:#e8e8e8;padding:3px 8px 3px 0;font-size:0.7rem;'
        f'width:66%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{label}</td>'
        f'<td style="text-align:right;font-weight:600;{vc}padding:3px 0;'
        f'font-size:0.7rem;width:34%;white-space:nowrap;">{value}</td></tr>'
    )
