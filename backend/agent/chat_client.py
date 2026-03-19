from __future__ import annotations

import json
import os
import re
from typing import Any

import numpy as np
import pandas as pd
import requests

from .agent_config import (
    CHAT_MAX_TOKENS,
    CHAT_TEMPERATURE,
    DEFAULT_MODEL,
    DEFAULT_SCORE_COLUMN,
    DEFAULT_SCORE_OPTION,
    MAX_SELECTED_ROWS_JSON_CHARS,
    OPTION_ALIASES,
    RAW_TO_PCTILE,
    SCORE_DEFINITIONS,
    SYSTEM_BEHAVIOR,
    WHATIF_KEYWORDS,
)

# ── OpenRouter settings ────────────────────────────────────────────────────────
OPENROUTER_API_URL = "https://openrouter.ai/api/v1/chat/completions"
OPENROUTER_DEFAULT_MODEL = "meta-llama/llama-3.3-70b-instruct"

# System prompt used for the final narrative answer step (matches the notebook exactly)
_EXECUTIVE_SYSTEM_PROMPT = (
    "You are a strategic healthcare market analyst for Orlando Health, writing for senior "
    "executives. Every response MUST follow this exact structure:\n"
    "1. HEADLINE (one bold sentence): the direct answer or bottom-line conclusion.\n"
    "2. SUPPORTING BULLETS: 3-5 concise bullet points with the key facts, numbers, and context.\n"
    "3. STRATEGIC IMPLICATION (one bold sentence): what this means for Orlando Health.\n"
    "4. SUGGESTED FOLLOW-UP QUESTIONS: 2-3 specific questions the executive could ask next.\n"
    "Use dashes only in hyphenated words (e.g. part-time); "
    "use colons and semicolons to separate clauses, never dashes."
)


# ── Helpers ────────────────────────────────────────────────────────────────────

class _NumpyEncoder(json.JSONEncoder):
    """Converts numpy int64/float64/ndarray to native Python types for json.dumps."""
    def default(self, obj: Any) -> Any:
        if isinstance(obj, np.integer):
            return int(obj)
        if isinstance(obj, np.floating):
            return float(obj)
        if isinstance(obj, np.ndarray):
            return obj.tolist()
        return super().default(obj)


def _read_env_file() -> dict[str, str]:
    """Read simple KEY=VALUE pairs from project .env (if present)."""
    env: dict[str, str] = {}
    try:
        here = os.path.dirname(os.path.abspath(__file__))
        project_root = os.path.abspath(os.path.join(here, "..", ".."))
        env_path = os.path.join(project_root, ".env")
        if not os.path.exists(env_path):
            return env
        with open(env_path, "r", encoding="utf-8") as f:
            for raw in f:
                line = raw.strip()
                if not line or line.startswith("#") or "=" not in line:
                    continue
                k, v = line.split("=", 1)
                k = k.strip()
                v = v.strip().strip('"').strip("'")
                if k and v:
                    env[k] = v
    except Exception:
        return {}
    return env


def _get_token_and_model(api_key: str, model: str) -> tuple[str, str]:
    """Resolve OpenRouter API key and model from args, then env var, then .env file."""
    env_file = _read_env_file()
    token = (
        (api_key or "").strip()
        or os.getenv("OPENROUTER_API_KEY", "").strip()
        or env_file.get("OPENROUTER_API_KEY", "").strip()
    )
    if not token:
        raise ValueError(
            "OpenRouter API key is missing. "
            "Set OPENROUTER_API_KEY in your environment or .env file, "
            "or pass it as api_key= when calling query_agent()."
        )
    resolved_model = (
        os.getenv("OPENROUTER_MODEL", "").strip()
        or env_file.get("OPENROUTER_MODEL", "").strip()
        or (model or OPENROUTER_DEFAULT_MODEL).strip()
    )
    return token, resolved_model


def _call_openrouter(
    *,
    token: str,
    model: str,
    messages: list[dict[str, str]],
    max_tokens: int = 1000,
    temperature: float = 0.0,
    timeout_seconds: int = 60,
) -> str:
    """
    Single OpenRouter chat completion call.
    Returns the reply text string.
    verify=False bypasses corporate SSL proxy certificate errors.
    """
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    body = {
        "model": model,
        "messages": messages,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    resp = requests.post(
        OPENROUTER_API_URL,
        headers=headers,
        data=json.dumps(body),
        timeout=timeout_seconds,
        verify=False,  # bypasses corporate SSL proxy self-signed cert errors
    )
    result = resp.json()

    if not resp.ok:
        error_msg = ""
        if isinstance(result, dict) and "error" in result:
            error_msg = result["error"].get("message", str(result["error"]))
        raise RuntimeError(
            f"OpenRouter API call failed ({resp.status_code}): "
            f"{error_msg or resp.text[:220]}"
        )
    if isinstance(result, dict) and "error" in result:
        raise RuntimeError(
            f"OpenRouter returned an error: "
            f"{result['error'].get('message', str(result['error']))}"
        )

    choices = result.get("choices") or []
    if not choices:
        raise RuntimeError(f"OpenRouter returned no choices. Payload: {str(result)[:400]}")
    return (choices[0].get("message") or {}).get("content", "").strip()


# ── Step helpers mirroring the notebook pattern ───────────────────────────────

def _schema_context(df: pd.DataFrame) -> str:
    """Build the schema + sample + stats string passed to the code-generation LLM."""
    return (
        f"You have access to a pandas DataFrame called `df` with the following structure:\n\n"
        f"COLUMNS:\n{df.dtypes.to_string()}\n\n"
        f"SHAPE: {df.shape[0]} rows x {df.shape[1]} columns\n\n"
        f"SAMPLE (first 3 rows):\n{df.head(3).to_csv(index=False)}\n\n"
        f"STATISTICS:\n{df.describe().to_string()}"
    )


def _generate_pandas_code(
    df: pd.DataFrame,
    user_question: str,
    token: str,
    model: str,
    timeout_seconds: int,
) -> str:
    """
    Notebook Step 1: give the LLM schema + question, get back executable Pandas code.
    """
    prompt = (
        f"{_schema_context(df)}\n\n"
        f'User question: "{user_question}"\n\n'
        f"Write Python/Pandas code to answer this question using the DataFrame `df`.\n"
        f"Return ONLY executable Python code, no explanation, no markdown fences.\n"
        f"Store your final answer in a variable called `result`.\n"
        f"If the exact column does not exist, use the closest available columns and\n"
        f"add a comment explaining your assumption."
    )
    return _call_openrouter(
        token=token,
        model=model,
        messages=[
            {"role": "system", "content": "You are a Python/Pandas expert. Return only raw executable code."},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=512,
        temperature=0.1,
        timeout_seconds=timeout_seconds,
    )


def _execute_pandas_code(df: pd.DataFrame, generated_code: str) -> Any:
    """
    Notebook Step 2: run the generated code against the real DataFrame.
    Returns whatever the code stored in `result`, or an error string.
    """
    code = re.sub(r"```(?:python)?", "", generated_code).replace("```", "").strip()
    # Include builtins + common libraries so generated code never hits NameError
    exec_globals: dict[str, Any] = {
        "__builtins__": __builtins__,
        "pd": pd,
        "np": np,
        "df": df,
        "json": json,
        "re": re,
    }
    exec_locals: dict[str, Any] = {"df": df}
    try:
        exec(code, exec_globals, exec_locals)  # noqa: S102
        return exec_locals.get("result", exec_globals.get("result", "No result variable found."))
    except Exception as exc:
        return f"Code execution error: {exc}"


def _narrative_answer(
    user_question: str,
    result: Any,
    token: str,
    model: str,
    timeout_seconds: int,
) -> str:
    """
    Notebook Step 3: send the computed result back to the LLM for a structured
    executive-style narrative answer.
    """
    user_content = (
        f'Original question: "{user_question}"\n\n'
        f"The Pandas code returned this result:\n{result}\n\n"
        f"Answer using this exact structure:\n"
        f"HEADLINE: One bold sentence with the direct answer.\n"
        f"SUPPORTING BULLETS: 3-5 bullets with key facts and numbers.\n"
        f"STRATEGIC IMPLICATION: One bold sentence on what this means for Orlando Health.\n"
        f"SUGGESTED FOLLOW-UP QUESTIONS: 2-3 specific questions the executive could ask next."
    )
    return _call_openrouter(
        token=token,
        model=model,
        messages=[
            {"role": "system", "content": _EXECUTIVE_SYSTEM_PROMPT},
            {"role": "user",   "content": user_content},
        ],
        max_tokens=CHAT_MAX_TOKENS,
        temperature=0.3,
        timeout_seconds=timeout_seconds,
    )


def _execute_llm_generated_code(
    df: pd.DataFrame,
    user_question: str,
    token: str,
    model: str,
    timeout_seconds: int,
) -> str:
    """
    Full 3-step notebook pattern for surface queries:
      schema -> LLM writes Pandas code -> execute code -> LLM writes answer.
    Also used as a fallback from explanation / comparison / what-if handlers.
    """
    generated_code = _generate_pandas_code(df, user_question, token, model, timeout_seconds)
    result = _execute_pandas_code(df, generated_code)
    return _narrative_answer(user_question, result, token, model, timeout_seconds)


# ── Intent classifier ─────────────────────────────────────────────────────────

def _classify_intent(
    user_question: str,
    token: str,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Classify the user's question into surface_query / explanation / comparison."""
    prompt = (
        f"Classify this question and return JSON with these exact fields:\n\n"
        f'{{\n'
        f'  "intent": "surface_query" or "explanation" or "comparison",\n'
        f'  "score_column": "attractiveness_score_opt1" or "attractiveness_score_opt2" '
        f'or "attractiveness_score_opt4" or null,\n'
        f'  "geographic_level": "zip" or "county" or "msa" or null,\n'
        f'  "target_entity": "<specific name or top or null>",\n'
        f'  "needs_ranking_first": true or false\n'
        f'}}\n\n'
        f"CLASSIFICATION RULES:\n"
        f"- intent = 'explanation' if question contains: why, what makes, explain, reason, factor, drive, cause\n"
        f"- intent = 'comparison' if question contains: compare, vs, versus, difference, how does X differ\n"
        f"- intent = 'surface_query' for all others (what is, which, how many, average, highest, lowest)\n"
        f"- score_column: 'option 1' or 'opt1' -> attractiveness_score_opt1; "
        f"'option 2' or 'opt2' -> attractiveness_score_opt2; "
        f"'option 4' or 'opt4' -> attractiveness_score_opt4\n"
        f"- target_entity: extract specific MSA/county/zip name if mentioned, "
        f"or 'top' if asking about the highest scoring\n\n"
        f'Question: "{user_question}"'
    )
    raw = _call_openrouter(
        token=token,
        model=model,
        messages=[
            {"role": "system", "content": "You are a query intent classifier. Return only valid JSON, no markdown."},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=200,
        temperature=0.0,
        timeout_seconds=timeout_seconds,
    )
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except json.JSONDecodeError:
        q_lower = user_question.lower()
        return {
            "intent": (
                "explanation" if any(w in q_lower for w in ["why", "what makes", "explain", "reason", "factor"])
                else "comparison" if any(w in q_lower for w in ["compare", " vs ", "versus", "differ"])
                else "surface_query"
            ),
            "score_column": (
                "attractiveness_score_opt1" if "option 1" in q_lower or "opt1" in q_lower
                else "attractiveness_score_opt2" if "option 2" in q_lower or "opt2" in q_lower
                else "attractiveness_score_opt4" if "option 4" in q_lower or "opt4" in q_lower
                else None
            ),
            "geographic_level": (
                "zip" if re.search(r"\b\d{5}\b", user_question)
                else "county" if "county" in q_lower
                else "msa"
            ),
            "target_entity": "top",
            "needs_ranking_first": False,
        }


# ── Explanation engine ────────────────────────────────────────────────────────

def _explain_attractiveness_score(
    df: pd.DataFrame,
    user_question: str,
    intent: dict[str, Any],
    token: str,
    model: str,
    timeout_seconds: int,
) -> str:
    """
    Mirrors explain_attractiveness_score() from the notebook.
    Pulls real factor values, computes percentile comparisons vs dataset,
    then asks the LLM to narrate WHY the score is what it is.
    """
    score_col = intent.get("score_column")
    geo_level = intent.get("geographic_level", "msa")
    target    = intent.get("target_entity", "top")

    if not score_col or score_col not in SCORE_DEFINITIONS:
        return _execute_llm_generated_code(df, user_question, token, model, timeout_seconds)

    score_def      = SCORE_DEFINITIONS[score_col]
    component_cols = list(score_def["components"].keys())

    geo_col = {"msa": "msa_name", "county": "county_name", "zip": "zipcode"}.get(
        geo_level, "msa_name"
    )

    sum_cols = [
        c for c in component_cols if c in df.columns
        and any(k in c for k in ["population", "income", "unemployed", "migration"])
    ]
    agg_dict: dict[str, str] = {score_col: "mean"}
    for c in component_cols:
        if c in df.columns:
            agg_dict[c] = "sum" if c in sum_cols else "mean"

    if geo_col in df.columns and geo_level != "zip":
        grouped = df.groupby(geo_col).agg(agg_dict).reset_index()
    else:
        grouped = df.copy()

    if target == "top":
        target_row  = grouped.loc[grouped[score_col].idxmax()]
        target_name = target_row[geo_col]
    else:
        mask = grouped[geo_col].str.contains(target, case=False, na=False)
        if mask.sum() == 0:
            return _execute_llm_generated_code(df, user_question, token, model, timeout_seconds)
        target_row  = grouped[mask].iloc[0]
        target_name = target_row[geo_col]

    # Build component comparison vs dataset benchmarks
    component_analysis = []
    for col, meta in score_def["components"].items():
        if col not in grouped.columns:
            continue
        val      = target_row[col]
        col_mean = grouped[col].mean()
        pct_rank = (grouped[col] <= val).mean() * 100

        if meta["direction"] == "higher_is_better":
            strength = "STRONG" if pct_rank >= 75 else "MODERATE" if pct_rank >= 40 else "WEAK"
        else:
            strength = "STRONG" if pct_rank <= 25 else "MODERATE" if pct_rank <= 60 else "WEAK"

        component_analysis.append({
            "factor":      meta["label"],
            "weight":      f"{meta['weight'] * 100:.0f}%",
            "value":       round(float(val), 2),
            "dataset_avg": round(float(col_mean), 2),
            "percentile":  f"{float(pct_rank):.0f}th",
            "strength":    strength,
        })

    prompt = (
        f'The user asked: "{user_question}"\n\n'
        f"Answer: **{target_name}** has the {'highest ' if target == 'top' else ''}"
        f"{score_def['description']} ({score_col}) = "
        f"{round(float(target_row[score_col]), 3)}.\n\n"
        f"Factor-by-factor breakdown (vs all {geo_level.upper()}-level markets):\n\n"
        f"{json.dumps(component_analysis, indent=2, cls=_NumpyEncoder)}\n\n"
        f"Score formula: {score_def['description']}\n\n"
        f"Write a clear executive explanation that:\n"
        f"1. States the conclusion first (entity name + score)\n"
        f"2. Explains the TOP 2-3 strongest driving factors with percentile ranks vs dataset average\n"
        f"3. Notes any weak factors that held the score back\n"
        f"4. Ends with the strategic implication for Orlando Health\n\n"
        f"Use plain business language. Be specific with numbers. "
        f"Use colons and semicolons to separate clauses, not dashes.\n"
        f"End with 'Suggested Follow-Up Questions:' listing 2-3 specific next questions."
    )
    return _call_openrouter(
        token=token,
        model=model,
        messages=[
            {"role": "system", "content": _EXECUTIVE_SYSTEM_PROMPT},
            {"role": "user",   "content": prompt},
        ],
        max_tokens=CHAT_MAX_TOKENS,
        temperature=0.3,
        timeout_seconds=timeout_seconds,
    )


# ── Comparison engine ─────────────────────────────────────────────────────────

def _handle_comparison(
    df: pd.DataFrame,
    user_question: str,
    intent: dict[str, Any],
    token: str,
    model: str,
    timeout_seconds: int,
) -> str:
    """Mirrors handle_comparison() from the notebook."""
    score_col = intent.get("score_column") or DEFAULT_SCORE_COLUMN
    geo_level = intent.get("geographic_level", "msa")
    geo_col   = {"msa": "msa_name", "county": "county_name", "zip": "zipcode"}.get(
        geo_level, "msa_name"
    )

    if geo_col in df.columns and geo_level != "zip":
        grouped = df.groupby(geo_col)[score_col].mean().reset_index()
        grouped.columns = [geo_col, score_col]
    else:
        grouped = df[[geo_col, score_col]].copy()

    available_names = grouped[geo_col].dropna().unique().tolist()

    raw = _call_openrouter(
        token=token,
        model=model,
        messages=[
            {"role": "system", "content": "You are a string matcher. Return only valid JSON."},
            {"role": "user", "content": (
                f"From this list of available names:\n{available_names}\n\n"
                f"Find the TWO names that best match what the user is comparing in:\n"
                f'"{user_question}"\n\n'
                f'Return JSON: {{"entity_1": "<exact name from list>", "entity_2": "<exact name from list>"}}'
            )},
        ],
        max_tokens=100,
        temperature=0.0,
        timeout_seconds=timeout_seconds,
    )
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        entities = json.loads(raw)
        name_1, name_2 = entities["entity_1"], entities["entity_2"]
    except Exception:
        top2   = grouped.nlargest(2, score_col)[geo_col].tolist()
        name_1, name_2 = top2[0], top2[1]

    row_1 = grouped[grouped[geo_col] == name_1].iloc[0] if name_1 in grouped[geo_col].values else None
    row_2 = grouped[grouped[geo_col] == name_2].iloc[0] if name_2 in grouped[geo_col].values else None

    if row_1 is None or row_2 is None:
        return _execute_llm_generated_code(df, user_question, token, model, timeout_seconds)

    score_1 = round(float(row_1[score_col]), 3)
    score_2 = round(float(row_2[score_col]), 3)
    winner  = name_1 if score_1 >= score_2 else name_2
    diff    = round(abs(score_1 - score_2), 3)

    expl_1 = _explain_attractiveness_score(
        df, f"Why does {name_1} score the way it does?",
        {**intent, "target_entity": name_1}, token, model, timeout_seconds,
    )
    expl_2 = _explain_attractiveness_score(
        df, f"Why does {name_2} score the way it does?",
        {**intent, "target_entity": name_2}, token, model, timeout_seconds,
    )

    return _call_openrouter(
        token=token,
        model=model,
        messages=[
            {"role": "system", "content": _EXECUTIVE_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f"Compare these two markets on {score_col}:\n\n"
                f"{name_1}: {score_1}\n"
                f"{name_2}: {score_2}\n"
                f"Difference: {diff} points (winner: {winner})\n\n"
                f"--- {name_1} factor analysis ---\n{expl_1}\n\n"
                f"--- {name_2} factor analysis ---\n{expl_2}\n\n"
                f"Write a 4-6 sentence executive comparison covering:\n"
                f"1. Which market wins and by how much\n"
                f"2. The 1-2 factors where {name_1} leads\n"
                f"3. The 1-2 factors where {name_2} leads\n"
                f"4. A final strategic recommendation for Orlando Health\n"
                f"Be specific with numbers. Use colons and semicolons, not dashes.\n"
                f"End with 'Suggested Follow-Up Questions:' listing 2-3 next questions."
            )},
        ],
        max_tokens=500,
        temperature=0.3,
        timeout_seconds=timeout_seconds,
    )


# ── What-If engine ────────────────────────────────────────────────────────────

def _detect_whatif_scenario(
    user_question: str,
    df: pd.DataFrame,
    token: str,
    model: str,
    timeout_seconds: int,
) -> dict[str, Any]:
    """Mirrors detect_whatif_scenario() from the notebook."""
    available_cols = df.dtypes.to_string()
    available_msas = (
        df["msa_name"].dropna().unique().tolist() if "msa_name" in df.columns else []
    )
    raw = _call_openrouter(
        token=token,
        model=model,
        messages=[
            {"role": "system", "content": "You are a scenario parser. Return only valid JSON."},
            {"role": "user", "content": (
                f"Extract the hypothetical scenario from this question and return JSON:\n\n"
                f'{{\n'
                f'  "is_whatif": true or false,\n'
                f'  "changes": [\n'
                f'    {{"entity": "<MSA/county/zip name>", "column": "<df column>", '
                f'"operation": "multiply|add|set", "value": <number>}}\n'
                f'  ],\n'
                f'  "score_column": "attractiveness_score_opt1|opt2|opt4",\n'
                f'  "geographic_level": "msa|county|zip"\n'
                f'}}\n\n'
                f"Available columns:\n{available_cols}\n\n"
                f"Available MSA names (sample): {available_msas[:20]}\n\n"
                f"Operation mapping: 'doubles' -> multiply 2; 'triples' -> multiply 3; "
                f"'grows 50%' -> multiply 1.5; 'drops to X' -> set X; 'increases by X' -> add X\n\n"
                f'Question: "{user_question}"'
            )},
        ],
        max_tokens=300,
        temperature=0.0,
        timeout_seconds=timeout_seconds,
    )
    raw = raw.replace("```json", "").replace("```", "").strip()
    try:
        return json.loads(raw)
    except Exception:
        return {"is_whatif": False, "changes": []}


def _apply_whatif_scenario(df: pd.DataFrame, scenario: dict[str, Any]) -> pd.DataFrame:
    """Mirrors apply_whatif_scenario() from the notebook."""
    df_out  = df.copy()
    geo_col = {"msa": "msa_name", "county": "county_name", "zip": "zipcode"}.get(
        scenario.get("geographic_level", "msa"), "msa_name"
    )
    for change in scenario.get("changes", []):
        entity    = change["entity"]
        col       = change["column"]
        operation = change["operation"]
        value     = change["value"]
        # Auto-resolve percentile col -> raw col
        if col.endswith("_pctile"):
            col = next((r for r, p in RAW_TO_PCTILE.items() if p == col), col)
        if col not in df_out.columns:
            continue
        mask = df_out[geo_col].str.contains(entity, case=False, na=False)
        if mask.sum() == 0:
            continue
        if operation == "multiply":
            df_out.loc[mask, col] = df_out.loc[mask, col] * value
        elif operation == "add":
            df_out.loc[mask, col] = df_out.loc[mask, col] + value
        elif operation == "set":
            df_out.loc[mask, col] = value
    return df_out


def _rescore_after_scenario(
    df_original: pd.DataFrame,
    df_scenario: pd.DataFrame,
    score_col: str,
) -> pd.DataFrame:
    """Mirrors rescore_after_scenario() from the notebook."""
    if score_col not in SCORE_DEFINITIONS:
        return df_scenario

    score_def   = SCORE_DEFINITIONS[score_col]
    df_rescored = df_scenario.copy()

    for pctile_col, meta in score_def["components"].items():
        raw_col = next(
            (r for r, p in RAW_TO_PCTILE.items() if p == pctile_col), None
        )
        if raw_col is None or raw_col not in df_rescored.columns:
            continue
        orig_vals = df_original[raw_col].dropna().values

        def _pctile(v: float, orig: np.ndarray = orig_vals,
                    direction: str = meta["direction"]) -> float:
            pct = (orig <= v).mean() * 99 if direction == "higher_is_better" else (orig >= v).mean() * 99
            return round(float(np.clip(pct, 0, 99)), 2)

        df_rescored[pctile_col] = df_rescored[raw_col].apply(_pctile)

    weighted_sum = sum(
        df_rescored[pctile_col] * meta["weight"]
        for pctile_col, meta in score_def["components"].items()
        if pctile_col in df_rescored.columns
    )
    df_rescored[score_col] = (weighted_sum / 99 * 100).round(2)
    return df_rescored


def _handle_whatif(
    df: pd.DataFrame,
    user_question: str,
    scenario: dict[str, Any],
    token: str,
    model: str,
    timeout_seconds: int,
) -> str:
    """Mirrors handle_whatif() from the notebook."""
    score_col = scenario.get("score_column", DEFAULT_SCORE_COLUMN)
    geo_level = scenario.get("geographic_level", "msa")
    geo_col   = {"msa": "msa_name", "county": "county_name", "zip": "zipcode"}.get(
        geo_level, "msa_name"
    )
    entities_changed = list({c["entity"] for c in scenario.get("changes", [])})

    grouped_before = (
        df.groupby(geo_col)[score_col].mean().reset_index()
        if geo_level != "zip" else df[[geo_col, score_col]].copy()
    )

    df_mod    = _apply_whatif_scenario(df, scenario)
    df_mod    = _rescore_after_scenario(df, df_mod, score_col)

    grouped_after = (
        df_mod.groupby(geo_col)[score_col].mean().reset_index()
        if geo_level != "zip" else df_mod[[geo_col, score_col]].copy()
    )

    comparison_rows = []
    for entity in entities_changed:
        mb = grouped_before[geo_col].str.contains(entity, case=False, na=False)
        ma = grouped_after[geo_col].str.contains(entity, case=False, na=False)
        if mb.sum() == 0 or ma.sum() == 0:
            continue
        sb = round(float(grouped_before[mb][score_col].iloc[0]), 4)
        sa = round(float(grouped_after[ma][score_col].iloc[0]), 4)
        comparison_rows.append({
            "entity":       grouped_before[mb][geo_col].iloc[0],
            "score_before": sb,
            "score_after":  sa,
            "delta":        round(sa - sb, 4),
            "delta_pct":    round((sa - sb) / sb * 100, 1) if sb else 0,
        })

    rank_before = grouped_before.sort_values(score_col, ascending=False).reset_index(drop=True)
    rank_after  = grouped_after.sort_values(score_col, ascending=False).reset_index(drop=True)
    rank_before["rank"] = rank_before.index + 1
    rank_after["rank"]  = rank_after.index + 1

    rank_changes = []
    for row in comparison_rows:
        rb = rank_before[rank_before[geo_col].str.contains(row["entity"], case=False, na=False)]
        ra = rank_after[rank_after[geo_col].str.contains(row["entity"], case=False, na=False)]
        if len(rb) > 0 and len(ra) > 0:
            rank_changes.append({
                "entity":      row["entity"],
                "rank_before": int(rb["rank"].iloc[0]),
                "rank_after":  int(ra["rank"].iloc[0]),
                "rank_change": int(rb["rank"].iloc[0]) - int(ra["rank"].iloc[0]),
            })

    return _call_openrouter(
        token=token,
        model=model,
        messages=[
            {"role": "system", "content": _EXECUTIVE_SYSTEM_PROMPT},
            {"role": "user", "content": (
                f'User asked: "{user_question}"\n\n'
                f"NOTE: Scores use a fixed baseline so before/after values are directly comparable.\n\n"
                f"SCORE CHANGES:\n{json.dumps(comparison_rows, indent=2, cls=_NumpyEncoder)}\n\n"
                f"RANKING CHANGES:\n{json.dumps(rank_changes, indent=2, cls=_NumpyEncoder)}\n\n"
                f"Top 5 BEFORE:\n{rank_before[[geo_col, score_col]].head(5).to_string(index=False)}\n\n"
                f"Top 5 AFTER:\n{rank_after[[geo_col, score_col]].head(5).to_string(index=False)}\n\n"
                f"Write a 4-6 sentence executive response covering:\n"
                f"1. What the scenario assumed\n"
                f"2. Exact score change (before -> after)\n"
                f"3. Ranking change (rank X -> rank Y)\n"
                f"4. Both before AND after rank for every entity mentioned\n"
                f"5. If two entities compared: which leads and by how much\n"
                f"Be specific with numbers. Use colons/semicolons, not dashes.\n"
                f"End with 'Suggested Follow-Up Questions:' listing 2-3 next questions."
            )},
        ],
        max_tokens=500,
        temperature=0.3,
        timeout_seconds=timeout_seconds,
    )


# ── Public entry point ────────────────────────────────────────────────────────

def query_agent(
    *,
    endpoint: str = "",          # unused; kept for call-site compatibility
    api_key: str = "",
    user_message: str,
    history: list[dict[str, str]] | None = None,
    context: dict[str, Any] | None = None,
    model: str = OPENROUTER_DEFAULT_MODEL,
    timeout_seconds: int = 60,
    df: pd.DataFrame | None = None,
) -> str:
    """
    Main entry point for the agent.

    When `df` is supplied the agent uses the full notebook agentic pattern:
      what-if check -> intent classify -> explanation / comparison / code-execute path.

    When `df` is None it falls back to context-only LLM answering (original behaviour,
    used when the DataFrame cannot be passed directly to this layer).
    """
    token, resolved_model = _get_token_and_model(api_key, model)

    # ── DataFrame path: full notebook agentic pattern ─────────────────────────
    if df is not None and not df.empty:
        from .query_router import _ensure_score_columns  # avoid circular import
        df = _ensure_score_columns(df)

        # Step 0: what-if routing (highest priority)
        if any(kw in user_message.lower() for kw in WHATIF_KEYWORDS):
            scenario = _detect_whatif_scenario(user_message, df, token, resolved_model, timeout_seconds)
            if scenario.get("is_whatif") and scenario.get("changes"):
                return _handle_whatif(df, user_message, scenario, token, resolved_model, timeout_seconds)

        # Step 1: classify intent
        intent = _classify_intent(user_message, token, resolved_model, timeout_seconds)
        intent_type = intent.get("intent", "surface_query")

        if intent_type == "explanation":
            return _explain_attractiveness_score(
                df, user_message, intent, token, resolved_model, timeout_seconds
            )
        elif intent_type == "comparison":
            return _handle_comparison(
                df, user_message, intent, token, resolved_model, timeout_seconds
            )
        else:
            # surface_query: 3-step code-generate -> execute -> narrate
            return _execute_llm_generated_code(
                df, user_message, token, resolved_model, timeout_seconds
            )

    # ── Context-only fallback (no DataFrame supplied) ─────────────────────────
    ctx = context or {}
    system_prompt = (
        f"{SYSTEM_BEHAVIOR}\n"
        f"Context:\n"
        f"- Available states: {ctx.get('available_states', [])}\n"
        f"- Row count: {ctx.get('row_count', 0)}\n"
        f"- Default scoring option: {DEFAULT_SCORE_OPTION}\n"
        f"- Score definitions: "
        f"{json.dumps(SCORE_DEFINITIONS, cls=_NumpyEncoder)[:MAX_SELECTED_ROWS_JSON_CHARS]}\n"
        f"- Global MSA preview: "
        f"{json.dumps(ctx.get('global_msa_preview', []), cls=_NumpyEncoder)[:MAX_SELECTED_ROWS_JSON_CHARS]}\n"
    )
    messages: list[dict[str, str]] = [{"role": "system", "content": system_prompt}]
    for item in history or []:
        role    = str(item.get("role", "")).strip().lower()
        content = str(item.get("text", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})

    return _call_openrouter(
        token=token,
        model=resolved_model,
        messages=messages,
        max_tokens=CHAT_MAX_TOKENS,
        temperature=CHAT_TEMPERATURE,
        timeout_seconds=timeout_seconds,
    )