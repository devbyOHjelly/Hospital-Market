"""Shared scoring / weighting logic for the Dash dashboard."""

from __future__ import annotations

import pandas as pd

from backend.agent.agent_config import SCORE_DEFINITIONS, DEFAULT_SCORE_COLUMN, RAW_TO_PCTILE

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

_DIMENSION_INDICATORS = {
    "attractiveness": [
        "age_65_plus_pct",
        "population_growth_rate_2yr",
        "age_45_64_pct",
        "birth_rate_per_1000",
        "total_population",
    ],
    "ability_to_win": [
        "unemployment_rate",
        "industry_public_administration",
    ],
    "ripeness": [
        "bachelors_or_higher_pct",
        "industry_education_and_health",
        "median_household_income",
        "per_capita_income_growth_2yr",
        "county_level_gdp_growth_5yr",
    ],
    "economic_significance": [
        "hispanic_pct",
        "black_pct",
        "median_age",
        "industry_agriculture",
        "industry_manufacturing",
    ],
}
_INVERTED_INDICATORS = {
    "unemployment_rate",
}


def default_option_component_weights() -> dict[str, dict[str, float]]:
    out: dict[str, dict[str, float]] = {}
    for score_col, score_def in SCORE_DEFINITIONS.items():
        weights: dict[str, float] = {}
        for component_col, meta in (score_def.get("components") or {}).items():
            weights[component_col] = float(meta.get("weight", 0.0)) * 100.0
        out[score_col] = weights
    return out


def default_construct_component_weights() -> dict[str, dict[str, dict[str, float]]]:
    out: dict[str, dict[str, dict[str, float]]] = {}
    for score_col in _SCORE_OPTION_CHOICES:
        out[score_col] = {}
        for dim, _ in _DIMENSION_META:
            cols = list(_DIMENSION_INDICATORS.get(dim, []))
            if not cols:
                out[score_col][dim] = {}
                continue

            if dim == "attractiveness":
                comp_defs = SCORE_DEFINITIONS.get(score_col, {}).get("components", {}) or {}
                dim_w: dict[str, float] = {}
                for raw_col in cols:
                    pct_col = RAW_TO_PCTILE.get(raw_col)
                    if pct_col and pct_col in comp_defs:
                        dim_w[raw_col] = float(comp_defs[pct_col].get("weight", 0.0)) * 100.0
                if dim_w and int(round(sum(dim_w.values()))) == 100:
                    out[score_col][dim] = dim_w
                    continue

            base = 100.0 / float(len(cols))
            ws = {c: float(int(base)) for c in cols}
            rem = int(round(100.0 - sum(ws.values())))
            for c in cols[: max(0, rem)]:
                ws[c] += 1.0
            out[score_col][dim] = ws
    return out


# Expose for definitions / settings UI
DIMENSION_META = _DIMENSION_META
TIER_META = _TIER_META
DEFAULT_TIER_WEIGHTS = _DEFAULT_TIER_WEIGHTS
SCORE_OPTION_CHOICES = _SCORE_OPTION_CHOICES
DIMENSION_INDICATORS = _DIMENSION_INDICATORS
INVERTED_INDICATORS = _INVERTED_INDICATORS


def apply_settings_weights(
    frame: pd.DataFrame,
    *,
    approved_option_component_weights: dict,
    approved_construct_component_weights: dict,
    approved_score_option: str,
    approved_tier_weights: dict,
) -> pd.DataFrame:
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
    for score_col, score_def in SCORE_DEFINITIONS.items():
        components = score_def.get("components") or {}
        comp_series: dict[str, pd.Series] = {}
        for pct_col, meta in components.items():
            s = None
            raw_col = pct_to_raw.get(pct_col)
            direction = str(meta.get("direction", "higher_is_better"))
            if score_col == "attractiveness_score_opt1" and raw_col and raw_col in data.columns:
                s = pd.to_numeric(data[raw_col], errors="coerce")
                if direction == "lower_is_better":
                    s = -1.0 * s
            elif pct_col in data.columns:
                s = pd.to_numeric(data[pct_col], errors="coerce")
            elif raw_col and raw_col in data.columns:
                raw = pd.to_numeric(data[raw_col], errors="coerce")
                rank_pct = raw.rank(pct=True, method="average")
                if direction == "lower_is_better":
                    rank_pct = 1.0 - rank_pct
                s = (rank_pct * 99.0).clip(0.0, 99.0)
            if s is not None:
                comp_series[pct_col] = s

        if not comp_series:
            if score_col in data.columns:
                data[score_col] = pd.to_numeric(data[score_col], errors="coerce").fillna(fallback).clip(0, 100)
            else:
                data[score_col] = fallback
            continue

        comp_df = pd.DataFrame(comp_series, index=data.index)
        option_weights_pct = approved_option_component_weights.get(score_col, {})
        comp_cols = list(comp_df.columns)
        pct_sum = sum(float(option_weights_pct.get(c, 0.0)) for c in comp_cols)
        if pct_sum <= 0:
            pct_sum = 100.0

        if score_col == "attractiveness_score_opt1":
            z_scores = (comp_df - comp_df.mean()) / comp_df.std()
            z_scores = z_scores.replace([float("inf"), float("-inf")], pd.NA)
            weighted_num = None
            weighted_den = None
            for pct_col in comp_cols:
                default_pct = float((components.get(pct_col) or {}).get("weight", 0.0)) * 100.0
                approved_pct = float(option_weights_pct.get(pct_col, default_pct))
                z_col = pd.to_numeric(z_scores[pct_col], errors="coerce")
                w_col = z_col.notna().astype(float) * approved_pct
                contrib = z_col.fillna(0.0) * approved_pct
                weighted_num = contrib if weighted_num is None else (weighted_num + contrib)
                weighted_den = w_col if weighted_den is None else (weighted_den + w_col)
            z_avg = (weighted_num / weighted_den.replace(0, pd.NA)) if weighted_num is not None else pd.Series(pd.NA, index=data.index)
            valid = z_avg.dropna()
            if len(valid) == 0:
                data[score_col] = fallback
            else:
                mn, mx = float(valid.min()), float(valid.max())
                if mx <= mn:
                    rescaled = z_avg * 0 + 50.0
                else:
                    rescaled = ((z_avg - mn) / (mx - mn) * 100.0)
                data[score_col] = pd.to_numeric(rescaled, errors="coerce").fillna(fallback).clip(0, 100).round(2)
            continue

        if score_col == "attractiveness_score_opt4":
            weighted_num = None
            weighted_den = None
            for pct_col in comp_cols:
                default_pct = float((components.get(pct_col) or {}).get("weight", 0.0)) * 100.0
                approved_pct = float(option_weights_pct.get(pct_col, default_pct))
                p_col = pd.to_numeric(comp_df[pct_col], errors="coerce")
                w_col = p_col.notna().astype(float) * approved_pct
                contrib = p_col.fillna(0.0) * approved_pct
                weighted_num = contrib if weighted_num is None else (weighted_num + contrib)
                weighted_den = w_col if weighted_den is None else (weighted_den + w_col)
            eq = (weighted_num / weighted_den.replace(0, pd.NA)) if weighted_num is not None else pd.Series(pd.NA, index=data.index)
            data[score_col] = pd.to_numeric(eq, errors="coerce").fillna(fallback).clip(0, 99).round(2)
            continue

        weighted = None
        for pct_col in comp_cols:
            default_pct = float((components.get(pct_col) or {}).get("weight", 0.0)) * 100.0
            approved_pct = float(option_weights_pct.get(pct_col, default_pct))
            contrib = pd.to_numeric(comp_df[pct_col], errors="coerce").fillna(0.0) * (approved_pct / float(pct_sum))
            weighted = contrib if weighted is None else (weighted + contrib)
        if weighted is not None:
            data[score_col] = pd.to_numeric(weighted, errors="coerce").fillna(fallback).clip(0.0, 99.0).round(2)

    construct_col_map = {
        "attractiveness": {"opt1": "attractiveness_score_opt1", "opt2": "attractiveness_score_opt2", "opt4": "attractiveness_score_opt4"},
        "ability_to_win": {"opt1": "win_score_opt1", "opt2": "win_score_opt2", "opt4": "win_score_opt4"},
        "ripeness": {"opt1": "strength_score_opt1", "opt2": "strength_score_opt2", "opt4": "strength_score_opt4"},
        "economic_significance": {"opt1": "rightness_score_opt1", "opt2": "rightness_score_opt2", "opt4": "rightness_score_opt4"},
    }

    def _construct_from_indicators(dim_key: str, opt: str) -> pd.Series | None:
        cols = _DIMENSION_INDICATORS.get(dim_key, [])
        parts: list[pd.Series] = []
        weights: list[float] = []
        dim_w = (
            approved_construct_component_weights.get(f"attractiveness_score_{opt}", {}).get(dim_key, {})
        )
        for raw_col in cols:
            if raw_col not in data.columns:
                continue
            raw = pd.to_numeric(data[raw_col], errors="coerce")
            if opt == "opt1":
                s = (-1.0 * raw) if raw_col in _INVERTED_INDICATORS else raw
            else:
                pct_col = RAW_TO_PCTILE.get(raw_col)
                if pct_col and pct_col in data.columns:
                    s = pd.to_numeric(data[pct_col], errors="coerce")
                    if raw_col in _INVERTED_INDICATORS:
                        s = 99.0 - s
                else:
                    rank_pct = raw.rank(pct=True, method="average")
                    if raw_col in _INVERTED_INDICATORS:
                        rank_pct = 1.0 - rank_pct
                    s = (rank_pct * 99.0).clip(0.0, 99.0)
            parts.append(s)
            weights.append(max(0.0, float(dim_w.get(raw_col, 0.0))))
        if not parts:
            return None
        comp_df = pd.concat(parts, axis=1)
        if sum(weights) <= 0:
            weights = [1.0] * len(parts)
        w_series = pd.Series(weights, index=comp_df.columns, dtype=float)
        if opt == "opt1":
            z = (comp_df - comp_df.mean()) / comp_df.std()
            z = z.replace([float("inf"), float("-inf")], pd.NA)
            wdf = z.notna().astype(float).mul(w_series, axis=1)
            num = z.fillna(0.0).mul(w_series, axis=1).sum(axis=1)
            den = wdf.sum(axis=1).replace(0, pd.NA)
            z_avg = num / den
            valid = z_avg.dropna()
            if len(valid) == 0:
                return None
            mn, mx = float(valid.min()), float(valid.max())
            if mx <= mn:
                out = z_avg * 0 + 50.0
            else:
                out = ((z_avg - mn) / (mx - mn) * 100.0)
            return pd.to_numeric(out, errors="coerce").clip(0.0, 100.0).round(2)
        num = comp_df.fillna(0.0).mul(w_series, axis=1).sum(axis=1)
        den = comp_df.notna().astype(float).mul(w_series, axis=1).sum(axis=1).replace(0, pd.NA)
        out = num / den
        return pd.to_numeric(out, errors="coerce").clip(0.0, 99.0).round(2)

    for dim_key, opt_map in construct_col_map.items():
        for opt, out_col in opt_map.items():
            gen = _construct_from_indicators(dim_key, opt)
            if gen is None:
                continue
            if out_col not in data.columns:
                data[out_col] = gen
            else:
                existing = pd.to_numeric(data[out_col], errors="coerce")
                data[out_col] = existing.where(existing.notna(), gen)

    selected_option = str(approved_score_option or DEFAULT_SCORE_COLUMN).strip()
    if selected_option not in _SCORE_OPTION_CHOICES:
        selected_option = DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in _SCORE_OPTION_CHOICES else "attractiveness_score_opt2"
    opt_suffix = selected_option.split("_")[-1] if "_" in selected_option else "opt2"
    if opt_suffix not in {"opt1", "opt2", "opt4"}:
        opt_suffix = "opt2"

    attr_series = _series_or_default(f"attractiveness_score_{opt_suffix}", default=float("nan"))
    win_series = _series_or_default(f"win_score_{opt_suffix}", default=float("nan"))
    ripe_series = _series_or_default(f"strength_score_{opt_suffix}", default=float("nan"))
    econ_series = _series_or_default(f"rightness_score_{opt_suffix}", default=float("nan"))

    data["attractiveness"] = pd.to_numeric(attr_series, errors="coerce").fillna(fallback).clip(0, 100)
    data["ability_to_win"] = pd.to_numeric(win_series, errors="coerce").fillna(fallback).clip(0, 100)
    data["ripeness"] = pd.to_numeric(ripe_series, errors="coerce").fillna(fallback).clip(0, 100)
    data["economic_significance"] = pd.to_numeric(econ_series, errors="coerce").fillna(fallback).clip(0, 100)

    tier1_base = (
        pd.concat(
            [
                data["attractiveness"],
                data["ability_to_win"],
                data["ripeness"],
                data["economic_significance"],
            ],
            axis=1,
        )
        .mean(axis=1)
        .fillna(fallback)
        .clip(0, 100)
    )
    tier_series = {
        "tier1": tier1_base,
        "tier2": _series_or_default("tier2_score", default=0.0).clip(0, 100),
        "tier3": _series_or_default("tier3_score", default=0.0).clip(0, 100),
    }
    for tier, _ in _TIER_META:
        data[tier] = tier_series[tier]

    tier_weights = {
        tier: max(0.0, float(approved_tier_weights.get(tier, _DEFAULT_TIER_WEIGHTS.get(tier, 0.0))))
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


def default_weight_state() -> dict:
    return {
        "approved_option_component_weights": default_option_component_weights(),
        "approved_construct_component_weights": default_construct_component_weights(),
        "approved_score_option": (
            DEFAULT_SCORE_COLUMN if DEFAULT_SCORE_COLUMN in _SCORE_OPTION_CHOICES else "attractiveness_score_opt2"
        ),
        "approved_tier_weights": dict(_DEFAULT_TIER_WEIGHTS),
        "approved_dim_weights": {dim: 25.0 for dim, _ in _DIMENSION_META},
    }
