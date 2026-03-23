"""
Config-driven hospital_potential for the ZIP choropleth.
Reads formulas from backend/configs/config.yml (hospital_potential section).
"""

from __future__ import annotations

import re
from typing import Any

import numpy as np
import pandas as pd


def to_snake(name: str) -> str:
    s = str(name).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def normalize_tier1_columns(df: pd.DataFrame) -> pd.DataFrame:
    out = df.copy()
    out.columns = [to_snake(c) for c in out.columns]
    return out


def _norm_zip5(s: object) -> str:
    x = str(s).strip()
    if not x or x.lower() in {"nan", "none"}:
        return ""
    if x.endswith(".0"):
        x = x[:-2]
    d = "".join(ch for ch in x if ch.isdigit())
    return d[:5].zfill(5) if d else ""


_STATE_MAP = {
    "al": "alabama",
    "fl": "florida",
    "ga": "georgia",
    "alabama": "alabama",
    "florida": "florida",
    "georgia": "georgia",
}


def prepare_tier1_for_merge(tier1: pd.DataFrame) -> pd.DataFrame:
    """Align Tier 1 parquet (snake_case) — mirrors frontend loader."""
    t = normalize_tier1_columns(tier1)
    if "zip_code" not in t.columns:
        if "zipcode" in t.columns:
            t["zip_code"] = t["zipcode"]
        elif "zip" in t.columns:
            t["zip_code"] = t["zip"]
        else:
            raise ValueError("Tier 1 parquet needs zip_code / zipcode / zip")
    if "state_name" not in t.columns:
        if "state" in t.columns:
            t["state_name"] = t["state"]
        elif "state_abbr" in t.columns:
            t["state_name"] = t["state_abbr"]
        else:
            t["state_name"] = ""
    t["zip_code"] = t["zip_code"].map(_norm_zip5)
    t["state_name"] = t["state_name"].fillna("").astype(str).str.strip()
    t["state_key"] = t["state_name"].str.lower().map(lambda s: _STATE_MAP.get(s, s.lower()))
    if "data_year" in t.columns:
        t["data_year"] = pd.to_numeric(t["data_year"], errors="coerce")
        t = t.sort_values("data_year", ascending=False)
    elif "historical_year" in t.columns:
        t["historical_year"] = pd.to_numeric(t["historical_year"], errors="coerce")
        t = t.sort_values("historical_year", ascending=False)
    dedupe = ["zip_code", "state_key"] if "state_name" in t.columns else ["zip_code"]
    t = t.drop_duplicates(subset=dedupe, keep="first")
    return t


def merge_tier1_onto_gdf(gdf: pd.DataFrame, tier1: pd.DataFrame) -> pd.DataFrame:
    """Left-merge Tier 1 onto polygon attributes (same rules as frontend loader)."""
    t = prepare_tier1_for_merge(tier1)
    out = gdf.copy()
    out["zipcode"] = out["zipcode"].map(_norm_zip5)
    out["state"] = out["state"].astype(str).str.strip()
    out["state_key"] = out["state"].str.lower().map(lambda s: _STATE_MAP.get(s, s.lower()))

    base_cols = [c for c in t.columns if c not in ("zip_code", "state_name", "state_key")]
    exact = None
    if "state_name" in t.columns:
        exact = out.merge(
            t,
            how="left",
            left_on=["zipcode", "state_key"],
            right_on=["zip_code", "state_key"],
            suffixes=("", "__t1_exact"),
        )
    zip_only = t.drop_duplicates(subset=["zip_code"], keep="first")
    merged = out.merge(
        zip_only,
        how="left",
        left_on="zipcode",
        right_on="zip_code",
        suffixes=("", "__t1_zip"),
    )
    for col in base_cols:
        zip_col = f"{col}__t1_zip"
        exact_col = f"{col}__t1_exact"
        if col not in merged.columns:
            merged[col] = pd.NA
        if exact is not None and exact_col in exact.columns:
            merged[col] = exact[exact_col].combine_first(merged[col])
        if zip_col in merged.columns:
            merged[col] = merged[col].combine_first(merged[zip_col])
            merged.drop(columns=[zip_col], inplace=True, errors="ignore")
    for c in ("zip_code", "zip_code__t1_zip", "state_key", "state_name"):
        merged.drop(columns=[c], inplace=True, errors="ignore")
    return merged


def _rescale_mask(vals: np.ndarray, mask: np.ndarray) -> np.ndarray:
    out = np.zeros_like(vals, dtype=float)
    sub = vals[mask]
    if sub.size == 0:
        return out
    mn, mx = np.nanmin(sub), np.nanmax(sub)
    if mx > mn:
        out[mask] = (vals[mask] - mn) / (mx - mn)
    else:
        out[mask] = 0.5
    out[np.isnan(out)] = 0.0
    return out


def compute_hospital_potential(merged: pd.DataFrame, hp_cfg: dict[str, Any]) -> pd.Series:
    """
    Returns 0-100 Series aligned to merged index.
    """
    n = len(merged)
    fb = float(hp_cfg.get("fallback", 50.0))
    direct_cols = hp_cfg.get("use_direct_columns")
    if not direct_cols:
        single = (hp_cfg.get("use_direct_column") or "").strip()
        direct_cols = [single] if single else []
    for direct in direct_cols:
        direct = str(direct).strip()
        if direct and direct in merged.columns:
            s = pd.to_numeric(merged[direct], errors="coerce").clip(0, 100)
            return s.fillna(fb)

    factors = hp_cfg.get("factors") or []
    if not factors:
        return pd.Series(fb, index=merged.index)

    # Rows with at least one factor present
    acc = np.zeros(n, dtype=float)
    wsum = np.zeros(n, dtype=float)
    for spec in factors:
        col = spec.get("column")
        if not col or col not in merged.columns:
            continue
        w = float(spec.get("weight", 1.0))
        inv = bool(spec.get("invert", False))
        v = pd.to_numeric(merged[col], errors="coerce").values.astype(float)
        mask = np.isfinite(v)
        if not mask.any():
            continue
        normed = _rescale_mask(v, mask)
        if inv:
            normed[mask] = 1.0 - normed[mask]
        acc += w * normed
        wsum += w * mask.astype(float)
    ok = wsum > 0
    out = np.full(n, fb, dtype=float)
    out[ok] = (acc[ok] / wsum[ok]) * 100.0
    return pd.Series(np.round(out, 1), index=merged.index)
