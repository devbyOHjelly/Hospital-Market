from __future__ import annotations

from typing import Any
import os
import requests
import json

from .agent_config import (
    DEFAULT_MODEL,
    CHAT_TEMPERATURE,
    CHAT_MAX_TOKENS,
    MAX_SELECTED_ROWS_JSON_CHARS,
    SYSTEM_BEHAVIOR,
    OUTPUT_STRUCTURE_RULES,
    DEFAULT_SCORE_OPTION,
    DEFAULT_SCORE_COLUMN,
    SCORE_DEFINITIONS,
    OPTION_ALIASES,
)


def _normalize_endpoint(endpoint: str) -> str:
    ep = (endpoint or "").strip().rstrip("/")
    if not ep:
        return ""
    if ep.endswith("/chat/completions"):
        return ep
    if ep.endswith("/serving-endpoints"):
        return ep + "/chat/completions"
    return ep


def _normalize_host(host: str) -> str:
    h = (host or "").strip().rstrip("/")
    if not h:
        return ""
    if h.startswith("http://") or h.startswith("https://"):
        return h
    return f"https://{h}"


def _safe_opt_get(obj: Any) -> str:
    if obj is None:
        return ""
    for attr in ("get",):
        fn = getattr(obj, attr, None)
        if callable(fn):
            try:
                v = fn()
                if v is not None:
                    s = str(v).strip()
                    if s and s.lower() not in {"none", "null"}:
                        return s
            except Exception:
                pass
    try:
        s = str(obj).strip()
        if s and s.lower() not in {"none", "null", "optional.empty"}:
            return s
    except Exception:
        pass
    return ""


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


def _discover_databricks_host_token() -> tuple[str, str]:
    env_file = _read_env_file()
    host = _normalize_host(os.getenv("DATABRICKS_HOST", "") or env_file.get("DATABRICKS_HOST", ""))
    token = (
        os.getenv("DATABRICKS_TOKEN", "")
        or os.getenv("DATABRICKS_API_TOKEN", "")
        or env_file.get("DATABRICKS_TOKEN", "")
        or env_file.get("DATABRICKS_API_TOKEN", "")
        or ""
    ).strip()

    # Notebook-style discovery fallback.
    if not host:
        try:
            spark_obj = globals().get("spark")
            if spark_obj is not None:
                ws = spark_obj.conf.get("spark.databricks.workspaceUrl")
                host = _normalize_host(ws)
        except Exception:
            pass

    if not token:
        try:
            dbutils_obj = globals().get("dbutils")
            if dbutils_obj is not None:
                ctx = (
                    dbutils_obj.notebook.entry_point.getDbutils()
                    .notebook()
                    .getContext()
                )
                token = _safe_opt_get(ctx.apiToken())
        except Exception:
            pass

    return host, token


def _host_from_endpoint(endpoint_url: str) -> str:
    marker = "/serving-endpoints"
    idx = endpoint_url.find(marker)
    if idx > 0:
        return endpoint_url[:idx].rstrip("/")
    return ""


def _list_serving_endpoints(host: str, token: str, timeout_seconds: int) -> list[str]:
    if not host or not token:
        return []
    try:
        r = requests.get(
            f"{host}/api/2.0/serving-endpoints",
            headers={"Authorization": f"Bearer {token}"},
            timeout=timeout_seconds,
        )
        if not r.ok:
            return []
        data = r.json()
        items = data.get("endpoints") or []
        names: list[str] = []
        for ep in items:
            name = str(ep.get("name", "")).strip()
            if name:
                names.append(name)
        return names
    except Exception:
        return []


def _build_system_prompt(context: dict[str, Any] | None) -> str:
    ctx = context or {}
    available_states = ctx.get("available_states", [])
    row_count = ctx.get("row_count", 0)
    zip_count = ctx.get("zip_count", 0)
    msa_count = ctx.get("msa_count", 0)
    weights = ctx.get("weights", {})
    global_msa_preview = ctx.get("global_msa_preview", [])
    tier1_source = ctx.get("tier1_data_source", "")
    global_msa_preview_json = json.dumps(global_msa_preview, ensure_ascii=True)[:MAX_SELECTED_ROWS_JSON_CHARS]
    weights_json = json.dumps(weights, ensure_ascii=True)
    option_aliases_json = json.dumps(OPTION_ALIASES, ensure_ascii=True)
    score_defs_json = json.dumps(SCORE_DEFINITIONS, ensure_ascii=True)[:MAX_SELECTED_ROWS_JSON_CHARS]
    return (
        f"{SYSTEM_BEHAVIOR}\n"
        f"{OUTPUT_STRUCTURE_RULES}\n"
        f"Context:\n"
        f"- Available states (all data): {available_states}\n"
        f"- Row count (all data): {row_count}\n"
        f"- ZIP count (all data): {zip_count}\n"
        f"- MSA count (all data): {msa_count}\n"
        f"- Active construct weights: {weights_json}\n"
        f"- Tier 1 source: {tier1_source}\n"
        f"- Default attractiveness option: {DEFAULT_SCORE_OPTION}\n"
        f"- Default attractiveness score column: {DEFAULT_SCORE_COLUMN}\n"
        f"- Option aliases to score columns: {option_aliases_json}\n"
        f"- Score definition JSON (options/components/weights): {score_defs_json}\n"
        f"- Global MSA preview JSON: {global_msa_preview_json}\n"
    )


def _openai_messages(
    user_message: str,
    history: list[dict[str, str]] | None,
    context: dict[str, Any] | None,
) -> list[dict[str, str]]:
    messages: list[dict[str, str]] = [{"role": "system", "content": _build_system_prompt(context)}]
    for item in history or []:
        role = str(item.get("role", "")).strip().lower()
        content = str(item.get("text", "")).strip()
        if role in {"user", "assistant"} and content:
            messages.append({"role": role, "content": content})
    messages.append({"role": "user", "content": user_message})
    return messages


def _extract_text(payload: dict[str, Any]) -> str:
    def _from_content(content: Any) -> str:
        if isinstance(content, str):
            return content.strip()
        if isinstance(content, list):
            parts: list[str] = []
            for item in content:
                if isinstance(item, str) and item.strip():
                    parts.append(item.strip())
                elif isinstance(item, dict):
                    # Ignore reasoning-only blocks; surface final answer text only.
                    item_type = str(item.get("type", "")).strip().lower()
                    if item_type == "reasoning":
                        continue
                    txt = (
                        item.get("text")
                        or item.get("content")
                        or item.get("value")
                        or item.get("output_text")
                    )
                    if isinstance(txt, str) and txt.strip():
                        parts.append(txt.strip())
            if parts:
                return "\n".join(parts).strip()
        if isinstance(content, dict):
            item_type = str(content.get("type", "")).strip().lower()
            if item_type == "reasoning":
                return ""
            txt = (
                content.get("text")
                or content.get("content")
                or content.get("value")
                or content.get("output_text")
            )
            if isinstance(txt, str):
                return txt.strip()
        return ""

    try:
        choices = payload.get("choices") or []
        if choices:
            msg = choices[0].get("message") or {}
            content = _from_content(msg.get("content"))
            if content:
                return content
            msg_out = _from_content(msg.get("output_text"))
            if msg_out:
                return msg_out
            txt = choices[0].get("text")
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
    except Exception:
        pass

    preds = payload.get("predictions")
    if isinstance(preds, list) and preds:
        first = preds[0]
        if isinstance(first, dict):
            txt = (
                _from_content(first.get("content"))
                or _from_content(first.get("output"))
                or first.get("text")
                or first.get("answer")
                or first.get("response")
                or first.get("result")
            )
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
        if isinstance(first, str) and first.strip():
            return first.strip()

    # Last-resort top-level fields commonly returned by chat/inference gateways.
    for key in ("output_text", "text", "content", "answer", "response", "result"):
        val = payload.get(key)
        txt = _from_content(val)
        if txt:
            return txt
        if isinstance(val, str) and val.strip():
            return val.strip()

    # Give a compact payload preview for debugging rather than a generic error.
    preview = json.dumps(payload, ensure_ascii=True)[:600]
    raise RuntimeError(f"Agent response format not recognized. Payload preview: {preview}")


def query_agent(
    *,
    endpoint: str = "",
    api_key: str = "",
    user_message: str,
    history: list[dict[str, str]] | None = None,
    context: dict[str, Any] | None = None,
    model: str = DEFAULT_MODEL,
    timeout_seconds: int = 45,
) -> str:
    endpoint_url = _normalize_endpoint(endpoint)
    token = (api_key or "").strip()
    model = (
        os.getenv("DATABRICKS_MODEL", "")
        or _read_env_file().get("DATABRICKS_MODEL", "")
        or model
    )

    # If manual settings are omitted, use Databricks notebook-style auth.
    if not endpoint_url or not token:
        host, discovered_token = _discover_databricks_host_token()
        if not endpoint_url and host:
            endpoint_url = _normalize_endpoint(f"{host}/serving-endpoints")
        if not token and discovered_token:
            token = discovered_token

    if not endpoint_url:
        raise ValueError(
            "Agent endpoint is missing. In Databricks, set DATABRICKS_HOST or run inside a notebook/app context."
        )
    if not token:
        raise ValueError(
            "Agent token is missing. In Databricks, set DATABRICKS_TOKEN or use notebook context token."
        )

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }
    messages = _openai_messages(user_message, history, context)

    def _post_openai(model_name: str) -> requests.Response:
        body = {
            "model": model_name,
            "messages": messages,
            "temperature": CHAT_TEMPERATURE,
            "max_tokens": CHAT_MAX_TOKENS,
        }
        return requests.post(endpoint_url, json=body, headers=headers, timeout=timeout_seconds)

    # Primary path: OpenAI-compatible chat endpoint (Databricks serving compatible).
    resp = _post_openai(model)
    if resp.ok:
        return _extract_text(resp.json())

    # Databricks helper: provide clear model/endpoint guidance when endpoint is missing.
    if resp.status_code == 404 and "ENDPOINT_NOT_FOUND" in (resp.text or ""):
        host = _host_from_endpoint(endpoint_url)
        names = _list_serving_endpoints(host, token, timeout_seconds)
        if names:
            shown = ", ".join(names[:8])
            raise RuntimeError(
                "Configured model/endpoint was not found. "
                f"Available serving endpoints in your workspace: {shown}. "
                "Set DATABRICKS_MODEL in .env to one of these endpoint names."
            )
        raise RuntimeError(
            "Configured model/endpoint was not found and no serving endpoints were listed for this token. "
            "Create a serving endpoint or use a token with serving permissions."
        )

    # Databricks helper: if current endpoint is disabled/rate-limited, try alternatives automatically.
    if resp.status_code == 403 and "rate limit of 0" in (resp.text or "").lower():
        host = _host_from_endpoint(endpoint_url)
        names = _list_serving_endpoints(host, token, timeout_seconds)
        candidates = [n for n in names if n and n != model]
        for alt in candidates[:8]:
            alt_resp = _post_openai(alt)
            if alt_resp.ok:
                return _extract_text(alt_resp.json())
        if candidates:
            shown = ", ".join(candidates[:8])
            raise RuntimeError(
                "Current model endpoint is disabled by Databricks rate limits. "
                f"Tried alternatives without success: {shown}. "
                "Retry later or choose another endpoint with available quota."
            )
        raise RuntimeError(
            "Current model endpoint is disabled by Databricks rate limits and no alternative endpoints were available."
        )

    # Fallback path: generic chat service shape.
    fallback_body = {
        "message": user_message,
        "history": history or [],
        "context": context or {},
    }
    fallback_resp = requests.post(endpoint_url, json=fallback_body, headers=headers, timeout=timeout_seconds)
    if fallback_resp.ok:
        data = fallback_resp.json()
        if isinstance(data, dict):
            txt = data.get("response") or data.get("answer") or data.get("content")
            if isinstance(txt, str) and txt.strip():
                return txt.strip()
        raise RuntimeError("Fallback agent response was missing text.")

    raise RuntimeError(
        f"Agent call failed ({resp.status_code}): {resp.text[:220]}"
    )
