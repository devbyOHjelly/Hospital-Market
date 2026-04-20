"""Agent tab: deterministic replies, router, and LLM (orchestration for Dash)."""

from __future__ import annotations

import re

import pandas as pd

from backend.agent import query_agent, try_handle_query
from backend.agent.agent_config import DEFAULT_SCORE_COLUMN
from frontend.modules.dashboard.utils import normalize_zip
from frontend.modules.scoring_core import DEFAULT_TIER_WEIGHTS, TIER_META

# --- Deterministic shortcuts (orchestrated by `run_agent_turn` in the Dash app) ---


def _state_in_query(q: str) -> str | None:
    ql = (q or "").lower()
    if "florida" in ql or re.search(r"\bfl\b", ql):
        return "Florida"
    if "alabama" in ql or re.search(r"\bal\b", ql):
        return "Alabama"
    if "georgia" in ql or re.search(r"\bga\b", ql):
        return "Georgia"
    return None


def _deterministic_agent_reply(
    user_text: str,
    zip_records: list[dict],
    top_population: dict | None,
    all_rows: pd.DataFrame,
    current_option: str,
) -> str | None:
    q = (user_text or "").strip().lower()
    if not q:
        return None
    requested_opt = None
    if ("option 1" in q) or ("opt1" in q):
        requested_opt = "opt1"
    elif ("option 2" in q) or ("opt2" in q):
        requested_opt = "opt2"
    elif ("option 4" in q) or ("opt4" in q):
        requested_opt = "opt4"

    asks_construct_scores = any(
        k in q
        for k in (
            "attractiveness",
            "ability to win",
            "ability-to-win",
            "ripeness",
            "economic significance",
            "construct score",
            "construct scores",
            "four construct",
            "four scores",
        )
    )
    asks_market_potential = any(k in q for k in ("market potential", "hospital potential", "market score"))
    asks_best = any(k in q for k in ("highest", "best", "top", "stronger", "look into"))
    asks_population = "population" in q
    asks_highest = any(k in q for k in ("highest", "largest", "max", "most"))
    asks_population_growth = ("population growth" in q) or ("growth rate" in q)
    asks_selected = ("selected" in q) or ("these zip" in q) or ("those zip" in q) or ("of the zip" in q)
    asks_top_ranked_zip = (
        ("zip" in q)
        and any(k in q for k in ("highest", "top", "best"))
        and any(k in q for k in ("rank", "ranking", "overall", "market score", "market"))
    )

    def _resolved_opt() -> str:
        opt = requested_opt or str(current_option or "").strip().lower()
        if "_opt" in opt:
            opt = opt.split("_")[-1]
        return opt if opt in {"opt1", "opt2", "opt4"} else "opt2"

    if asks_top_ranked_zip and "zipcode" in all_rows.columns and len(all_rows) > 0:
        scoped = all_rows.copy()
        asked_state = _state_in_query(q)
        if asked_state and "state" in scoped.columns:
            scoped = scoped[scoped["state"].astype(str).str.lower() == asked_state.lower()].copy()
        if len(scoped) == 0:
            return f"No rows are available for {asked_state} in the dashboard data."

        scoped["zip_key"] = scoped["zipcode"].map(normalize_zip)
        scoped["__score"] = pd.to_numeric(scoped.get("hospital_potential"), errors="coerce")
        zip_rank = (
            scoped.groupby("zip_key", dropna=True)["__score"].mean().dropna().sort_values(ascending=False)
        )
        if len(zip_rank) == 0:
            return "No ranked ZIP scores are available for this scope."

        top_zip = str(zip_rank.index[0])
        top_score = float(zip_rank.iloc[0])
        top_rows = scoped[scoped["zip_key"] == top_zip].copy()
        top_idx = pd.to_numeric(top_rows["__score"], errors="coerce").idxmax()
        row = top_rows.loc[top_idx]
        st_name = str(row.get("state", "")).strip()

        opt = _resolved_opt()
        col_map = {
            "opt1": {
                "attr": "attractiveness_score_opt1",
                "win": "win_score_opt1",
                "ripe": "strength_score_opt1",
                "econ": "rightness_score_opt1",
            },
            "opt2": {
                "attr": "attractiveness_score_opt2",
                "win": "win_score_opt2",
                "ripe": "strength_score_opt2",
                "econ": "rightness_score_opt2",
            },
            "opt4": {
                "attr": "attractiveness_score_opt4",
                "win": "win_score_opt4",
                "ripe": "strength_score_opt4",
                "econ": "rightness_score_opt4",
            },
        }[opt]

        def _as_num(v):
            n = pd.to_numeric(pd.Series([v]), errors="coerce").iloc[0]
            return None if pd.isna(n) else float(n)

        av0 = _as_num(row.get("attractiveness"))
        wv0 = _as_num(row.get("ability_to_win"))
        rv0 = _as_num(row.get("ripeness"))
        ev0 = _as_num(row.get("economic_significance"))
        av = av0 if av0 is not None else _as_num(row.get(col_map["attr"]))
        wv = wv0 if wv0 is not None else _as_num(row.get(col_map["win"]))
        rv = rv0 if rv0 is not None else _as_num(row.get(col_map["ripe"]))
        ev = ev0 if ev0 is not None else _as_num(row.get(col_map["econ"]))

        w = pd.to_numeric(scoped.get("total_population"), errors="coerce").fillna(0.0).clip(lower=0.0)
        m = pd.to_numeric(scoped["__score"], errors="coerce")
        valid = m.notna()
        if valid.any() and float(w[valid].sum()) > 0:
            avg_market = float((m[valid] * w[valid]).sum() / w[valid].sum())
        elif valid.any():
            avg_market = float(m[valid].mean())
        else:
            avg_market = float("nan")

        def _fmt_v(v):
            try:
                fv = float(v)
                if fv != fv:
                    return "N/A"
                return f"{fv:.2f}"
            except Exception:
                return "N/A"

        return (
            f"Highest ranked ZIP {('in ' + asked_state + ' ') if asked_state else ''}is "
            f"{top_zip}{(' (' + st_name + ')') if st_name else ''} with ZIP score {_fmt_v(top_score)}. "
            f"Construct scores: Attractiveness {_fmt_v(av)}, Ability to Win {_fmt_v(wv)}, "
            f"Ripeness {_fmt_v(rv)}, Economic Significance {_fmt_v(ev)}. "
            f"Tier scores: Tier 1 {_fmt_v(row.get('tier1'))}, Tier 2 {_fmt_v(row.get('tier2'))}, Tier 3 {_fmt_v(row.get('tier3'))}. "
            f"{('State' if asked_state else 'Dataset')} average market score: {_fmt_v(avg_market)}."
        )

    asks_ranking_explain = (
        ("rank" in q or "ranking" in q)
        and any(k in q for k in ("highest", "top", "best"))
        and any(k in q for k in ("why", "explain", "reason"))
    )

    if asks_ranking_explain and "zipcode" in all_rows.columns and len(all_rows) > 0:
        opt = requested_opt or str(current_option or "").strip().lower()
        if "_opt" in opt:
            opt = opt.split("_")[-1]
        if opt not in {"opt1", "opt2", "opt4"}:
            opt = "opt2"
        option_label = {"opt1": "Option 1", "opt2": "Option 2", "opt4": "Option 4"}[opt]
        col_map = {
            "opt1": {
                "attr": "attractiveness_score_opt1",
                "win": "win_score_opt1",
                "ripe": "strength_score_opt1",
                "econ": "rightness_score_opt1",
            },
            "opt2": {
                "attr": "attractiveness_score_opt2",
                "win": "win_score_opt2",
                "ripe": "strength_score_opt2",
                "econ": "rightness_score_opt2",
            },
            "opt4": {
                "attr": "attractiveness_score_opt4",
                "win": "win_score_opt4",
                "ripe": "strength_score_opt4",
                "econ": "rightness_score_opt4",
            },
        }[opt]
        scoped = all_rows.copy()
        asked_state = _state_in_query(q)
        if asked_state and "state" in scoped.columns:
            scoped = scoped[scoped["state"].astype(str).str.lower() == asked_state.lower()].copy()
        if len(scoped) == 0:
            return f"No rows are available for {asked_state} in the dashboard data."

        scoped["zip_key"] = scoped["zipcode"].map(normalize_zip)
        for key, col in col_map.items():
            scoped[f"__{key}"] = pd.to_numeric(scoped.get(col), errors="coerce")
        scoped["__market"] = scoped[[f"__{k}" for k in ("attr", "win", "ripe", "econ")]].mean(axis=1)
        zip_rank = (
            scoped.groupby("zip_key", dropna=True)["__market"].mean().dropna().sort_values(ascending=False)
        )
        if len(zip_rank) == 0:
            return "No rankable ZIP scores are available for this scope."
        top_zip = str(zip_rank.index[0])
        top_score = float(zip_rank.iloc[0])
        top_rows = scoped[scoped["zip_key"] == top_zip].copy()
        top_idx = pd.to_numeric(top_rows["__market"], errors="coerce").idxmax()
        row = top_rows.loc[top_idx]
        st_name = str(row.get("state", "")).strip()

        w = pd.to_numeric(scoped.get("total_population"), errors="coerce").fillna(0.0).clip(lower=0.0)
        m = pd.to_numeric(scoped["__market"], errors="coerce")
        valid = m.notna()
        if valid.any() and float(w[valid].sum()) > 0:
            avg_market = float((m[valid] * w[valid]).sum() / w[valid].sum())
        elif valid.any():
            avg_market = float(m[valid].mean())
        else:
            avg_market = float("nan")

        def _fmt_v2(v):
            try:
                fv = float(v)
                if fv != fv:
                    return "N/A"
                return f"{fv:.2f}"
            except Exception:
                return "N/A"

        return (
            f"Under {option_label}, ZIP {top_zip}{(' (' + st_name + ')') if st_name else ''} ranks highest "
            f"{('in ' + asked_state + ' ') if asked_state else ''}with ZIP score {_fmt_v2(top_score)}. "
            f"Construct scores: Attractiveness {_fmt_v2(row.get('__attr'))}, "
            f"Ability to Win {_fmt_v2(row.get('__win'))}, Ripeness {_fmt_v2(row.get('__ripe'))}, "
            f"Economic Significance {_fmt_v2(row.get('__econ'))}. "
            f"Tier scores: Tier 1 {_fmt_v2(row.get('tier1'))}, Tier 2 {_fmt_v2(row.get('tier2'))}, Tier 3 {_fmt_v2(row.get('tier3'))}. "
            f"{('State' if asked_state else 'Dataset')} average market score: {_fmt_v2(avg_market)}."
        )

    if asks_construct_scores and "zipcode" in all_rows.columns and len(all_rows) > 0:
        zip_match = re.search(r"\b(\d{5})\b", q)
        if zip_match:
            target_zip = zip_match.group(1)
            scoped = all_rows.copy()
            scoped["zip_key"] = scoped["zipcode"].map(normalize_zip)
            asked_state = _state_in_query(q)
            if asked_state and "state" in scoped.columns:
                scoped = scoped[scoped["state"].astype(str).str.lower() == asked_state.lower()].copy()
            hit = scoped[scoped["zip_key"] == target_zip].copy()
            if len(hit) == 0:
                if asked_state:
                    return f"I couldn't find ZIP {target_zip} in {asked_state}."
                return f"I couldn't find ZIP {target_zip} in the loaded dataset."

            if "hospital_potential" in hit.columns:
                hp = pd.to_numeric(hit["hospital_potential"], errors="coerce")
                if hp.notna().any():
                    hit = hit.loc[[hp.idxmax()]]
            row = hit.iloc[0]
            st = str(row.get("state", "")).strip()

            opt = requested_opt or str(current_option or "").strip().lower()
            if "_opt" in opt:
                opt = opt.split("_")[-1]
            if opt not in {"opt1", "opt2", "opt4"}:
                opt = "opt2"
            cmap = {
                "opt1": {
                    "attr": "attractiveness_score_opt1",
                    "win": "win_score_opt1",
                    "ripe": "strength_score_opt1",
                    "econ": "rightness_score_opt1",
                },
                "opt2": {
                    "attr": "attractiveness_score_opt2",
                    "win": "win_score_opt2",
                    "ripe": "strength_score_opt2",
                    "econ": "rightness_score_opt2",
                },
                "opt4": {
                    "attr": "attractiveness_score_opt4",
                    "win": "win_score_opt4",
                    "ripe": "strength_score_opt4",
                    "econ": "rightness_score_opt4",
                },
            }[opt]
            av = pd.to_numeric(pd.Series([row.get(cmap["attr"])]), errors="coerce").iloc[0]
            wv = pd.to_numeric(pd.Series([row.get(cmap["win"])]), errors="coerce").iloc[0]
            rv = pd.to_numeric(pd.Series([row.get(cmap["ripe"])]), errors="coerce").iloc[0]
            ev = pd.to_numeric(pd.Series([row.get(cmap["econ"])]), errors="coerce").iloc[0]
            vals = [v for v in (av, wv, rv, ev) if pd.notna(v)]
            opt_market = (sum(vals) / len(vals)) if vals else float("nan")

            def _fmt_v3(v):
                try:
                    fv = float(v)
                    if fv != fv:
                        return "N/A"
                    return f"{fv:.2f}"
                except Exception:
                    return "N/A"

            return (
                f"Construct scores for ZIP {target_zip}{(' (' + st + ')') if st else ''} under "
                f"{opt.replace('opt', 'Option ')}: "
                f"Attractiveness {_fmt_v3(av)}, "
                f"Ability to Win {_fmt_v3(wv)}, "
                f"Ripeness {_fmt_v3(rv)}, "
                f"Economic Significance {_fmt_v3(ev)}; "
                f"ZIP score {_fmt_v3(opt_market)}; "
                f"Tier 1 {_fmt_v3(row.get('tier1'))}, Tier 2 {_fmt_v3(row.get('tier2'))}, Tier 3 {_fmt_v3(row.get('tier3'))}."
            )

    if asks_selected and asks_market_potential and asks_best:
        if not zip_records:
            return "No selected ZIP data is available right now."
        rows = pd.DataFrame(zip_records)
        if "hospital_potential" not in rows.columns:
            return "Market-potential values are unavailable for the selected ZIPs."
        s = pd.to_numeric(rows["hospital_potential"], errors="coerce")
        if not s.notna().any():
            return "Market-potential values are unavailable for the selected ZIPs."
        idx = s.idxmax()
        z = normalize_zip(str(rows.loc[idx, "zipcode"])) if "zipcode" in rows.columns else "N/A"
        st = str(rows.loc[idx, "state"]) if "state" in rows.columns else ""
        val = float(s.loc[idx])
        return f"For selected ZIPs, ZIP {z}{(' (' + st + ')') if st else ''} is strongest for market potential at {val:.2f}."
    if asks_population_growth:
        return None
    if not (asks_population and asks_highest):
        return None
    if asks_selected:
        if not zip_records:
            return "No selected ZIP data is available right now."
        if top_population is None:
            return "Population data is unavailable for the selected ZIPs."

        z = normalize_zip(str(top_population.get("zipcode", "")))
        st = str(top_population.get("state", "")).strip()
        pop_val = top_population.get("total_population")
        try:
            pop_num = int(float(pop_val))
            pop_txt = f"{pop_num:,}"
        except Exception:
            pop_txt = str(pop_val)
        state_txt = f" ({st})" if st else ""
        return (
            f"From the current selected ZIPs in the dashboard/parquet-backed data, "
            f"ZIP {z}{state_txt} has the highest total population at {pop_txt}."
        )

    if "total_population" not in all_rows.columns or len(all_rows) == 0:
        return None
    scoped = all_rows.copy()
    asked_state = _state_in_query(q)
    if asked_state and "state" in scoped.columns:
        scoped = scoped[scoped["state"].astype(str).str.lower() == asked_state.lower()].copy()
        if len(scoped) == 0:
            return f"No rows are available for {asked_state} in the dashboard data."
    pop = pd.to_numeric(scoped["total_population"], errors="coerce")
    if not pop.notna().any():
        return None
    idx = pop.idxmax()
    z = normalize_zip(str(scoped.loc[idx, "zipcode"])) if "zipcode" in scoped.columns else "N/A"
    st = str(scoped.loc[idx, "state"]) if "state" in scoped.columns else ""
    pop_val = pop.loc[idx]
    try:
        pop_num = int(float(pop_val))
        pop_txt = f"{pop_num:,}"
    except Exception:
        pop_txt = str(pop_val)
    state_txt = f" ({st})" if st else ""
    scope_txt = f"Across ZIPs in {asked_state}, " if asked_state else "Across all ZIPs in the dashboard/parquet-backed data, "
    return scope_txt + f"ZIP {z}{state_txt} has the highest total population at {pop_txt}."


def _clean_scalar(v):
    if pd.isna(v):
        return None
    if isinstance(v, (str, bool, int)):
        return v
    if isinstance(v, float):
        return round(v, 4)
    try:
        return float(v)
    except Exception:
        return str(v)


def run_agent_turn(
    msg: str,
    history: list,
    selected_zips: list[dict],
    data: pd.DataFrame,
    approved_tier_weights: dict,
    approved_score_option: str,
) -> list:
    msg = (msg or "").strip()
    if not msg:
        return list(history)
    history = list(history)
    history.append({"role": "user", "text": msg})
    sel_zip_list = [normalize_zip(str(z.get("zipcode", ""))) for z in selected_zips if str(z.get("zipcode", "")).strip()]
    selected_records = []
    highest_population = None
    available_states = sorted(data["state"].dropna().astype(str).unique().tolist()) if "state" in data.columns else []
    msa_count = int(data["msa_name"].dropna().astype(str).nunique()) if "msa_name" in data.columns else 0
    global_msa_preview = []
    if "msa_name" in data.columns and "hospital_potential" in data.columns:
        m = data.copy()
        m["hospital_potential"] = pd.to_numeric(m["hospital_potential"], errors="coerce").fillna(0)
        if "total_population" in m.columns:
            m["__w"] = pd.to_numeric(m["total_population"], errors="coerce").fillna(0)
        else:
            m["__w"] = 0.0
        if "state" in m.columns:
            grouped = (
                m.groupby(["msa_name", "state"], dropna=True)
                .apply(
                    lambda g: ((g["hospital_potential"] * g["__w"]).sum() / g["__w"].sum())
                    if g["__w"].sum() > 0
                    else g["hospital_potential"].mean()
                )
                .reset_index(name="score")
            )
        else:
            grouped = (
                m.groupby(["msa_name"], dropna=True)
                .apply(
                    lambda g: ((g["hospital_potential"] * g["__w"]).sum() / g["__w"].sum())
                    if g["__w"].sum() > 0
                    else g["hospital_potential"].mean()
                )
                .reset_index(name="score")
            )
        grouped = grouped.sort_values("score", ascending=False).head(60)
        for _, row in grouped.iterrows():
            global_msa_preview.append(
                {
                    "msa_name": str(row.get("msa_name", "")),
                    "state": str(row.get("state", "")) if "state" in grouped.columns else "",
                    "score": _clean_scalar(row.get("score")),
                }
            )
    if len(data) > 0 and sel_zip_list:
        rows = data.copy()
        rows["zip_key"] = rows["zipcode"].map(normalize_zip)
        rows = rows[rows["zip_key"].isin(sel_zip_list)].copy()
        order = {z: i for i, z in enumerate(sel_zip_list)}
        rows["__ord"] = rows["zip_key"].map(lambda z: order.get(z, 9999))
        rows = rows.sort_values("__ord")
        drop_cols = {"geometry", "__ord"}
        for _, r in rows.iterrows():
            rec = {}
            for c in rows.columns:
                if c in drop_cols:
                    continue
                rec[c] = _clean_scalar(r[c])
            selected_records.append(rec)
        if "total_population" in rows.columns and len(rows) > 0:
            pop = pd.to_numeric(rows["total_population"], errors="coerce")
            if pop.notna().any():
                top_idx = pop.idxmax()
                highest_population = {
                    "zipcode": normalize_zip(str(rows.loc[top_idx, "zipcode"])),
                    "state": str(rows.loc[top_idx, "state"]) if "state" in rows.columns else "",
                    "total_population": _clean_scalar(pop.loc[top_idx]),
                }
    context = {
        "tier1_data_source": "backend/data/raw/final_tier1_all_percentiles.parquet",
        "weights": {
            tier: float(approved_tier_weights.get(tier, DEFAULT_TIER_WEIGHTS.get(tier, 0.0)))
            for tier, _ in TIER_META
        },
        "selected_option": str(approved_score_option or DEFAULT_SCORE_COLUMN),
        "available_states": available_states,
        "row_count": int(len(data)),
        "zip_count": int(data["zipcode"].nunique()) if "zipcode" in data.columns else int(len(data)),
        "msa_count": msa_count,
        "global_msa_preview": global_msa_preview,
    }
    prior_turns = [m for m in history[:-1] if str(m.get("role", "")).lower() in {"user", "assistant"}]
    try:
        deterministic_reply = _deterministic_agent_reply(
            msg,
            selected_records,
            highest_population,
            data,
            str(approved_score_option or DEFAULT_SCORE_COLUMN).strip().lower(),
        )
        if deterministic_reply is not None:
            reply = deterministic_reply
        else:
            routed_reply = try_handle_query(data, msg)
            if routed_reply is not None:
                reply = routed_reply
            else:
                reply = query_agent(
                    user_message=msg,
                    history=prior_turns,
                    context=context,
                    df=data,
                    timeout_seconds=40,
                )
    except Exception as e:
        reply = f"Agent connection failed: {e}"
    history.append({"role": "assistant", "text": reply})
    return history
