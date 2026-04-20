import colorsys
import os

TARGET_STATES = ["FL", "GA", "AL"]

# Brand orange #F37021 — map ramp uses same hue; RGB lerp looks pink/peach in the middle.
BRAND_ORANGE_HEX = "#F37021"
MAP_SCORE_ORANGE_RGB: tuple[int, int, int] = (243, 112, 33)


def _hsv_bucket_colors(n: int, rgb_end: tuple[int, int, int]) -> list[str]:
    """White → rgb_end at fixed orange hue (saturation/value ramp; avoids pink mid-tones)."""
    r, g, b = rgb_end[0] / 255.0, rgb_end[1] / 255.0, rgb_end[2] / 255.0
    h, s_end, v_end = colorsys.rgb_to_hsv(r, g, b)
    out: list[str] = []
    for i in range(n):
        t = i / (n - 1) if n > 1 else 0.0
        s = t * s_end
        v = 1.0 - t * (1.0 - v_end)
        rr, gg, bb = colorsys.hsv_to_rgb(h, s, v)
        out.append(
            f"#{int(round(rr * 255)):02x}{int(round(gg * 255)):02x}{int(round(bb * 255)):02x}"
        )
    return out


# 20 buckets (0–4 … 95–100): white → #F37021, matches ZIP Score legend strip.
SCORE_BUCKET_COLORS: list[str] = _hsv_bucket_colors(20, MAP_SCORE_ORANGE_RGB)


def score_fill_color(score: float | None) -> str:
    try:
        x = float(score if score is not None else 0)
    except (TypeError, ValueError):
        x = 0.0
    x = max(0.0, min(100.0, x))
    idx = min(19, max(0, int(x // 5)))
    return SCORE_BUCKET_COLORS[idx]


def ui_chrome_background() -> str:
    """App shell background (main layout, tabs strip, panels)."""
    return "#000000"


def score_legend_gradient_css() -> str:
    n = len(SCORE_BUCKET_COLORS)
    parts: list[str] = []
    for i, c in enumerate(SCORE_BUCKET_COLORS):
        a = i * 100.0 / n
        b = (i + 1) * 100.0 / n
        parts.append(f"{c} {a:.4f}%, {c} {b:.4f}%")
    return f"linear-gradient(90deg, {', '.join(parts)})"


def score_legend_gradient_css_vertical() -> str:
    """White (low) at bottom → orange (high) at top, for vertical map legend."""
    n = len(SCORE_BUCKET_COLORS)
    parts: list[str] = []
    for i, c in enumerate(SCORE_BUCKET_COLORS):
        a = i * 100.0 / n
        b = (i + 1) * 100.0 / n
        parts.append(f"{c} {a:.4f}%, {c} {b:.4f}%")
    return f"linear-gradient(to top, {', '.join(parts)})"


COLORMAP = score_fill_color

# Paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(APP_DIR)
_gpkg_override = os.environ.get("HOSPITAL_MARKET_GPKG", "").strip()
DATA_PATH = (
    _gpkg_override
    if _gpkg_override
    else os.path.join(REPO_ROOT, "backend", "data", "zcta_hospital_potential.gpkg")
)
ENTITIES_PATH = os.path.join(REPO_ROOT, "backend", "data", "gold", "entities.parquet")
ZCTA_SHP_DIR = os.path.join(REPO_ROOT, "backend", "data", "zcta_shp")
STATE_SHP_DIR = os.path.join(REPO_ROOT, "backend", "data", "state_shp")
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
WWW_DIR = os.path.join(APP_DIR, "modules", "map", "www")
os.makedirs(WWW_DIR, exist_ok=True)