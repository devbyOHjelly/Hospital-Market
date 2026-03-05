"""Ranking helpers for the leaderboard."""

from __future__ import annotations

import pandas as pd


def prioritize_selected_rows(
    ranked: pd.DataFrame,
    selected_zips: set[str],
    threshold: int = 5,
) -> pd.DataFrame:
    """
    Move selected ZIP rows to the top when selection reaches threshold.

    Preserves descending hospital_potential ordering within each block.
    """
    if len(selected_zips) < threshold or ranked.empty:
        return ranked

    out = ranked.copy()
    out["_selected_top"] = out["zip_key"].isin(selected_zips).astype(int)
    out = out.sort_values(
        ["_selected_top", "hospital_potential"],
        ascending=[False, False],
        kind="mergesort",
    ).drop(columns=["_selected_top"])
    return out
