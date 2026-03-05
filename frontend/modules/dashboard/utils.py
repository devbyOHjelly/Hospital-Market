"""Small shared helpers for dashboard features."""

from __future__ import annotations


def normalize_zip(value) -> str:
    """Normalize mixed ZIP values (e.g., 34737.0) to a clean string."""
    s = str(value).strip()
    if not s or s.lower() == "nan":
        return ""
    try:
        n = int(float(s))
    except (TypeError, ValueError):
        return s
    if n < 0:
        return s
    return str(n).zfill(5) if n <= 99999 else str(n)


def selected_zip_set(selected: list[dict]) -> set[str]:
    """Return normalized ZIP set from selected ZIP payloads."""
    out = set()
    for item in selected:
        z = normalize_zip(item.get("zipcode", ""))
        if z:
            out.add(z)
    return out
