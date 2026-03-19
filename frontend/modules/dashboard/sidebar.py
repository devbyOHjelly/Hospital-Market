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


_TIER2_NA_FACTORS = [
    "Commercial % of Covered Lives",
    "Dual-Eligible Population",
    "Fully Insured vs Self-Insured Ratio",
    "Health Plan Market Share by MCO",
    "Health Insurance Exchange Enrollment",
    "Health System Market Share",
    "Net New IP Bed Inventory",
    "Competitor Revenue & Financial Performance",
    "Market Control",
    "Provider Alignment Stage",
    "Value-Based Care Adoption Stage",
    "Physician Age Profile",
    "Burnout / Intent to Reduce Services",
]


def _safe_float(val, default=0.0):
    try:
        v = float(val)
        return v if v == v else default
    except (TypeError, ValueError):
        return default


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


def _clip_norm(value, lo, hi, invert=False):
    v = _safe_float(value)
    if hi <= lo:
        return 50.0
    r = (v - lo) / (hi - lo)
    r = max(0.0, min(1.0, r))
    if invert:
        r = 1.0 - r
    return r * 100.0


def _market_framework_html(
    selected: list[dict],
    selected_option: str = "attractiveness_score_opt2",
    tier_weights: dict | None = None,
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

    # Color reflects ripeness. With no Tier-2/3 data, keep low-ripeness red.
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


def _build_tier2_rows(selected, _avg_fn, _fmt_fn):
    """Build aggregate Tier 2 rows from selected ZIP properties."""
    na = '<span style="color:#1a1a1a;">N/A</span>'

    avg_hhi = _avg_fn("hhi_market_concentration")
    if avg_hhi and avg_hhi > 0:
        if avg_hhi > 2500:
            hhi_label = f"{int(avg_hhi):,} (Concentrated)"
        elif avg_hhi > 1500:
            hhi_label = f"{int(avg_hhi):,} (Moderate)"
        else:
            hhi_label = f"{int(avg_hhi):,} (Competitive)"
    else:
        hhi_label = na

    bene_total = sum(_safe_float(z.get("bene_count")) for z in selected)
    bene_pen = _avg_fn("medicare_beneficiary_penetration_pct")
    total_pop = sum(_safe_float(z.get("total_population")) for z in selected)
    total_beds = sum(_safe_float(z.get("total_beds")) for z in selected)
    total_discharges = sum(_safe_float(z.get("total_discharges")) for z in selected)
    if (bene_pen is None or bene_pen == 0) and total_pop > 0 and bene_total > 0:
        bene_pen = (bene_total / total_pop) * 100.0

    beds_per_100k = _avg_fn("inpatient_beds_per_100k")
    if (beds_per_100k is None or beds_per_100k == 0) and total_pop > 0 and total_beds > 0:
        beds_per_100k = (total_beds / total_pop) * 100_000.0

    discharges_per_100k = _avg_fn("inpatient_discharges_per_100k")
    if (
        (discharges_per_100k is None or discharges_per_100k == 0)
        and total_pop > 0
        and total_discharges > 0
    ):
        discharges_per_100k = (total_discharges / total_pop) * 100_000.0

    ed_per_100k = _avg_fn("ed_visits_per_100k")
    if (ed_per_100k is None or ed_per_100k == 0) and total_pop > 0 and bene_total > 0:
        ed_per_1k_bene = _avg_fn("er_visits_per_1k")
        if ed_per_1k_bene not in (None, 0):
            est_ed_visits = (ed_per_1k_bene * bene_total) / 1000.0
            ed_per_100k = (est_ed_visits / total_pop) * 100_000.0

    bene_label = (
        f"{int(bene_total):,} ({bene_pen:.1f}%)"
        if bene_total > 0 and bene_pen not in (None, 0)
        else (_fmt_fn(bene_total, "int") if bene_total > 0 else na)
    )

    rows = [
        ("Physician Supply: Primary Care per 100K", _fmt_fn(_avg_fn("pcp_per_100k"), "num")),
        (
            "Physician Supply: Specialty per 100K",
            _fmt_fn(_avg_fn("specialist_per_100k"), "num"),
        ),
        (
            "Number of Facilities by Type",
            _fmt_fn(sum(_safe_float(z.get("facility_total")) for z in selected), "int"),
        ),
        ("Inpatient Beds per 100K", _fmt_fn(beds_per_100k, "num")),
        ("Inpatient Discharges per 100K", _fmt_fn(discharges_per_100k, "num")),
        ("IP Bed Utilization Rate", _fmt_fn(_avg_fn("bed_utilization_rate"), "pct")),
        ("ED Visits per 100K", _fmt_fn(ed_per_100k, "num")),
        (
            "Hospital Outpatient Visits per 1,000",
            _fmt_fn(_avg_fn("outpatient_visits_per_1k"), "num"),
        ),
        ("Medicare Beneficiary Count & Penetration", bene_label),
        ("Medicare Advantage Penetration", _fmt_fn(_avg_fn("ma_penetration"), "pct")),
        ("Medicaid Enrollment & Penetration", _fmt_fn(_avg_fn("medicaid_pct"), "pct")),
        (
            "Medicare Discharges per 1,000 Beneficiaries",
            _fmt_fn(_avg_fn("ip_stays_per_1k"), "num"),
        ),
        ("Uninsured Rate", _fmt_fn(_avg_fn("uninsured_rate"), "pct")),
        ("Operating Margin", _fmt_fn(_avg_fn("operating_margin_pct"), "pct")),
        (
            "Net Patient Service Revenue",
            _fmt_fn(_avg_fn("net_patient_revenue", skip_negative=True), "money"),
        ),
        ("Market Consolidation Level (HHI)", hhi_label),
    ]
    for f in _TIER2_NA_FACTORS:
        rows.append((f, na))
    return rows


def _build_tier2_rows_single(zd, _fmt_fn):
    """Build per-ZIP Tier 2 rows from a single ZIP dict."""
    na = '<span style="color:#1a1a1a;">N/A</span>'

    def _g(key):
        return _safe_float(zd.get(key))

    pop = _g("total_population")
    beds_per_100k = _g("inpatient_beds_per_100k")
    if beds_per_100k == 0 and pop > 0 and _g("total_beds") > 0:
        beds_per_100k = (_g("total_beds") / pop) * 100_000.0

    discharges_per_100k = _g("inpatient_discharges_per_100k")
    if discharges_per_100k == 0 and pop > 0 and _g("total_discharges") > 0:
        discharges_per_100k = (_g("total_discharges") / pop) * 100_000.0

    bene_pen = _g("medicare_beneficiary_penetration_pct")
    if bene_pen == 0 and pop > 0 and _g("bene_count") > 0:
        bene_pen = (_g("bene_count") / pop) * 100.0

    ed_per_100k = _g("ed_visits_per_100k")
    if ed_per_100k == 0 and pop > 0 and _g("bene_count") > 0 and _g("er_visits_per_1k") > 0:
        est_ed_visits = (_g("er_visits_per_1k") * _g("bene_count")) / 1000.0
        ed_per_100k = (est_ed_visits / pop) * 100_000.0

    facility_detail = ""
    ft = _g("facility_total")
    if ft > 0:
        parts = []
        for label, key in [
            ("Hosp", "facility_hospital"),
            ("ASC", "facility_asc"),
            ("Lab", "facility_lab"),
            ("Img", "facility_imaging"),
            ("UC", "facility_urgent_care"),
            ("SNF", "facility_snf"),
        ]:
            v = _g(key)
            if v > 0:
                parts.append(f"{label}:{int(v)}")
        facility_detail = f'{int(ft)} ({", ".join(parts)})' if parts else f"{int(ft)}"
    else:
        facility_detail = na

    hhi_val = _g("hhi_market_concentration")
    if hhi_val > 0:
        if hhi_val > 2500:
            hhi_label = f"{int(hhi_val):,} (Concentrated)"
        elif hhi_val > 1500:
            hhi_label = f"{int(hhi_val):,} (Moderate)"
        else:
            hhi_label = f"{int(hhi_val):,} (Competitive)"
    else:
        hhi_label = na

    rows = [
        (
            "Physician Supply: Primary Care per 100K",
            _fmt_fn(_g("pcp_per_100k"), "num") if _g("pcp_per_100k") else na,
        ),
        (
            "Physician Supply: Specialty per 100K",
            _fmt_fn(_g("specialist_per_100k"), "num") if _g("specialist_per_100k") else na,
        ),
        ("Number of Facilities by Type", facility_detail),
        ("Inpatient Beds per 100K", _fmt_fn(beds_per_100k, "num") if beds_per_100k else na),
        (
            "Inpatient Discharges per 100K",
            _fmt_fn(discharges_per_100k, "num") if discharges_per_100k else na,
        ),
        (
            "IP Bed Utilization Rate",
            _fmt_fn(_g("bed_utilization_rate"), "pct") if _g("bed_utilization_rate") else na,
        ),
        ("ED Visits per 100K", _fmt_fn(ed_per_100k, "num") if ed_per_100k else na),
        (
            "Hospital Outpatient Visits per 1,000",
            _fmt_fn(_g("outpatient_visits_per_1k"), "num") if _g("outpatient_visits_per_1k") else na,
        ),
        (
            "Medicare Beneficiary Count & Penetration",
            (
                f'{int(_g("bene_count")):,} ({bene_pen:.1f}%)'
                if _g("bene_count") and bene_pen
                else (_fmt_fn(_g("bene_count"), "int") if _g("bene_count") else na)
            ),
        ),
        (
            "Medicare Advantage Penetration",
            _fmt_fn(_g("ma_penetration"), "pct") if _g("ma_penetration") else na,
        ),
        (
            "Medicaid Enrollment & Penetration",
            _fmt_fn(_g("medicaid_pct"), "pct") if _g("medicaid_pct") else na,
        ),
        (
            "Medicare Discharges per 1,000 Beneficiaries",
            _fmt_fn(_g("ip_stays_per_1k"), "num") if _g("ip_stays_per_1k") else na,
        ),
        ("Uninsured Rate", _fmt_fn(_g("uninsured_rate"), "pct") if _g("uninsured_rate") else na),
        (
            "Operating Margin",
            _fmt_fn(_g("operating_margin_pct"), "pct") if _g("operating_margin_pct") else na,
        ),
        (
            "Net Patient Service Revenue",
            _fmt_fn(_g("net_patient_revenue"), "money") if _g("net_patient_revenue") else na,
        ),
        ("Market Consolidation Level (HHI)", hhi_label),
    ]
    for f in _TIER2_NA_FACTORS:
        rows.append((f, na))
    return rows


def market_tab_html(
    selected: list[dict],
    entities_df=None,
    selected_option: str = "attractiveness_score_opt2",
    tier_weights: dict | None = None,
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
    total_hosp = sum(int(z.get("hospital_count", 0)) for z in selected)
    avg_ent = total_ent / count
    avg_hosp = total_hosp / count

    hosp_by_type = {}
    hosp_by_ownership = {}
    avg_rating = None
    emergency_count = 0
    total_hospitals_with_data = 0
    if entities_df is not None and len(entities_df) > 0:
        hospitals = entities_df[entities_df.get("entity_type", pd.Series()) == "hospital"]
        if len(hospitals) > 0:
            total_hospitals_with_data = len(hospitals)
            if "hospital_type" in hospitals.columns:
                hosp_by_type = hospitals["hospital_type"].dropna().value_counts().head(5).to_dict()
            if "ownership" in hospitals.columns:
                hosp_by_ownership = (
                    hospitals["ownership"].dropna().value_counts().head(5).to_dict()
                )
            if "hospital_rating" in hospitals.columns:
                ratings = pd.to_numeric(hospitals["hospital_rating"], errors="coerce").dropna()
                if len(ratings) > 0:
                    avg_rating = ratings.mean()
            if "emergency_services" in hospitals.columns:
                emergency_count = (
                    hospitals["emergency_services"].astype(str).str.lower() == "yes"
                ).sum()

    title_html = ""

    score_box = (
        f'<div class="market-detail-block">'
        f"{_market_framework_html(selected, selected_option=selected_option, tier_weights=tier_weights)}"
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

    def _avg(key, skip_negative=False):
        vals = [float(z.get(key, 0) or 0) for z in selected]
        if skip_negative:
            vals = [v for v in vals if v > 0]
        return sum(vals) / len(vals) if vals else None

    def _fmt_val(val, fmt="num", prefix="", suffix=""):
        if val is None or val == 0:
            return '<span style="color:#1a1a1a;">N/A</span>'
        if fmt == "int":
            return f"{prefix}{int(val):,}{suffix}"
        if fmt == "pct":
            return f"{val:.1f}%"
        if fmt == "pct_signed":
            color = "#22c55e"
            return f'<span style="color:{color};">{val:+.1f}%</span>'
        if fmt == "money":
            if val < 0:
                return '<span style="color:#1a1a1a;">N/A</span>'
            return f"${int(val):,}"
        if fmt == "rate":
            return f"{val:.0f}/1,000"
        if fmt == "str":
            return (
                str(val)
                if val and str(val) != "Unknown"
                else '<span style="color:#1a1a1a;">N/A</span>'
            )
        return f"{val:.1f}"

    from collections import Counter

    _TIER1_ALIASES = {
        "zip_code": ("zipcode", "zip"),
        "county_flips": ("county_fips",),
        "state_name": ("state", "state_abbr"),
        "white_pct": ("pct_white",),
        "black_pct": ("pct_black",),
        "asian_pct": ("pct_asian",),
        "hispanic_pct": ("pct_hispanic",),
        "in_migration_rate": ("in_migration_pct",),
        "in_migration_pct": ("in_migration_rate",),
        "birth_rate_per_1000": ("birth_rate",),
        "top_industry_employment": ("top_industry_employee_count",),
    }

    def _tier1_get(row, key):
        if key in row and row.get(key) not in (None, "", "nan", "None"):
            return row.get(key)
        for alt in _TIER1_ALIASES.get(key, ()):
            if alt in row and row.get(alt) not in (None, "", "nan", "None"):
                return row.get(alt)
        # Fallback: normalized lookup by collapsing underscores/case.
        nk = str(key).replace("_", "").lower()
        for rk, rv in row.items():
            if str(rk).replace("_", "").lower() == nk and rv not in (None, "", "nan", "None"):
                return rv
        return row.get(key)

    def _to_num(raw):
        if raw is None:
            return None
        if isinstance(raw, (int, float)):
            return float(raw)
        s = str(raw).strip()
        if not s or s.lower() in ("nan", "none", "null"):
            return None
        # normalize common formatted strings like "$35,575", "6.1%", "39/1,000"
        s = s.replace("$", "").replace(",", "").replace("%", "")
        s = s.replace("/1000", "").replace("/1,000", "")
        try:
            return float(s)
        except (TypeError, ValueError):
            return None

    def _avg_num(key):
        vals = []
        for z in selected:
            v = _to_num(_tier1_get(z, key))
            if v is not None and v == v:
                vals.append(v)
        return (sum(vals) / len(vals)) if vals else None

    def _mode_str(key):
        vals = [
            str(_tier1_get(z, key)).strip()
            for z in selected
            if _tier1_get(z, key) not in (None, "", "nan", "None")
        ]
        return Counter(vals).most_common(1)[0][0] if vals else None

    def _fmt_t1(raw, fmt):
        if fmt == "str":
            return _fmt_val(raw, "str")
        try:
            num = float(raw)
        except (TypeError, ValueError):
            num = None
        if num is None:
            return '<span style="color:#1a1a1a;">N/A</span>'
        if fmt == "int":
            return f"{int(round(num)):,}"
        if fmt == "pct":
            return f"{num:.1f}%"
        if fmt == "pct_signed":
            return f"{num:+.1f}%"
        if fmt == "money":
            return f"${int(round(num)):,}"
        if fmt == "rate":
            return f"{num:.0f}/1,000"
        return f"{num:.1f}"

    tier1_specs = [
        ("ZIP Code", "zip_code", "str", "mode"),
        ("Data Year", "data_year", "int", "mode"),
        ("Total Population", "total_population", "int", "avg"),
        ("Population Growth Rate (2yr)", "population_growth_rate_2yr", "pct_signed", "avg"),
        ("Net Population Change (2yr)", "net_population_change_2yr", "int", "avg"),
        ("Historical Year", "historical_year", "int", "mode"),
        ("Age 0-17", "age_0_17", "int", "avg"),
        ("Age 18-44", "age_18_44", "int", "avg"),
        ("Age 45-64", "age_45_64", "int", "avg"),
        ("Age 65+", "age_65_plus", "int", "avg"),
        ("Age 0-17 %", "age_0_17_pct", "pct", "avg"),
        ("Age 18-44 %", "age_18_44_pct", "pct", "avg"),
        ("Age 45-64 %", "age_45_64_pct", "pct", "avg"),
        ("Age 65+ %", "age_65_plus_pct", "pct", "avg"),
        ("Median Age", "median_age", "num", "avg"),
        ("White Alone", "white_alone", "int", "avg"),
        ("Black Alone", "black_alone", "int", "avg"),
        ("Asian Alone", "asian_alone", "int", "avg"),
        ("Hispanic Latino", "hispanic_latino", "int", "avg"),
        ("White %", "white_pct", "pct", "avg"),
        ("Black %", "black_pct", "pct", "avg"),
        ("Asian %", "asian_pct", "pct", "avg"),
        ("Hispanic %", "hispanic_pct", "pct", "avg"),
        ("Median Household Income", "median_household_income", "money", "avg"),
        ("Bachelors or Higher", "bachelors_or_higher", "int", "avg"),
        ("Bachelors or Higher %", "bachelors_or_higher_pct", "pct", "avg"),
        ("Birth Rate per 1,000", "birth_rate_per_1000", "rate", "avg"),
        ("In-Migration from Other State", "in_migration_from_other_state", "int", "avg"),
        ("In-Migration Rate", "in_migration_rate", "pct", "avg"),
        ("Unemployed", "unemployed", "int", "avg"),
        ("Unemployment Rate", "unemployment_rate", "pct", "avg"),
        ("Per Capita Income", "per_capita_income", "money", "avg"),
        ("Per Capita Income Growth (2yr)", "per_capita_income_growth_2yr", "pct_signed", "avg"),
        ("Top Industry", "top_industry", "str", "mode"),
        ("Top Industry Employment", "top_industry_employment", "int", "avg"),
        ("Industry Agriculture", "industry_agriculture", "int", "avg"),
        ("Industry Construction", "industry_construction", "int", "avg"),
        ("Industry Manufacturing", "industry_manufacturing", "int", "avg"),
        ("Industry Retail", "industry_retail", "int", "avg"),
        ("Industry Finance", "industry_finance", "int", "avg"),
        ("Industry Professional/Tech", "industry_professional_tech", "int", "avg"),
        ("Industry Education & Health", "industry_education_and_health", "int", "avg"),
        ("Industry Arts & Entertainment", "industry_arts_entertainment", "int", "avg"),
        ("Industry Other Services", "industry_other_services", "int", "avg"),
        ("Industry Public Administration", "industry_public_administration", "int", "avg"),
        ("County Name", "county_name", "str", "mode"),
        ("County FIPS", "county_flips", "str", "mode"),
        ("State FIPS", "state_fips", "str", "mode"),
        ("State Name", "state_name", "str", "mode"),
        ("MSA (Yes/No)", "msa", "str", "mode"),
        ("MSA Name", "msa_name", "str", "mode"),
        ("County-level GDP (thousands)", "county_level_gdp_thousands", "money", "avg"),
        ("County GDP Growth (5yr)", "county_level_gdp_growth_5yr", "pct_signed", "avg"),
        ("GDP Year", "gdp_year", "int", "mode"),
        ("MSA-level GDP (millions)", "msa_level_gdp_millions", "money", "avg"),
        ("MSA GDP Growth (5yr)", "msa_gdp_growth_5yr", "pct_signed", "avg"),
        ("MSA GDP Year", "msa_gdp_year", "int", "mode"),
    ]

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
            "tier2",
            "tier3",
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

    preferred = [k for _, k, _, _ in tier1_specs]
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

    # User preference: parquet-driven factors should only appear in Tier 1.
    tier1_rows = all_rows_agg
    tier2_factors = []
    tier3_rows = []

    def _tier_dropdown(title, rows, open_default=False):
        tid = title.lower().replace(" ", "_")
        open_attr = " open" if open_default else ""
        html = (
            f'<details class="tier-dropdown" data-tier="{tid}"{open_attr}>'
            f'<summary class="tier-dropdown-summary">{title}</summary>'
            f'<div class="tier-dropdown-content">'
            f'<table style="width:100%;font-size:0.7rem;border-collapse:collapse;table-layout:fixed;">'
        )
        for label, val in rows:
            html += _row(label, val)
        html += "</table></div></details>"
        return html

    score_box += "</div></div>"

    header = ""

    items = ""
    for zd in selected:
        zc = zd.get("zipcode", "")
        st = zd.get("state", "")
        sc = float(zd.get("hospital_potential", 0) or 0)
        sc_color = COLORMAP(sc)
        ent_count = int(zd.get("entity_count", 0) or 0)
        hosp_count = int(zd.get("hospital_count", 0) or 0)
        row_pairs = [(_pretty_col(k), _fmt_dynamic(k, zd.get(k))) for k in ordered_keys]
        zt1 = _tier_dropdown("Tier 1", row_pairs if row_pairs else [("No parquet factors found", na)])
        zt2 = _tier_dropdown("Tier 2", [])
        zt3 = _tier_dropdown("Tier 3", [])

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
            f"{hosp_dropdown}{zt1}{zt2}{zt3}"
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

    return f'{title_html}{score_box}{header}<ul class="market-zip-list">{items}</ul>{persist_js}'


def _section_header(title: str) -> str:
    return (
        f'<tr><td colspan="2" style="padding:4px 0 1px;font-size:0.62rem;'
        f'color:#1a1a1a;text-transform:uppercase;letter-spacing:0.03em;">'
        f"{title}</td></tr>"
    )


def _row(label: str, value: str, color: str = "#1a1a1a") -> str:
    return (
        f'<tr><td style="color:#1a1a1a;padding:3px 8px 3px 0;font-size:0.7rem;'
        f'width:66%;white-space:nowrap;overflow:hidden;text-overflow:ellipsis;">{label}</td>'
        f'<td style="text-align:right;font-weight:600;color:{color};padding:3px 0;'
        f'font-size:0.7rem;width:34%;white-space:nowrap;">{value}</td></tr>'
    )


def _score_color(score: float) -> str:
    ratio = max(0, min(score, 100)) / 100.0
    g = int(255 - ratio * (255 - 127))
    b = int(255 - ratio * 255)
    return f"rgb(255,{g},{b})"
