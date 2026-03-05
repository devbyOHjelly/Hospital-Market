from shiny import App, ui, render, reactive
import html
import pandas as pd
from config import WWW_DIR
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

_STATE_TO_ABBR = {
    "Alabama": "AL", "Florida": "FL", "Georgia": "GA",
}

# UI
app_ui = ui.page_sidebar(
    ui.sidebar(
        ui.navset_underline(
            # Definitions tab
            ui.nav_panel(
                "Definitions",
                ui.div(
                    ui.output_ui("definitions_panel"),
                    class_="definitions-section",
                ),
            ),
            # Ranks tab
            ui.nav_panel(
                "Ranks",
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
            ),
            # myMarket tab
            ui.nav_panel(
                "myMarket",
                ui.div(
                    ui.output_ui("market_panel"),
                    class_="market-section",
                ),
            ),
            # Settings tab
            ui.nav_panel(
                "Settings",
                ui.div(class_="settings-section"),
            ),
            id="sidebar_tabs",
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

    @reactive.calc
    def r_gdf():
        data = r_raw_gdf().copy()
        if "hospital_potential" not in data.columns:
            data["hospital_potential"] = 0.0
        return data

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

        # Use all Tier 1 numeric fields and map each into one of 4 framework dimensions.
        tier1_numeric_fields = [
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
        available_tier1 = [c for c in tier1_numeric_fields if c in data.columns]

        dim_rules = {
            "attractiveness": {
                "keywords": (
                    "growth", "income", "migration", "bachelors", "gdp", "birth", "unemploy"
                ),
                "invert_keywords": ("unemploy",),
            },
            "ability_to_win": {
                "keywords": (
                    "industry", "employment", "18_44", "45_64", "18_64", "bachelors", "working"
                ),
                "invert_keywords": (),
            },
            "ripeness": {
                "keywords": (
                    "65_plus", "median_age", "hispanic", "black", "asian", "white", "pct_"
                ),
                "invert_keywords": (),
            },
            "economic_significance": {
                "keywords": (
                    "total_population", "gdp", "employment", "count", "income", "age_"
                ),
                "invert_keywords": (),
            },
        }

        dim_cols = {k: [] for k in dim_rules}
        leftovers = []
        for col in available_tier1:
            col_l = col.lower()
            best_dim = None
            best_score = 0
            for dim, cfg in dim_rules.items():
                score = sum(1 for kw in cfg["keywords"] if kw in col_l)
                if score > best_score:
                    best_score = score
                    best_dim = dim
            if best_dim and best_score > 0:
                invert = any(kw in col_l for kw in dim_rules[best_dim]["invert_keywords"])
                dim_cols[best_dim].append((col, invert))
            else:
                leftovers.append(col)

        # Ensure every Tier 1 numeric field contributes to some dimension.
        dim_cycle = list(dim_cols.keys())
        for idx, col in enumerate(leftovers):
            dim_cols[dim_cycle[idx % len(dim_cycle)]].append((col, False))

        def _compose(cols):
            parts = []
            for col, invert in cols:
                v = _norm(col, invert=invert)
                if v is not None:
                    parts.append(v)
            return (sum(parts) / len(parts)) if parts else None

        attr = _compose(dim_cols["attractiveness"])
        win = _compose(dim_cols["ability_to_win"])
        ripe = _compose(dim_cols["ripeness"])
        econ = _compose(dim_cols["economic_significance"])

        fallback = pd.to_numeric(data["hospital_potential"], errors="coerce").fillna(0)
        data["attractiveness"] = attr if attr is not None else fallback
        data["ability_to_win"] = win if win is not None else fallback
        data["ripeness"] = ripe if ripe is not None else fallback
        data["economic_significance"] = econ if econ is not None else fallback

        w, h = 360, 268
        ml, mr, mt, mb = 44, 14, 16, 54
        pw, ph = w - ml - mr, h - mt - mb
        cell_w, cell_h = pw / 3.0, ph / 3.0

        bg_rects = (
            # High attractiveness row
            f'<rect x="{ml:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd699"/>'
            f'<rect x="{ml+cell_w:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffb84d"/>'
            f'<rect x="{ml+2*cell_w:.1f}" y="{mt:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ff9b1a"/>'
            # Medium attractiveness row
            f'<rect x="{ml:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#fff0d4"/>'
            f'<rect x="{ml+cell_w:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd699"/>'
            f'<rect x="{ml+2*cell_w:.1f}" y="{mt+cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffb84d"/>'
            # Low attractiveness row
            f'<rect x="{ml:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffffff"/>'
            f'<rect x="{ml+cell_w:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#fff0d4"/>'
            f'<rect x="{ml+2*cell_w:.1f}" y="{mt+2*cell_h:.1f}" width="{cell_w:.1f}" height="{cell_h:.1f}" fill="#ffd699"/>'
        )

        def _x(v):
            return ml + (max(0.0, min(100.0, float(v))) / 100.0) * pw

        def _y(v):
            return mt + (1.0 - (max(0.0, min(100.0, float(v))) / 100.0)) * ph

        def _r(v):
            return 5.5 + (max(0.0, min(100.0, float(v))) / 100.0) * 12.5

        # Single framework point for the selected state (aggregate position).
        agg_attr = float(data["attractiveness"].fillna(0).mean())
        agg_win = float(data["ability_to_win"].fillna(0).mean())
        agg_ripe = float(data["ripeness"].fillna(0).mean())
        agg_econ = float(data["economic_significance"].fillna(0).mean())
        agg_score = float(data["hospital_potential"].fillna(0).mean())

        def _lerp(a, b, t):
            return int(round(a + (b - a) * t))

        rscore = max(0.0, min(100.0, agg_ripe))
        if rscore <= 50.0:
            t = rscore / 50.0
            r = _lerp(220, 245, t)
            g = _lerp(38, 158, t)
            b = _lerp(38, 11, t)
            rs = _lerp(153, 161, t)
            gs = _lerp(27, 98, t)
            bs = _lerp(27, 7, t)
        else:
            t = (rscore - 50.0) / 50.0
            r = _lerp(245, 34, t)
            g = _lerp(158, 197, t)
            b = _lerp(11, 94, t)
            rs = _lerp(161, 21, t)
            gs = _lerp(98, 128, t)
            bs = _lerp(7, 61, t)

        bubble_fill = f"rgba({r},{g},{b},0.45)"
        bubble_stroke = f"rgba({rs},{gs},{bs},0.95)"

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
            f'<rect x="0" y="0" width="{w}" height="{h}" fill="#ffffff"/>'
            + bg_rects
            + f'<rect x="{ml}" y="{mt}" width="{pw:.1f}" height="{ph:.1f}" fill="none" stroke="#d1d5db" stroke-width="1"/>'
            f'<line x1="{ml+pw/3:.1f}" y1="{mt}" x2="{ml+pw/3:.1f}" y2="{mt+ph}" stroke="#e5e7eb" stroke-width="1"/>'
            f'<line x1="{ml+2*pw/3:.1f}" y1="{mt}" x2="{ml+2*pw/3:.1f}" y2="{mt+ph}" stroke="#e5e7eb" stroke-width="1"/>'
            f'<line x1="{ml}" y1="{mt+ph/3:.1f}" x2="{ml+pw}" y2="{mt+ph/3:.1f}" stroke="#e5e7eb" stroke-width="1"/>'
            f'<line x1="{ml}" y1="{mt+2*ph/3:.1f}" x2="{ml+pw}" y2="{mt+2*ph/3:.1f}" stroke="#e5e7eb" stroke-width="1"/>'
            + circle
            + f'<text x="{ml+pw/2:.1f}" y="{h-8}" fill="#1a1a1a" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle">ABILITY TO SUCCEED</text>'
            + f'<text x="0" y="{mt+ph/2:.1f}" fill="#1a1a1a" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle" transform="rotate(-90 0 {mt+ph/2:.1f})">MARKET ATTRACTIVENESS</text>'
            + f'<text x="{ml}" y="{mt+ph+16}" fill="#1a1a1a" font-size="10" font-weight="600" letter-spacing="0.03em">LOW</text>'
            + f'<text x="{ml+pw/2:.1f}" y="{mt+ph+16}" fill="#1a1a1a" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="middle">MED</text>'
            + f'<text x="{ml+pw}" y="{mt+ph+16}" fill="#1a1a1a" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">HIGH</text>'
            + f'<text x="{ml-8}" y="{mt+ph}" fill="#1a1a1a" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">LOW</text>'
            + f'<text x="{ml-8}" y="{mt+ph/2:.1f}" fill="#1a1a1a" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">MED</text>'
            + f'<text x="{ml-8}" y="{mt+8}" fill="#1a1a1a" font-size="10" font-weight="600" letter-spacing="0.03em" text-anchor="end">HIGH</text>'
            + "</svg>"
        )

        tier1_defs = [
            ("zip_code", "Five-digit ZIP code for the record."),
            ("data_year", "Year the ZIP-level Tier 1 snapshot represents."),
            ("total_population", "Total resident population in the ZIP."),
            ("population_growth_rate_2yr", "Two-year percent population growth."),
            ("net_population_change_2yr", "Net resident count change over two years."),
            ("historical_year", "Baseline historical year used for trend comparison."),
            ("age_0_17", "Population count ages 0 through 17."),
            ("age_18_44", "Population count ages 18 through 44."),
            ("age_45_64", "Population count ages 45 through 64."),
            ("age_65_plus", "Population count ages 65 and older."),
            ("age_0_17_pct", "Share of population ages 0 through 17."),
            ("age_18_44_pct", "Share of population ages 18 through 44."),
            ("age_45_64_pct", "Share of population ages 45 through 64."),
            ("age_65_plus_pct", "Share of population ages 65 and older."),
            ("median_age", "Median resident age in the ZIP."),
            ("white_alone", "Count of residents identifying as White alone."),
            ("black_alone", "Count of residents identifying as Black alone."),
            ("asian_alone", "Count of residents identifying as Asian alone."),
            ("hispanic_latino", "Count of residents identifying as Hispanic/Latino."),
            ("white_pct", "Percent of residents identifying as White."),
            ("black_pct", "Percent of residents identifying as Black."),
            ("asian_pct", "Percent of residents identifying as Asian."),
            ("hispanic_pct", "Percent of residents identifying as Hispanic/Latino."),
            ("median_household_income", "Median annual household income."),
            ("bachelors_or_higher", "Count of adults with bachelor's degree or higher."),
            ("bachelors_or_higher_pct", "Percent of adults with bachelor's degree or higher."),
            ("birth_rate_per_1000", "Birth events per 1,000 residents."),
            ("in_migration_from_other_state", "Count of residents moving in from other states."),
            ("in_migration_rate", "In-migration as a percent of population."),
            ("unemployed", "Count of unemployed residents in labor force context."),
            ("unemployment_rate", "Unemployment as a percent of labor force."),
            ("per_capita_income", "Average income per resident."),
            ("per_capita_income_growth_2yr", "Two-year percent growth in per-capita income."),
            ("top_industry", "Largest employment industry in the local economy."),
            ("top_industry_employment", "Employment count in the top local industry."),
            ("industry_agriculture", "Employment count in agriculture-related industries."),
            ("industry_construction", "Employment count in construction."),
            ("industry_manufacturing", "Employment count in manufacturing."),
            ("industry_retail", "Employment count in retail trade."),
            ("industry_finance", "Employment count in finance and insurance."),
            ("industry_professional_tech", "Employment count in professional and technical services."),
            ("industry_education_and_health", "Employment count in education and healthcare services."),
            ("industry_arts_entertainment", "Employment count in arts, entertainment, and recreation."),
            ("industry_other_services", "Employment count in other services."),
            ("industry_public_administration", "Employment count in public administration."),
            ("county_name", "County name associated with the ZIP."),
            ("county_flips", "County FIPS code associated with the ZIP."),
            ("state_fips", "State FIPS code."),
            ("state_name", "State name."),
            ("msa", "Whether the ZIP is in a metropolitan statistical area (Yes/No)."),
            ("msa_name", "Metropolitan statistical area name when applicable."),
            ("county_level_gdp_thousands", "County GDP level in thousands of dollars."),
            ("county_level_gdp_growth_5yr", "Five-year county GDP growth rate."),
            ("gdp_year", "Reference year for county GDP values."),
            ("msa_level_gdp_millions", "MSA GDP level in millions of dollars."),
            ("msa_gdp_growth_5yr", "Five-year MSA GDP growth rate."),
            ("msa_gdp_year", "Reference year for MSA GDP values."),
        ]

        tier2_defs = [
            ("Commercial % of Covered Lives", "Share of insured population covered by commercial plans."),
            ("Medicare Beneficiary Count & Penetration", "Total Medicare beneficiaries and their share of total population."),
            ("Medicare Advantage Penetration", "Share of Medicare beneficiaries enrolled in MA plans."),
            ("Medicaid Enrollment & Penetration", "Total Medicaid-covered lives and market share of Medicaid."),
            ("Dual-Eligible Population", "Population enrolled in both Medicare and Medicaid."),
            ("Uninsured Rate", "Share of residents without health insurance."),
            ("Fully Insured vs Self-Insured Ratio", "Employer coverage mix between fully insured and ASO/self-funded."),
            ("Health Plan Market Share by MCO", "Concentration and split of covered lives across managed care plans."),
            ("Health Insurance Exchange Enrollment", "Marketplace enrollment footprint in the local market."),
            ("Inpatient Discharges per 100K", "Hospital discharge volume normalized by population."),
            ("Inpatient Beds per 100K", "Licensed/available inpatient bed supply normalized by population."),
            ("IP Bed Utilization Rate", "Occupied bed-days as a share of available bed capacity."),
            ("ED Visits per 100K", "Emergency utilization intensity normalized by population."),
            ("Hospital Outpatient Visits per 1,000", "Outpatient utilization intensity normalized per 1,000 residents."),
            ("Medicare Discharges per 1,000 Beneficiaries", "Inpatient Medicare utilization among Medicare beneficiaries."),
            ("Health System Market Share", "Relative control of demand/volume by major systems in the market."),
            ("Number of Facilities by Type", "Supply footprint split across hospitals, ASCs, labs, imaging, urgent care, SNFs."),
            ("Net New IP Bed Inventory", "Net change in bed capacity after openings/closures/expansions."),
            ("Competitor Revenue & Financial Performance", "Local competitor scale and financial resilience indicators."),
            ("Market Consolidation Level (HHI)", "Market concentration metric (higher HHI = more concentrated market)."),
            ("Market Control", "Degree to which leading systems can influence referrals, pricing, and access."),
            ("Provider Alignment Stage", "Maturity of physician and provider alignment with systems/networks."),
            ("Value-Based Care Adoption Stage", "Maturity of participation in risk/value-based payment models."),
            ("Physician Supply: Primary Care per 100K", "Primary care clinician availability normalized by population."),
            ("Physician Supply: Specialty per 100K", "Specialist clinician availability normalized by population."),
            ("Physician Age Profile", "Age distribution of the provider base indicating pipeline/retirement risk."),
            ("Burnout / Intent to Reduce Services", "Provider strain signal tied to potential access contraction."),
            ("Operating Margin", "Operating profitability of local providers/facilities."),
            ("Net Patient Service Revenue", "Patient-care revenue base indicating provider financial scale."),
        ]

        tier3_defs = [
            ("Cardiovascular: IP Discharges & % of Total", "Cardiac inpatient demand and share of overall inpatient volume."),
            ("Oncology: IP Discharges & Hospitalization Rate", "Cancer-related inpatient demand and admission intensity."),
            ("Women's Health: IP Volume & % of Total", "Women's health inpatient footprint and service-line share."),
            ("Orthopedics: IP Discharges & ASC Migration Rate", "Ortho inpatient demand and shift toward ambulatory settings."),
            ("Neurosciences: IP Discharges & Stroke Rate", "Neuro/stroke-related inpatient demand intensity."),
            ("General Surgery: IP Volume & Ambulatory Migration", "Surgical inpatient volume and migration to outpatient care."),
            ("Neonatal / Normal Newborn: IP Volume", "Maternity/newborn inpatient demand signal."),
            ("ASC Market Penetration & Competitor Count", "Ambulatory surgery penetration and local competitor density."),
            ("Infusion Therapy: Ambulatory & Home Trends", "Shift of infusion demand across outpatient and home settings."),
            ("Age-Adjusted Disease Hospitalization Rates", "Burden-of-disease intensity normalized for age structure."),
            ("Alternative Payment Model Participation", "Service-line participation in bundled/risk-based reimbursement models."),
        ]

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
            f'{svg}'
            '</div>'
            '<div class="def-card">'
            '<div class="def-title">Dimensions</div>'
            '<div class="def-body">'
            '<div class="def-dim"><b>Construct 1 - Market Attractiveness (1-3, vertical axis)</b>: '
            'How structurally favorable the market is to pursue growth (demand, growth, economics, access, competitive intensity). '
            '<br><i>Interpretation:</i> Is this market worth being in or expanding in?</div>'
            '<div class="def-dim"><b>Construct 2 - Ability to Succeed (1-3, horizontal axis)</b>: '
            'Relative capability to win and sustain advantage in that market (brand/network, outcomes, referral ties, cost position, feasibility). '
            '<br><i>Interpretation:</i> Can we realistically win here versus competitors given our assets and constraints?</div>'
            '<div class="def-dim"><b>Construct 3 - Ripeness (1-3, bubble color: red to yellow to green)</b>: '
            'How actionable the opportunity is now, based on stage-gate signals (timing, readiness, and execution conditions). '
            '<br><i>Interpretation:</i> Is this opportunity ready to move now?</div>'
            '<div class="def-dim"><b>Construct 4 - Economic Significance (1-3, bubble size)</b>: '
            'Magnitude of value at stake if pursued successfully, used to scale diligence intensity and governance attention '
            '(revenue potential, cost/capital exposure, margin quality, portfolio impact). '
            '<br><i>Interpretation:</i> How important of a decision is this, and what analysis depth is warranted?</div>'
            '</div>'
            '</div>'
            '<div class="def-card">'
            '<div class="def-title">Tier Factors</div>'
            + _tier_defs_dropdown("Tier 1", tier1_defs)
            + _tier_defs_dropdown("Tier 2", tier2_defs)
            + _tier_defs_dropdown("Tier 3", tier3_defs)
            + '</div>'
            '<div class="def-card def-card-formula">'
            '<div class="def-title">Market Score Formula</div>'
            '<div class="def-body"><b>Market Score</b> is a ZIP-level composite that combines four dimensions: '
            'Market Attractiveness (structural favorability for growth), '
            'Ability to Succeed (our practical ability to win versus competitors), '
            'Ripeness (near-term actionability based on stage-gate readiness), and '
            'Economic Significance (magnitude of value, exposure, and portfolio impact). '
            'This score drives map coloring and rank ordering.</div>'
            '<div class="def-formula">'
            '<div class="def-formula-eq">Market Score = w1·Tier 1 + w2·Tier 2 + w3·Tier 3</div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 1</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 2</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '<div class="def-formula-row"><span class="def-chip">Tier 3</span><span>= Attractiveness, Ability to Win, Ripeness, Economic Significance</span></div>'
            '</div>'
            '<div class="def-ui-banner">'
            '<div class="def-ui-banner-title">Market Score UI</div>'
            '<div class="def-score-legend">'
            '<span class="def-score-edge">LOW</span>'
            '<span class="def-score-gradient"></span>'
            '<span class="def-score-edge">HIGH</span>'
            '</div>'
            '</div>'
            '</div>'
            '<div class="def-card def-card-formula">'
            '<div class="def-title">Entity Formula</div>'
            '<div class="def-body"><b>Entity Score</b> applies the same four-construct logic at the provider-site level. '
            'Each entity is evaluated on local Market Attractiveness (quality of the surrounding market), '
            'Ability to Succeed (competitive and operational win potential), '
            'Ripeness (how actionable the opportunity is now), and Economic Significance '
            '(value at stake and downside exposure), so entities can be compared consistently within and across ZIPs.</div>'
            '<div class="def-formula">'
            '<div class="def-formula-eq">Entity Score = w1·Tier 1 + w2·Tier 2 + w3·Tier 3</div>'
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
                f'<p style="font-size:0.98rem;color:#1a1a1a;letter-spacing:0.01em;'
                f'font-family:Open Sans,Segoe UI,Tahoma,Arial,sans-serif;'
                f'font-weight:700;margin:4px 8px 10px 18px;padding:0;">'
                f'{len(matched):,} Zip Codes</p>'
            )
        return ui.HTML(
            f'<p style="font-size:0.98rem;color:#1a1a1a;letter-spacing:0.01em;'
            f'font-family:Open Sans,Segoe UI,Tahoma,Arial,sans-serif;'
            f'font-weight:700;margin:4px 8px 10px 18px;padding:0;">'
            f'{total_count:,} Zip Codes</p>'
        )

    @render.ui
    def leaderboard():
        MAX_ROWS = 200
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
        else:
            ranked = ranked.head(MAX_ROWS)

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

        th_bg = "background:#fff8f0;"
        header = (
            '<table style="width:96%;margin:0 auto;font-size:0.78rem;color:#1a1a1a;'
            'border-collapse:collapse;">'
            '<thead><tr style="position:sticky;top:0;z-index:2;">'
            f'<th style="text-align:center;padding:4px 10px;color:#ff7f00;'
            f'font-weight:600;font-size:0.72rem;border-bottom:1px solid #ffe0b2;{th_bg}">#</th>'
            f'<th style="text-align:left;padding:4px 10px;color:#ff7f00;'
            f'font-weight:600;font-size:0.72rem;border-bottom:1px solid #ffe0b2;{th_bg}">ZIP</th>'
            f'<th style="text-align:left;padding:4px 10px;color:#ff7f00;'
            f'font-weight:600;font-size:0.72rem;border-bottom:1px solid #ffe0b2;{th_bg}">State</th>'
            f'<th style="text-align:right;padding:4px 25px 4px 10px;color:#ff7f00;'
            f'font-weight:600;font-size:0.72rem;border-bottom:1px solid #ffe0b2;{th_bg}">Market Score</th>'
            '</tr></thead><tbody>'
        )

        medal = {1: "#d4a017", 2: "#a0a0a0", 3: "#b87333"}
        parts = []
        for rank, zc, st, score in zip(
            show["rank"], show["zip_key"], show["state"], show["hospital_potential"]
        ):
            rank = int(rank)
            score = float(score)
            border = "border-top:1px solid #ffe0b2;" if rank > 1 else ""

            if rank <= 3:
                mc = medal[rank]
                glow = {1: "0 0 3px rgba(212,160,23,0.4)",
                        2: "0 0 3px rgba(160,160,160,0.35)",
                        3: "0 0 3px rgba(184,115,51,0.35)"}
                rc = (f'<span style="display:inline-flex;align-items:center;'
                      f'justify-content:center;width:22px;height:22px;'
                      f'border-radius:50%;background:linear-gradient(145deg,{mc} 40%,'
                      f'rgba(255,255,255,0.25) 70%,{mc});'
                      f'color:#fff;font-size:0.6rem;font-weight:700;'
                      f'box-shadow:{glow[rank]};">{rank}</span>')
                zs = f"font-weight:700;color:{mc};"
                ss = f"font-weight:700;color:{mc};"
            else:
                rc = (f'<span style="display:inline-flex;align-items:center;'
                      f'justify-content:center;width:22px;height:22px;'
                      f'border-radius:50%;background:#f0ebe4;'
                      f'color:#1a1a1a;font-size:0.6rem;font-weight:600;">'
                      f'{rank}</span>')
                zs = "font-weight:500;color:#1a1a1a;"
                ss = "font-weight:500;color:#1a1a1a;"

            parts.append(
                f'<tr class="leaderboard-zip" data-zip="{zc}" data-state="{st}"'
                f' style="cursor:pointer;" title="Go to {zc}">'
                f'<td style="padding:6px 16px 10px 10px;{border}line-height:1;text-align:center;">'
                f'{rc}</td>'
                f'<td style="padding:6px 10px 10px 14px;{border}{zs}">{zc}</td>'
                f'<td style="padding:6px 10px 10px 10px;{border}color:#1a1a1a;font-size:0.72rem;">{st}</td>'
                f'<td style="padding:6px 25px 10px 10px;{border}text-align:right;{ss}">{score:.1f}</td>'
                f'</tr>'
            )

        return ui.HTML(f'{header}{"".join(parts)}</tbody></table>')

    @render.ui
    def map_container():
        state_val = input.state()
        _ = map_version()
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
        ))


# App
app = App(app_ui, server, static_assets=WWW_DIR)