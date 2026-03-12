from __future__ import annotations

import re
from typing import Any

import pandas as pd
from .agent_config import (
    DEFAULT_SCORE_COLUMN,
    DEFAULT_SCORE_OPTION,
    EXECUTIVE_FOLLOWUPS,
    OPTION_ALIASES,
    SCORE_DEFINITIONS,
    WHATIF_KEYWORDS,
)


def _normalize_zip(z: Any) -> str:
    s = str(z or "").strip()
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits.zfill(5) if digits else s


def _render_structured_response(
    headline: str,
    bullets: list[str],
    implication: str,
    followups: list[str] | None = None,
) -> str:
    bullet_lines = "\n".join(f"- {b}" for b in bullets[:5] if b)
    followup_lines = "\n".join(
        f"{i + 1}. {q}" for i, q in enumerate((followups or list(EXECUTIVE_FOLLOWUPS))[:3])
    )
    return (
        f"FINAL ANSWER: **HEADLINE: {headline}**\n\n"
        f"SUPPORTING BULLETS:\n"
        f"{bullet_lines}\n\n"
        f"**STRATEGIC IMPLICATION: {implication}**\n\n"
        f"SUGGESTED FOLLOW-UP QUESTIONS:\n"
        f"{followup_lines}"
    )


def _extract_score_column(q: str) -> str:
    ql = (q or "").lower()
    for alias, col in OPTION_ALIASES.items():
        if alias in ql:
            return col
    return DEFAULT_SCORE_COLUMN


def _explicit_option_requested(q: str) -> bool:
    ql = (q or "").lower()
    return any(alias in ql for alias in OPTION_ALIASES.keys())


def _canonicalize_question(q: str) -> str:
    ql = (q or "").lower()
    # Notebook/user typo variants.
    ql = ql.replace("attractiness", "attractiveness")
    ql = ql.replace("attractivness", "attractiveness")
    ql = ql.replace("stage of", "state of")
    ql = ql.replace("avreage", "average")
    return ql


def _extract_option_label(score_col: str) -> str:
    if score_col == "attractiveness_score_opt1":
        return "Option 1"
    if score_col == "attractiveness_score_opt2":
        return "Option 2"
    if score_col == "attractiveness_score_opt4":
        return "Option 4"
    return DEFAULT_SCORE_OPTION.title()


def _compute_weighted_score(df: pd.DataFrame, score_col: str) -> pd.Series | None:
    score_def = SCORE_DEFINITIONS.get(score_col) or {}
    comps = (score_def.get("components") or {})
    if not comps:
        return None
    if not all(col in df.columns for col in comps.keys()):
        return None
    weighted = None
    for col, meta in comps.items():
        w = float(meta.get("weight", 0.0))
        s = pd.to_numeric(df[col], errors="coerce").fillna(0.0) * w
        weighted = s if weighted is None else (weighted + s)
    if weighted is None:
        return None
    return pd.to_numeric(weighted, errors="coerce").fillna(0.0).round(2)


def _ensure_score_columns(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or len(df) == 0:
        return df
    out = df.copy()
    for score_col in SCORE_DEFINITIONS.keys():
        if score_col in out.columns:
            continue
        computed = _compute_weighted_score(out, score_col)
        if computed is not None:
            out[score_col] = computed
    return out


def _state_from_question(q: str) -> str | None:
    for s in ("alabama", "florida", "georgia"):
        if s in q:
            return s.title()
    return None


def _msa_weighted_scores(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    if "msa_name" not in df.columns:
        return pd.DataFrame()
    w = df.copy()
    w[score_col] = pd.to_numeric(w[score_col], errors="coerce")
    if "total_population" in w.columns:
        w["__w"] = pd.to_numeric(w["total_population"], errors="coerce").fillna(0)
    else:
        w["__w"] = 0.0
    w = w[w[score_col].notna()].copy()
    if len(w) == 0:
        return pd.DataFrame()

    def _agg(g: pd.DataFrame) -> pd.Series:
        wg = pd.to_numeric(g["__w"], errors="coerce").fillna(0)
        sg = pd.to_numeric(g[score_col], errors="coerce").fillna(0)
        if float(wg.sum()) > 0:
            v = float((sg * wg).sum() / wg.sum())
        else:
            v = float(sg.mean())
        states = g["state"].dropna().astype(str) if "state" in g.columns else pd.Series(dtype=str)
        st = states.mode().iloc[0] if len(states) else ""
        return pd.Series({score_col: v, "state": st})

    out = w.groupby("msa_name", dropna=True).apply(_agg).reset_index()
    return out


def _msa_mean_scores(df: pd.DataFrame, score_col: str) -> pd.DataFrame:
    if "msa_name" not in df.columns:
        return pd.DataFrame()
    w = df.copy()
    w[score_col] = pd.to_numeric(w[score_col], errors="coerce")
    w = w[w[score_col].notna()].copy()
    if len(w) == 0:
        return pd.DataFrame()
    if "state" in w.columns:
        out = (
            w.groupby(["msa_name", "state"], dropna=True)[score_col]
            .mean()
            .reset_index()
        )
    else:
        out = (
            w.groupby(["msa_name"], dropna=True)[score_col]
            .mean()
            .reset_index()
        )
        out["state"] = ""
    return out


def _prefers_mean_average(q: str) -> bool:
    ql = (q or "").lower()
    return ("on average" in ql) or ("average attractiveness" in ql) or ("avg attractiveness" in ql)


def _resolve_msa_name(grouped: pd.DataFrame, raw_name: str) -> str | None:
    if len(grouped) == 0:
        return None
    target = (raw_name or "").strip().lower()
    if not target:
        return None
    names = grouped["msa_name"].astype(str)
    exact = grouped[names.str.lower() == target]
    if len(exact):
        return str(exact.iloc[0]["msa_name"])
    contains = grouped[names.str.lower().str.contains(re.escape(target), na=False)]
    if len(contains):
        return str(contains.iloc[0]["msa_name"])
    return None


def _ranked_msa_lines(grouped: pd.DataFrame, score_col: str, limit: int = 14) -> list[str]:
    ranked = grouped.sort_values(score_col, ascending=False).head(limit)
    out: list[str] = []
    for _, row in ranked.iterrows():
        out.append(f"{str(row['msa_name'])}: {float(row[score_col]):.2f}")
    return out


def _score_column_for_question(df: pd.DataFrame, q: str) -> str:
    col = _extract_score_column(q)
    # If user explicitly asks for an option, do not silently downgrade to hospital_potential.
    if _explicit_option_requested(q):
        return col
    if col in df.columns:
        return col
    if "hospital_potential" in df.columns:
        return "hospital_potential"
    return col


def _handle_top_msa_average_by_option(df: pd.DataFrame, q_raw: str, q: str) -> str | None:
    if "msa" not in q or "average" not in q:
        return None
    if not any(k in q for k in ("highest", "best", "top")):
        return None
    if not any(k in q for k in ("attractiveness", "option", "opt")):
        return None
    if "msa_name" not in df.columns:
        return None

    score_col = _score_column_for_question(df, q)
    if score_col not in df.columns:
        return (
            f"I could not find `{score_col}` in the current dataset context. "
            "Option-specific ranking needs the Option score column or its component percentile columns."
        )
    grouped = _msa_mean_scores(df, score_col)
    st = _state_from_question(q)
    if st and "state" in grouped.columns:
        grouped = grouped[grouped["state"].astype(str).str.lower() == st.lower()].copy()
    if len(grouped) == 0:
        return None
    grouped = grouped.sort_values(score_col, ascending=False)
    top = grouped.iloc[0]
    option_label = _extract_option_label(score_col)
    ranked_lines = _ranked_msa_lines(grouped, score_col, limit=20)
    return _render_structured_response(
        headline=(
            f"Under {option_label}, {str(top['msa_name'])} has the highest on-average "
            f"attractiveness score{(' in ' + st) if st else ''} at {float(top[score_col]):.2f}."
        ),
        bullets=[
            f"Score column used: {score_col}.",
            "Aggregation method: simple mean across ZIP rows per MSA (not population-weighted).",
            f"Scope: {st if st else 'all states in dashboard dataset'}.",
            "MSA ranking: " + " | ".join(ranked_lines),
        ],
        implication="This MSA should move to active diligence under the selected option methodology.",
    )


def _handle_methodology_questions(q: str) -> str | None:
    asks_formula = any(
        k in q for k in (
            "formula",
            "construct",
            "factors",
            "how is it calculated",
            "how are they calculated",
            "methodology",
            "how does scoring work",
        )
    )
    asks_avg = any(k in q for k in ("averaging", "weighted average", "unweighted average"))
    asks_sweet_spot = "sweet spot" in q or ("median age" in q and "average" in q)
    if not (asks_formula or asks_avg or asks_sweet_spot):
        return None
    return _render_structured_response(
        headline="The agent evaluates markets with Option 1, Option 2, and Option 4 scoring; default is Option 2 unless you request another option.",
        bullets=[
            "Option 1 is an equal-weight 5-factor attractiveness score.",
            "Option 2 is the expert-weight score: Total Population 50%, Age 65+ 20%, Population Growth 15%, Age 45-64 10%, Birth Rate 5%.",
            "Option 4 is equal-weight percentile-rank scoring across the same 5 factors.",
            "MSA-level aggregation uses population-weighted averaging when total population is available.",
            "Sweet-spot variables can require non-linear transforms; plain means can hide those effects.",
        ],
        implication="Decision quality improves when you explicitly specify Option 1, Option 2, or Option 4 for every comparison.",
    )


def _handle_surface_query(df: pd.DataFrame, q_raw: str, q: str) -> str | None:
    if len(df) == 0:
        return "No data is available to answer this question right now."
    df = _ensure_score_columns(df)
    st = _state_from_question(q)
    scoped = df
    if st and "state" in df.columns:
        scoped = df[df["state"].astype(str).str.lower() == st.lower()].copy()
        if len(scoped) == 0:
            return f"No rows are available for {st} in the dashboard data."

    if "msa" in q and any(k in q for k in ("best", "highest", "top")) and any(
        k in q for k in ("attractiveness", "market score", "market potential", "hospital potential")
    ):
        score_col = _score_column_for_question(df, q)
        grouped = _msa_mean_scores(df, score_col) if _prefers_mean_average(q) else _msa_weighted_scores(df, score_col)
        st = _state_from_question(q)
        if st and "state" in grouped.columns:
            grouped = grouped[grouped["state"].astype(str).str.lower() == st.lower()].copy()
        if len(grouped) == 0:
            return None
        grouped = grouped.sort_values(score_col, ascending=False)
        top = grouped.iloc[0]
        option_label = _extract_option_label(score_col)
        ranked_lines = _ranked_msa_lines(grouped, score_col, limit=14)
        return _render_structured_response(
            headline=(
                f"Under {option_label}, {str(top['msa_name'])} has the highest population-weighted "
                f"average attractiveness{(' in ' + st) if st else ''} at {float(top[score_col]):.2f}."
            ),
            bullets=[
                f"Score column used: {score_col}.",
                f"Aggregation method: {'simple mean' if _prefers_mean_average(q) else 'population-weighted average'}.",
                f"Scope: {st if st else 'all states in dashboard dataset'}.",
                "All ranked MSAs (top shown): " + " | ".join(ranked_lines),
            ],
            implication="This market is the first candidate for deeper diligence, competitor mapping, and service-line fit validation.",
        )

    # ZIP-level best market score / potential.
    if any(k in q for k in ("best", "highest", "top")) and (
        ("market score" in q) or ("market potential" in q) or ("hospital potential" in q)
    ) and ("zip" in q):
        if "hospital_potential" not in scoped.columns:
            return None
        s = pd.to_numeric(scoped["hospital_potential"], errors="coerce")
        if not s.notna().any():
            return None
        idx = s.idxmax()
        z = _normalize_zip(scoped.loc[idx, "zipcode"]) if "zipcode" in scoped.columns else "N/A"
        st_name = str(scoped.loc[idx, "state"]) if "state" in scoped.columns else ""
        return _render_structured_response(
            headline=f"ZIP {z}{(' (' + st_name + ')') if st_name else ''} has the highest market score at {float(s.loc[idx]):.2f}.",
            bullets=[
                "Metric used: hospital_potential.",
                f"Scope: {st if st else 'all states in dashboard dataset'}.",
                "Result is computed directly from the loaded dataset, not inferred.",
            ],
            implication="This ZIP should be prioritized for service-demand validation and local competitor pressure analysis.",
        )

    # ZIP-level highest 65+ signal.
    if any(k in q for k in ("highest", "best", "top")) and ("zip" in q) and (
        ("65+" in q) or ("65 plus" in q) or ("age 65" in q) or ("65-year" in q) or ("seniors" in q)
    ):
        metric = None
        metric_label = ""
        for col, label in (
            ("age_65_plus", "age_65_plus"),
            ("pct_65_plus", "pct_65_plus"),
            ("age_65_plus_pct", "age_65_plus_pct"),
        ):
            if col in scoped.columns:
                metric = col
                metric_label = label
                break
        if metric is None:
            return "No 65+ metric is available in the current dataset context."
        s = pd.to_numeric(scoped[metric], errors="coerce")
        if not s.notna().any():
            return "65+ metric values are unavailable in the current dataset context."
        idx = s.idxmax()
        z = _normalize_zip(scoped.loc[idx, "zipcode"]) if "zipcode" in scoped.columns else "N/A"
        st_name = str(scoped.loc[idx, "state"]) if "state" in scoped.columns else ""
        return f"ZIP {z}{(' (' + st_name + ')') if st_name else ''} is highest on {metric_label} at {float(s.loc[idx]):.2f}."

    # 1) Highest population growth rate ZIP.
    if "highest" in q and "population growth rate" in q:
        col = "population_growth_rate_2yr" if "population_growth_rate_2yr" in df.columns else None
        if col is None:
            return None
        s = pd.to_numeric(scoped[col], errors="coerce")
        if not s.notna().any():
            return "Population growth rate data is unavailable."
        idx = s.idxmax()
        z = _normalize_zip(scoped.loc[idx, "zipcode"]) if "zipcode" in scoped.columns else "N/A"
        v = float(s.loc[idx])
        return _render_structured_response(
            headline=f"ZIP {z} has the highest two-year population growth rate at {v:.2f}%.",
            bullets=[
                "This value is materially above most markets and should be validated against baseline population size.",
                "Outlier growth can be true demand expansion, new development, or a base-size artifact.",
                "The result comes directly from the population_growth_rate_2yr field in the dataset.",
            ],
            implication="If this growth is sustained and real, this ZIP is a strong candidate for near-term market-entry analysis.",
        )

    # 2) Highest attractiveness score (option X), commonly zip or msa in notebook tests.
    if any(k in q for k in ("highest", "best", "top")) and "attractiveness" in q:
        score_col = _score_column_for_question(df, q)
        s = pd.to_numeric(df.get(score_col), errors="coerce")
        if not s.notna().any():
            return None
        s = pd.to_numeric(scoped.get(score_col), errors="coerce")
        if len(scoped) == 0 or not s.notna().any():
            return None

        # MSA question.
        if "msa" in q and "average" in q and "msa_name" in scoped.columns:
            grouped = _msa_mean_scores(scoped, score_col) if _prefers_mean_average(q) else _msa_weighted_scores(scoped, score_col)
            if st and "state" in grouped.columns:
                grouped = grouped[grouped["state"].astype(str).str.lower() == st.lower()].copy()
            if len(grouped) == 0:
                return None
            grouped = grouped.sort_values(score_col, ascending=False)
            top = grouped.iloc[0]
            top_name = str(top["msa_name"])
            top_val = float(top[score_col])
            option_label = _extract_option_label(score_col)
            return _render_structured_response(
                headline=f"Under {option_label}, {top_name} has the highest average attractiveness score at {top_val:.2f}.",
                bullets=[
                    f"Score column used: {score_col}.",
                    f"Aggregation method: {'simple mean' if _prefers_mean_average(q) else 'population-weighted average'} at the MSA level.",
                    f"Scope: {st if st else 'all states in dashboard dataset'}.",
                ],
                implication="This MSA should be treated as the lead expansion candidate under the selected scoring option.",
            )

        # ZIP question default.
        idx = s.idxmax()
        z = _normalize_zip(scoped.loc[idx, "zipcode"]) if "zipcode" in scoped.columns else "N/A"
        st_name = str(scoped.loc[idx, "state"]) if "state" in scoped.columns else ""
        st_txt = f" ({st_name})" if st_name else ""
        option_label = _extract_option_label(score_col)
        return _render_structured_response(
            headline=f"Under {option_label}, ZIP {z}{st_txt} has the highest attractiveness score at {float(s.loc[idx]):.2f}.",
            bullets=[
                f"Score column used: {score_col}.",
                "Scoring is computed from the configured option definitions and percentile components.",
                f"Scope: {st if st else 'all states in dashboard dataset'}.",
            ],
            implication="This ZIP is the top-ranked target under the requested evaluation method.",
        )

    # 3) Average attractiveness for a named MSA.
    if "average attractiveness" in q and "msa" in q and "for" in q and "msa_name" in df.columns:
        score_col = _score_column_for_question(df, q)
        m = re.search(r"for\s+(.+?)\s+msa", q_raw, flags=re.IGNORECASE)
        if not m:
            return None
        target = m.group(1).strip().lower()
        grouped = _msa_mean_scores(df, score_col) if _prefers_mean_average(q) else _msa_weighted_scores(df, score_col)
        match = _resolve_msa_name(grouped, target)
        if not match:
            return f"I could not find an MSA matching '{target}'."
        row = grouped[grouped["msa_name"] == match].iloc[0]
        option_label = _extract_option_label(score_col)
        return _render_structured_response(
            headline=f"Under {option_label}, {row['msa_name']} has an average attractiveness score of {float(row[score_col]):.2f}.",
            bullets=[
                f"Score column used: {score_col}.",
                    f"Aggregation method: {'simple mean' if _prefers_mean_average(q) else 'population-weighted'} MSA average.",
                "This value is directly computed from the loaded dataset rows for that MSA.",
            ],
            implication="Use this as a baseline for side-by-side comparisons against peer MSAs before prioritization decisions.",
        )

    if ("best msa" in q or ("highest" in q and "msa" in q)) and "msa_name" in df.columns:
        score_col = _score_column_for_question(df, q)
        grouped = _msa_weighted_scores(df, score_col)
        st = _state_from_question(q)
        if st and "state" in grouped.columns:
            grouped = grouped[grouped["state"].astype(str).str.lower() == st.lower()].copy()
        if len(grouped) == 0:
            return None
        grouped = grouped.sort_values(score_col, ascending=False)
        top = grouped.iloc[0]
        option_label = _extract_option_label(score_col)
        return _render_structured_response(
            headline=f"Under {option_label}, {top['msa_name']} is the highest-scoring MSA{(' in ' + st) if st else ''} at {float(top[score_col]):.2f}.",
            bullets=[
                f"Score column used: {score_col}.",
                "Aggregation method: population-weighted average.",
                f"Scope: {st if st else 'all states in dashboard dataset'}.",
            ],
            implication="This is the top market to pressure-test with demand, access, and competitor analyses.",
        )

    return None


def _handle_comparison(df: pd.DataFrame, q: str) -> str | None:
    if not any(k in q for k in ("compare", " vs ", " versus ", "difference")):
        return None

    # MSA comparison first.
    if "msa" in q and "msa_name" in df.columns:
        score_col = _score_column_for_question(df, q)
        grouped = _msa_weighted_scores(df, score_col)
        if len(grouped) == 0:
            return None
        m_vs = re.search(r"(.+?)\s+(?:vs|versus)\s+(.+)", q, flags=re.IGNORECASE)
        m_cmp = re.search(r"compare\s+(.+?)\s+and\s+(.+)", q, flags=re.IGNORECASE)
        if m_vs:
            raw_a, raw_b = m_vs.group(1), m_vs.group(2)
        elif m_cmp:
            raw_a, raw_b = m_cmp.group(1), m_cmp.group(2)
        else:
            raw_a = raw_b = ""
        a_name = _resolve_msa_name(grouped, raw_a)
        b_name = _resolve_msa_name(grouped, raw_b)
        if a_name and b_name:
            a_val = float(grouped[grouped["msa_name"] == a_name][score_col].iloc[0])
            b_val = float(grouped[grouped["msa_name"] == b_name][score_col].iloc[0])
            better = a_name if a_val >= b_val else b_name
            diff = abs(a_val - b_val)
            return _render_structured_response(
                headline=f"{better} scores higher by {diff:.2f} points on {score_col}.",
                bullets=[
                    f"{a_name}: {a_val:.2f}",
                    f"{b_name}: {b_val:.2f}",
                    "Comparison method: population-weighted MSA average.",
                ],
                implication="The higher-scoring market is the better short-list candidate under the selected scoring option.",
            )

    if "zipcode" not in df.columns and "zip" not in q:
        return None

    zips = re.findall(r"\b\d{5}\b", q)
    if len(zips) < 2:
        return None
    z1, z2 = _normalize_zip(zips[0]), _normalize_zip(zips[1])
    if "zipcode" not in df.columns or "hospital_potential" not in df.columns:
        return None
    w = df.copy()
    w["zip_key"] = w["zipcode"].map(_normalize_zip)
    rows = w[w["zip_key"].isin([z1, z2])]
    if len(rows) < 2:
        return None
    a = float(pd.to_numeric(rows[rows["zip_key"] == z1]["hospital_potential"], errors="coerce").mean())
    b = float(pd.to_numeric(rows[rows["zip_key"] == z2]["hospital_potential"], errors="coerce").mean())
    better = z1 if a >= b else z2
    diff = abs(a - b)
    return _render_structured_response(
        headline=f"ZIP {better} has the higher market score by {diff:.2f} points.",
        bullets=[
            f"ZIP {z1}: {a:.2f}",
            f"ZIP {z2}: {b:.2f}",
            "Metric used: hospital_potential.",
        ],
        implication="The higher-scoring ZIP is the stronger immediate target for local growth planning.",
    )


def _handle_explanation(df: pd.DataFrame, q: str) -> str | None:
    if not any(k in q for k in ("why", "what makes", "explain", "reason", "factor", "drive", "cause")):
        return None
    if "highest attractiveness" in q or "highest" in q:
        score_col = _score_column_for_question(df, q)
        s = pd.to_numeric(df.get(score_col), errors="coerce")
        if not s.notna().any():
            return None
        idx = s.idxmax()
        z = _normalize_zip(df.loc[idx, "zipcode"]) if "zipcode" in df.columns else "N/A"
        signals = []
        for c in ("population_growth_rate_2yr", "median_household_income", "bachelors_or_higher_pct"):
            if c in df.columns:
                v = pd.to_numeric(df.loc[idx, c], errors="coerce")
                if pd.notna(v):
                    signals.append(f"{c}={float(v):.2f}")
        components = SCORE_DEFINITIONS.get(score_col, {}).get("components", {})
        weight_text = ", ".join(
            f"{meta.get('label', col)} {float(meta.get('weight', 0.0)) * 100:.0f}%"
            for col, meta in components.items()
        )
        extra = "; ".join(signals[:3]) if signals else "multiple favorable Tier 1 factors"
        return _render_structured_response(
            headline=f"ZIP {z} leads because it scores strongest on the weighted factors used by {score_col}.",
            bullets=[
                f"Key observed signals: {extra}.",
                f"Configured factor weights: {weight_text}.",
                "Higher-ranked component percentiles compound into a higher composite attractiveness score.",
            ],
            implication="The winning ZIP should be validated with competitive intensity and access constraints before final prioritization.",
        )
    return None


def try_handle_query(df: pd.DataFrame, user_question: str) -> str | None:
    q_raw = (user_question or "").strip()
    q = _canonicalize_question(q_raw)
    if not q_raw or df is None or len(df) == 0:
        return None
    df = _ensure_score_columns(df)

    if any(k in q for k in WHATIF_KEYWORDS):
        # Keep routing explicit: if "what-if" is asked, the model path can synthesize narrative.
        # The deterministic router still ensures all option scores are present in context.
        _ = _ensure_score_columns(df)
        return None

    method_reply = _handle_methodology_questions(q)
    if method_reply:
        return method_reply

    top_msa_avg_reply = _handle_top_msa_average_by_option(df, q_raw, q)
    if top_msa_avg_reply:
        return top_msa_avg_reply

    # Notebook-like routing order: explanation/comparison/surface.
    for handler in (_handle_explanation, _handle_comparison):
        out = handler(df, q)
        if out:
            return out
    return _handle_surface_query(df, q_raw, q)
