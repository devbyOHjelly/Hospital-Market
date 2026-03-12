"""
scoring.py
Tier-based entity scoring model (Tier 1 + Tier 2 + Tier 3) with
rubric 4-dimension scores (Strategic Fit, Platform Value, Feasibility,
Transaction Propensity).

Tier 1 = Census demographics at ZIP level (market attractiveness)
Tier 2 = Entity attributes + ZIP-level market supply/utilization from
         CMS Cost Reports, Medicare Geo Variation, SAHIE, ACS, NPPES taxonomy
Tier 3 = Service line data (placeholder — neutral 50 until POS/claims in v0.3)
"""

from __future__ import annotations
from pathlib import Path

import numpy as np
import pandas as pd
import yaml

# ── Defaults (overridden by scoring_rubric.yml when available) ───────────────

_DEFAULT_TIER_WEIGHTS = {
    "tier_1": 0.60,
    "tier_2": 0.30,
    "tier_3": 0.10,
}

_DEFAULT_RUBRIC_WEIGHTS = {
    "strategic_fit": 0.45,
    "platform_value": 0.20,
    "feasibility": 0.15,
    "transaction_propensity": 0.20,
}

TIER1_FACTORS = [
    "total_population",
    "population_growth_5yr_pct",
    "median_age",
    "median_household_income",
    "per_capita_income",
    "bachelors_or_higher_pct",
    "pct_65_plus",
    "birth_rate_per_1000",
    "in_migration_pct",
    "unemployment_rate",
]

TIER1_INVERT = {"unemployment_rate"}

OWNERSHIP_SCORES = {
    "voluntary non-profit - private":  1.0,
    "voluntary non-profit - church":   1.0,
    "voluntary non-profit - other":    1.0,
    "government - federal":            0.6,
    "government - state":              0.65,
    "government - local":              0.7,
    "government - hospital district":  0.7,
    "proprietary":                     0.5,
    "physician":                       0.4,
    "tribal":                          0.6,
}

HOSPITAL_TYPE_SCORES = {
    "acute care hospitals":              1.0,
    "acute care - department of defense": 0.9,
    "critical access hospitals":         0.8,
    "childrens":                         0.85,
    "psychiatric":                       0.6,
}


def _rescale(arr: np.ndarray) -> np.ndarray:
    """Min-max normalize to 0-1 (NaN-safe)."""
    mn, mx = np.nanmin(arr), np.nanmax(arr)
    if mx > mn:
        out = (arr - mn) / (mx - mn)
        return np.where(np.isnan(out), 0.0, out)
    return np.full_like(arr, 0.5, dtype=float)


def _load_rubric(cfg: dict) -> dict:
    """Load scoring_rubric.yml via the pipeline config."""
    rubric_path = cfg.get("processing", {}).get("scoring", {}).get("rubric_file", "")
    if not rubric_path:
        return {}
    full = Path(__file__).parent.parent / rubric_path
    if not full.exists():
        return {}
    with open(full, "r") as f:
        return yaml.safe_load(f) or {}


# ── Tier 1: ZIP-level market attractiveness ──────────────────────────────────

def _score_tier1(entities: pd.DataFrame, census_df: pd.DataFrame | None) -> np.ndarray:
    """
    Score each entity's ZIP on Tier 1 Census factors.
    Returns a 0-100 array aligned to the entities index.
    """
    n = len(entities)
    if census_df is None or census_df.empty:
        return np.full(n, 50.0)

    census = census_df.copy()
    census["zipcode"] = census["zipcode"].astype(str).str.zfill(5)
    ent_zip = entities["zip"].astype(str).str.zfill(5)

    available = [f for f in TIER1_FACTORS if f in census.columns]
    if not available:
        return np.full(n, 50.0)

    for col in available:
        census[col] = pd.to_numeric(census[col], errors="coerce")

    factor_scores = np.zeros((len(census), len(available)))
    for i, col in enumerate(available):
        vals = census[col].values.astype(float)
        normed = _rescale(vals)
        if col in TIER1_INVERT:
            normed = 1.0 - normed
        factor_scores[:, i] = normed

    census["_t1_score"] = _rescale(np.nanmean(factor_scores, axis=1)) * 100

    lookup = dict(zip(census["zipcode"], census["_t1_score"]))
    return ent_zip.map(lookup).fillna(50.0).values


# ── Tier 2 ZIP-level supply/utilization factors ──────────────────────────────

TIER2_ZIP_FACTORS = [
    "pcp_per_100k",
    "specialist_per_100k",
    "bed_utilization_rate",
    "operating_margin_pct",
    "ma_penetration",
    "er_visits_per_1k",
    "uninsured_rate",
    "medicaid_pct",
    "outpatient_visits_per_1k",
]
TIER2_ZIP_INVERT = {"uninsured_rate"}


# ── Tier 2: Entity-level + ZIP-level quality attributes ──────────────────────

def _score_tier2(entities: pd.DataFrame, tier2_df: pd.DataFrame | None = None) -> np.ndarray:
    """
    Score each entity on its own attributes (CMS/NPPES) blended with
    ZIP-level market supply/utilization metrics from tier2_demographics.
    Returns a 0-100 array aligned to the entities index.
    """
    n = len(entities)

    # --- Part A: Entity-level attributes (hospitals carry CMS fields) ---
    components_a = []
    weights_a = []

    if "hospital_rating" in entities.columns:
        rating = pd.to_numeric(entities["hospital_rating"], errors="coerce").fillna(0)
        components_a.append((rating.values / 5.0).clip(0, 1))
        weights_a.append(0.30)

    if "emergency_services" in entities.columns:
        es = entities["emergency_services"].fillna("").astype(str).str.lower().str.strip()
        components_a.append(es.map(lambda v: 1.0 if v in ("yes", "true", "1") else 0.0).values)
        weights_a.append(0.15)

    if "ownership" in entities.columns:
        own = entities["ownership"].fillna("").astype(str).str.lower().str.strip()
        components_a.append(own.map(lambda v: OWNERSHIP_SCORES.get(v, 0.5)).values)
        weights_a.append(0.20)

    if "hospital_type" in entities.columns:
        ht = entities["hospital_type"].fillna("").astype(str).str.lower().str.strip()
        components_a.append(ht.map(lambda v: HOSPITAL_TYPE_SCORES.get(v, 0.5)).values)
        weights_a.append(0.10)

    if "resolution_confidence" in entities.columns:
        conf = pd.to_numeric(entities["resolution_confidence"], errors="coerce").fillna(0.7)
        components_a.append(conf.values.clip(0, 1))
        weights_a.append(0.10)

    entity_score_a = np.full(n, 50.0)
    if components_a:
        wa = np.array(weights_a)
        wa /= wa.sum()
        stacked_a = np.column_stack(components_a)
        entity_score_a = (np.dot(stacked_a, wa) * 100).clip(0, 100)

    # --- Part B: ZIP-level supply / utilization metrics ---
    zip_score_b = np.full(n, 50.0)
    if tier2_df is not None and not tier2_df.empty:
        t2 = tier2_df.copy()
        t2["zip"] = t2["zip"].astype(str).str.zfill(5)
        ent_zip = entities["zip"].astype(str).str.zfill(5)

        available = [f for f in TIER2_ZIP_FACTORS if f in t2.columns]
        if available:
            for col in available:
                t2[col] = pd.to_numeric(t2[col], errors="coerce")

            factor_scores = np.zeros((len(t2), len(available)))
            for i, col in enumerate(available):
                vals = t2[col].values.astype(float)
                normed = _rescale(vals)
                if col in TIER2_ZIP_INVERT:
                    normed = 1.0 - normed
                factor_scores[:, i] = normed

            t2["_t2_zip_score"] = _rescale(np.nanmean(factor_scores, axis=1)) * 100
            lookup = dict(zip(t2["zip"], t2["_t2_zip_score"]))
            zip_score_b = ent_zip.map(lookup).fillna(50.0).values

    # Blend: 60% entity attributes, 40% ZIP-level market metrics
    has_entity_data = len(components_a) > 0
    has_zip_data = tier2_df is not None and not tier2_df.empty
    if has_entity_data and has_zip_data:
        return (0.6 * entity_score_a + 0.4 * zip_score_b).clip(0, 100)
    elif has_entity_data:
        return entity_score_a
    elif has_zip_data:
        return zip_score_b
    else:
        return np.full(n, 50.0)


# ── Main entry point ─────────────────────────────────────────────────────────

def score_entities(
    entities: pd.DataFrame,
    census_df: pd.DataFrame | None = None,
    tier2_df: pd.DataFrame | None = None,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """
    Score entities with the Tier 1+2+3 framework.

    Adds columns: tier1_score, tier2_score, tier3_score, entity_score.
    """
    rubric = _load_rubric(cfg or {})
    tw = rubric.get("tier_weights", _DEFAULT_TIER_WEIGHTS)
    w1 = tw.get("tier_1", 0.60)
    w2 = tw.get("tier_2", 0.30)
    w3 = tw.get("tier_3", 0.10)

    df = entities.copy()

    t1 = _score_tier1(df, census_df)
    t2 = _score_tier2(df, tier2_df)
    t3 = np.full(len(df), 50.0)  # placeholder until POS/claims data (v0.3)

    df["tier1_score"] = np.round(t1, 1)
    df["tier2_score"] = np.round(t2, 1)
    df["tier3_score"] = np.round(t3, 1)

    total_w = w1 + w2 + w3
    if total_w > 0:
        df["entity_score"] = np.round((w1 * t1 + w2 * t2 + w3 * t3) / total_w, 1)
    else:
        df["entity_score"] = np.round(t1, 1)

    return df


# ── Rubric 4-dimension scores (for scores.parquet) ──────────────────────────

def compute_rubric_scores(
    entities: pd.DataFrame,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """
    Produce the 4-dimension rubric scores using real entity data.
    Requires score_entities() to have been called first (tier1/2/3 columns).
    """
    rubric = _load_rubric(cfg or {})
    rw = rubric.get("weights", _DEFAULT_RUBRIC_WEIGHTS)
    w_fit = rw.get("strategic_fit", 0.45)
    w_plat = rw.get("platform_value", 0.20)
    w_feas = rw.get("feasibility", 0.15)
    w_prop = rw.get("transaction_propensity", 0.20)

    conf_rules = rubric.get("scoring_rules", {}).get("confidence_adjustment", {})
    conf_adjust = conf_rules.get("enabled", True)
    conf_floor = conf_rules.get("floor", 0.8)

    out = pd.DataFrame()
    out["entity_guid"] = entities["entity_guid"]

    out["strategic_fit_score"] = entities.get(
        "tier1_score", pd.Series(50.0, index=entities.index)
    ).values

    out["platform_value_score"] = entities.get(
        "tier2_score", pd.Series(50.0, index=entities.index)
    ).values

    conf = pd.to_numeric(
        entities.get("resolution_confidence", pd.Series(0.7, index=entities.index)),
        errors="coerce",
    ).fillna(0.7)
    out["feasibility_score"] = (conf * 100).clip(0, 100).values

    own_raw = np.full(len(entities), 0.5)
    if "ownership" in entities.columns:
        own_raw = (
            entities["ownership"]
            .fillna("")
            .astype(str)
            .str.lower()
            .str.strip()
            .map(lambda v: OWNERSHIP_SCORES.get(v, 0.5))
            .values
        )
    out["transaction_propensity_score"] = np.round(own_raw * 100, 1)

    out["overall_score"] = np.round(
        w_fit * out["strategic_fit_score"]
        + w_plat * out["platform_value_score"]
        + w_feas * out["feasibility_score"]
        + w_prop * out["transaction_propensity_score"],
        1,
    )

    if conf_adjust:
        adj = conf.values.clip(conf_floor, 1.0)
        out["overall_score"] = np.round(out["overall_score"] * adj, 1)

    dim_cols = [
        "strategic_fit_score",
        "platform_value_score",
        "feasibility_score",
        "transaction_propensity_score",
    ]
    dim_names = ["strategic_fit", "platform_value", "feasibility", "transaction_propensity"]
    scores_matrix = out[dim_cols].values
    top_indices = np.argmax(scores_matrix, axis=1)
    out["drivers"] = [f"top={dim_names[i]}" for i in top_indices]

    return out