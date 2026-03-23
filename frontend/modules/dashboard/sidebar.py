import html
import pandas as pd
from frontend.config import COLORMAP

MAX_SELECTED = 10

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
    counter_color = "#ff7f00" if count >= MAX_SELECTED else "#ffffff"

    chips = ""
    for zd in selected:
        zc = zd.get("zipcode", "")
        chips += f'<span class="map-chip">{zc}</span>'

    return (
        f'<div class="map-chips-bar">'
        f'<span class="map-chips-count" style="color:{counter_color};">'
        f"{count}/{MAX_SELECTED}</span>"
        f'<div class="map-chips-items">{chips}</div>'
        f"</div>"
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
    """Framework chart for market-average view (single dynamic bubble)."""
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

    # Final fallback to market score if any construct is missing.
    market_fallback = _weighted_avg_from_selected(selected, "hospital_potential")
    attr = float(attr if attr is not None else (market_fallback or 0.0))
    ability = float(ability if ability is not None else (market_fallback or 0.0))
    ripe = float(ripe if ripe is not None else (market_fallback or 0.0))
    econ = float(econ if econ is not None else (market_fallback or 0.0))

    w, h = 360, 268
    ml, mr, mt, mb = 44, 14, 16, 54
    pw, ph = w - ml - mr, h - mt - mb
    cell_w, cell_h = pw / 3.0, ph / 3.0

    bg_rects = (
        f'<rect x="{ml:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd699"/>'
        f'<rect x="{ml+cell_w:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffb84d"/>'
        f'<rect x="{ml+2*cell_w:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ff7f00"/>'
        f'<rect x="{ml:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#fff0d4"/>'
        f'<rect x="{ml+cell_w:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd699"/>'
        f'<rect x="{ml+2*cell_w:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffb84d"/>'
        f'<rect x="{ml:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffffff"/>'
        f'<rect x="{ml+cell_w:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#fff0d4"/>'
        f'<rect x="{ml+2*cell_w:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd699"/>'
    )

    def _x(v):
        return ml + (max(0.0, min(100.0, float(v))) / 100.0) * pw

    def _y(v):
        return mt + (1.0 - (max(0.0, min(100.0, float(v))) / 100.0)) * ph

    r = 5.5 + (max(0.0, min(100.0, econ)) / 100.0) * 12.5
    cx, cy = _x(ability), _y(attr)

    # Bubble color from ripeness construct.
    if ripe >= 67:
        bubble_fill = "#22c55e"
    elif ripe >= 34:
        bubble_fill = "#f59e0b"
    else:
        bubble_fill = "#ef4444"
    bubble_stroke = "#000000"

    svg = (
        f'<svg viewBox="0 0 {w} {h}" width="100%" height="250" role="img" '
        f'aria-label="Framework chart">'
        f'<rect x="0" y="0" width="{w}" height="{h}" fill="#000000"/>'
        + bg_rects
        + f'<rect x="{ml}" y="{mt}" width="{pw:.1f}" height="{ph:.1f}" fill="none" stroke="#9ca3af" stroke-width="1"/>'
        f'<line x1="{ml+pw/3:.1f}" y1="{mt}" x2="{ml+pw/3:.1f}" y2="{mt+ph}" stroke="#6b7280" stroke-width="1"/>'
        f'<line x1="{ml+2*pw/3:.1f}" y1="{mt}" x2="{ml+2*pw/3:.1f}" y2="{mt+ph}" stroke="#6b7280" stroke-width="1"/>'
        f'<line x1="{ml}" y1="{mt+ph/3:.1f}" x2="{ml+pw}" y2="{mt+ph/3:.1f}" stroke="#6b7280" stroke-width="1"/>'
        f'<line x1="{ml}" y1="{mt+2*ph/3:.1f}" x2="{ml+pw}" y2="{mt+2*ph/3:.1f}" stroke="#6b7280" stroke-width="1"/>'
        f'<circle cx="{cx:.1f}" cy="{cy:.1f}" r="{r:.1f}" fill="{bubble_fill}" stroke="{bubble_stroke}" stroke-width="1.2"></circle>'
        f'<text x="{ml+pw/2:.1f}" y="{h-8}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle">ABILITY TO SUCCEED</text>'
        f'<text x="0" y="{mt+ph/2:.1f}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle" transform="rotate(-90 0 {mt+ph/2:.1f})">MARKET ATTRACTIVENESS</text>'
        f'<text x="{ml}" y="{mt+ph+16}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em">LOW</text>'
        f'<text x="{ml+pw/2:.1f}" y="{mt+ph+16}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle">MED</text>'
        f'<text x="{ml+pw}" y="{mt+ph+16}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">HIGH</text>'
        f'<text x="{ml-8}" y="{mt+ph}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">LOW</text>'
        f'<text x="{ml-8}" y="{mt+ph/2:.1f}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">MED</text>'
        f'<text x="{ml-8}" y="{mt+8}" fill="#ffffff" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">HIGH</text>'
        "</svg>"
    )

    return (
        '<div style="border:none;border-radius:6px;background:#000;margin-bottom:10px;padding:8px 8px 6px;">'
        '<div class="def-title market-projection-title" style="margin:-2px 0 8px -4px;text-align:left;">Market Projection</div>'
        f'<div style="margin-top:40px;">{svg}</div>'
        "</div>"
    )


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
    """Render the Market tab with aggregate metrics + per-ZIP entity detail."""
    count = len(selected)

    if count == 0:
        return (
            '<p class="market-empty-msg" style="color:#1a1a1a;font-size:0.82rem;padding:10px 0;text-align:center;">'
            "Click a ZIP CODE on the map to add it here</p>"
        )

    avg_score = _weighted_avg_from_selected(selected, "hospital_potential")
    if avg_score is None:
        avg_score = 0.0
    avg_color = COLORMAP(avg_score)

    total_ent = sum(int(z.get("entity_count", 0)) for z in selected)
    avg_ent = total_ent / count

    score_box = (
        f'<div class="market-detail-block">'
        f"{_market_framework_html(selected, selected_option=selected_option)}"
        f'<div style="text-align:center;padding:6px 10px;">'
        f'<div style="font-size:0.6rem;color:#1a1a1a;">Average Market Score</div>'
        f'<div class="market-score-value" style="--ms-color:{avg_color};font-size:1.4rem;font-weight:800;line-height:1.2;">'
        f"{avg_score:.1f}</div>"
        f'<div style="font-size:0.6rem;color:#1a1a1a;">out of 100</div></div>'
        f'<div class="market-detail-content" style="border-top:none;">'
        f'<table style="width:100%;font-size:0.7rem;border-collapse:collapse;table-layout:fixed;">'
    )

    score_box += _row("Total Entities", f"{total_ent:,}")
    score_box += _row("Average Entities/ZIP", f"{avg_ent:.1f}")

    score_box += "</table>"
    score_box += '<div style="margin-top:8px;"></div>'

    from collections import Counter

    na = '<span style="color:#1a1a1a;">N/A</span>'

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

    def _agg_for_key(k):
        vals = [row.get(k) for row in selected if not _is_missing(row.get(k))]
        if not vals:
            return None
        nums = [_to_num(v) for v in vals]
        num_vals = [v for v in nums if v is not None]
        if num_vals and (len(num_vals) / len(vals)) >= 0.6:
            return sum(num_vals) / len(num_vals)
        return Counter(str(v).strip() for v in vals).most_common(1)[0][0]

    all_rows_agg = [(_pretty_col(k), _fmt_dynamic(k, _agg_for_key(k))) for k in ordered_keys]
    if not all_rows_agg:
        all_rows_agg = [("No parquet factors found", na)]

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

    score_box += "</div></div>"

    items = ""
    for zd in selected:
        zc = zd.get("zipcode", "")
        st = zd.get("state", "")
        sc = float(zd.get("hospital_potential", 0) or 0)
        sc_color = COLORMAP(sc)
        ent_count = int(zd.get("entity_count", 0) or 0)
        hosp_count = int(zd.get("hospital_count", 0) or 0)
        row_pairs = [(_pretty_col(k), _fmt_dynamic(k, zd.get(k))) for k in ordered_keys]
        factors_dd = _factor_dropdown(
            "ZIP-level factors",
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

        hosp_content = ""
        if entities_df is not None and len(entities_df) > 0:
            zip_ents = entities_df[
                (entities_df["zip"].astype(str).str.zfill(5) == zc)
                & (entities_df.get("entity_type", pd.Series()) == "hospital")
            ]
            if len(zip_ents) > 0:
                for _, h in zip_ents.head(10).iterrows():
                    name = (
                        str(h.get("display_name", ""))
                        if pd.notna(h.get("display_name"))
                        else ""
                    )
                    htype = (
                        str(h.get("hospital_type", ""))
                        if pd.notna(h.get("hospital_type"))
                        else ""
                    )
                    own = str(h.get("ownership", "")) if pd.notna(h.get("ownership")) else ""
                    rating = h.get("hospital_rating")
                    emerg = (
                        str(h.get("emergency_services", ""))
                        if pd.notna(h.get("emergency_services"))
                        else ""
                    )

                    hosp_content += (
                        f'<div style="padding:4px 0;border-top:1px solid #f0ebe4;">'
                        f'<div style="font-size:0.7rem;font-weight:600;color:#1a1a1a;">{name}</div>'
                    )
                    details = []
                    if htype:
                        details.append(htype)
                    if own:
                        short_own = own if len(own) < 30 else own[:27] + "..."
                        details.append(short_own)
                    if details:
                        hosp_content += (
                            f'<div style="font-size:0.62rem;color:#1a1a1a;">{" · ".join(details)}</div>'
                        )

                    badges = []
                    if pd.notna(rating) and str(rating).strip():
                        try:
                            rv = float(rating)
                            badges.append(
                                f'<span style="font-size:0.6rem;color:#f59e0b;">{"&#9733;" * round(rv)} {rv:.0f}/5</span>'
                            )
                        except ValueError:
                            badges.append(
                                '<span style="font-size:0.6rem;color:#1a1a1a;">Rating: N/A</span>'
                            )
                    else:
                        badges.append(
                            '<span style="font-size:0.6rem;color:#1a1a1a;">Rating: N/A</span>'
                        )
                    if emerg.lower() == "yes":
                        badges.append(
                            '<span style="font-size:0.6rem;color:#22c55e;">&#9679; ER</span>'
                        )
                    else:
                        badges.append(
                            '<span style="font-size:0.6rem;color:#1a1a1a;">ER: N/A</span>'
                        )
                    hosp_content += (
                        f'<div style="display:flex;gap:8px;margin-top:1px;">{"".join(badges)}</div>'
                    )
                    hosp_content += "</div>"

                if len(zip_ents) > 10:
                    hosp_content += (
                        f'<div style="font-size:0.6rem;color:#1a1a1a;padding:2px 0;">+{len(zip_ents) - 10} more</div>'
                    )
            else:
                hosp_content = (
                    '<div style="font-size:0.7rem;color:#1a1a1a;padding:4px 0;">No hospitals in this ZIP</div>'
                )
        else:
            hosp_content = (
                '<div style="font-size:0.7rem;color:#1a1a1a;padding:4px 0;">No hospital data available</div>'
            )

        hosp_dropdown = (
            f'<details class="tier-dropdown" data-tier="hospitals_{zc}">'
            f'<summary class="tier-dropdown-summary">Hospitals</summary>'
            f'<div class="tier-dropdown-content">{hosp_content}</div></details>'
        )
        score_html = (
            f'<span class="market-score-value" style="--ms-color:{sc_color};">{sc:.1f}</span>'
        )

        items += (
            f'<li class="market-zip-item">'
            f'<details class="zip-detail-toggle" data-zip="{zc}">'
            f'<summary class="zip-detail-summary">'
            f'<span style="font-size:0.8rem;color:#ff7f00;">{zc}</span>'
            f'<span style="font-size:0.72rem;color:#1a1a1a;margin-left:6px;">{st}</span>'
            f'<span class="market-score-value market-zip-score-value" style="--ms-color:{sc_color};margin-left:auto;font-size:0.78rem;font-weight:800;">{sc:.1f}</span>'
            f'<span class="market-zip-remove chip-remove" data-zip="{zc}" title="Remove ZIP">&times;</span>'
            f"</summary>"
            f'<div class="zip-detail-content">'
            f'<table style="width:100%;font-size:0.7rem;border-collapse:collapse;table-layout:fixed;">'
            f'{_row("Score", score_html, "#ffffff")}'
            f'{_row("Attractiveness", (f"{z_attr:.1f}" if z_attr is not None else na))}'
            f'{_row("Ability to Succeed", (f"{z_ability:.1f}" if z_ability is not None else na))}'
            f'{_row("Ripeness", (f"{z_ripe:.1f}" if z_ripe is not None else na))}'
            f'{_row("Economic Significance", (f"{z_econ:.1f}" if z_econ is not None else na))}'
            f'{_row("Entities", f"{ent_count:,}")}'
            f'{_row("Hospitals", f"{hosp_count:,}", "#22c55e")}'
            f"</table>"
            f'<div style="margin-top:6px;"></div>'
            f"{hosp_dropdown}{factors_dd}"
            f"</div></details></li>"
        )

    persist_js = """
<script>
(function() {
    if (!window._marketOpenState) window._marketOpenState = {};
    var state = window._marketOpenState;
    document.querySelectorAll('.tier-dropdown[data-tier]').forEach(function(d) {
        var parent = d.closest('.zip-detail-content');
        var prefix = parent ? 'zip_tier_' + d.closest('.zip-detail-toggle').dataset.zip + '_' : 'tier_';
        var k = prefix + d.dataset.tier;
        if (state[k]) d.setAttribute('open', '');
        d.addEventListener('toggle', function() { state[k] = d.open; });
    });
    document.querySelectorAll('.zip-detail-toggle[data-zip]').forEach(function(d) {
        var k = 'zip_' + d.dataset.zip;
        if (state[k]) d.setAttribute('open', '');
        d.addEventListener('toggle', function() { state[k] = d.open; });
    });
})();
</script>"""

    return f"{score_box}<ul class=\"market-zip-list\">{items}</ul>{persist_js}"


def _row(label: str, value: str, color: str = "#1a1a1a") -> str:
    return (
        f'<tr><td style="color:#1a1a1a;padding:3px 8px 3px 0;font-size:0.7rem;'
        f'width:66%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{label}</td>'
        f'<td style="text-align:right;font-weight:600;color:{color};padding:3px 0;'
        f'font-size:0.7rem;width:34%;white-space:nowrap;">{value}</td></tr>'
    )
