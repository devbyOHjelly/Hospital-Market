import os
import sys
import re
import pandas as pd
import geopandas as gpd
from frontend.config import DATA_PATH, ENTITIES_PATH, BACKEND_DIR

_DEFAULT_STATES = {"Florida", "Georgia", "Alabama"}
_TIER1_PARQUET_PATH = os.path.join(
    BACKEND_DIR, "data", "raw", "tier1", "final_tier1_percentiles.parquet"
)


def _auto_build_gpkg(empty_mode: bool = False):
    """Try to build the .gpkg automatically (FL, GA, AL)."""
    try:
        from backend.modules.map.build_base_map import build as build_map_data

        print(f"  Auto-building base map for: {sorted(_DEFAULT_STATES)}")
        build_map_data(state_filter=_DEFAULT_STATES, empty_mode=empty_mode)
    except Exception as e:
        raise FileNotFoundError(
            f"Base map not found at {DATA_PATH} and auto-build failed: {e}\n"
            f"Run:  python backend/pipeline.py"
        )


def load_data() -> gpd.GeoDataFrame:
    if not os.path.exists(DATA_PATH):
        has_entities = os.path.exists(ENTITIES_PATH)
        if has_entities:
            print("  .gpkg missing — auto-building from entities.parquet ...")
            _auto_build_gpkg(empty_mode=False)
        else:
            print("  .gpkg and entities.parquet missing — building map in empty mode ...")
            _auto_build_gpkg(empty_mode=True)
    gdf = gpd.read_file(DATA_PATH)
    gdf = _merge_tier1_parquet(gdf)
    gdf = _add_place_names(gdf)
    for col in (
        "entity_count",
        "hospital_count",
        "avg_entity_score",
        "avg_confidence",
        "hospital_potential",
    ):
        if col not in gdf.columns:
            gdf[col] = 0.0
    return gdf


def _to_snake(name: str) -> str:
    s = str(name).strip().lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = re.sub(r"_+", "_", s).strip("_")
    return s


def _norm_zip5(v: object) -> str:
    s = str(v).strip()
    if not s or s.lower() in {"nan", "none"}:
        return ""
    if s.endswith(".0"):
        s = s[:-2]
    digits = "".join(ch for ch in s if ch.isdigit())
    return digits[:5].zfill(5) if digits else ""


def _merge_tier1_parquet(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Overlay final Tier 1 parquet values onto map dataframe by ZIP/state."""
    if not os.path.exists(_TIER1_PARQUET_PATH):
        print(f"  Tier 1 parquet not found: {_TIER1_PARQUET_PATH}")
        return gdf

    try:
        tier1 = pd.read_parquet(_TIER1_PARQUET_PATH)
    except Exception as e:
        print(f"  Failed to read Tier 1 parquet ({_TIER1_PARQUET_PATH}): {e}")
        return gdf

    if tier1 is None or tier1.empty:
        print(f"  Tier 1 parquet is empty: {_TIER1_PARQUET_PATH}")
        return gdf

    tier1 = tier1.copy()
    tier1.columns = [_to_snake(c) for c in tier1.columns]

    # Normalize ZIP/state key columns from likely schema variants.
    if "zip_code" not in tier1.columns:
        if "zipcode" in tier1.columns:
            tier1["zip_code"] = tier1["zipcode"]
        elif "zip" in tier1.columns:
            tier1["zip_code"] = tier1["zip"]
    if "zip_code" not in tier1.columns:
        print("  Tier 1 parquet missing ZIP column (zip_code/zipcode/zip).")
        return gdf

    if "state_name" not in tier1.columns:
        if "state" in tier1.columns:
            tier1["state_name"] = tier1["state"]
        elif "state_abbr" in tier1.columns:
            tier1["state_name"] = tier1["state_abbr"]

    tier1["zip_code"] = tier1["zip_code"].map(_norm_zip5)
    if "state_name" in tier1.columns:
        tier1["state_name"] = tier1["state_name"].astype(str).str.strip()
        # Normalize both full names and 2-letter abbreviations into a comparable key.
        _state_map = {
            "al": "alabama",
            "fl": "florida",
            "ga": "georgia",
            "alabama": "alabama",
            "florida": "florida",
            "georgia": "georgia",
        }
        tier1["state_key"] = (
            tier1["state_name"]
            .astype(str)
            .str.strip()
            .str.lower()
            .map(lambda s: _state_map.get(s, s))
        )
    else:
        tier1["state_key"] = ""

    # Keep most recent row by ZIP/state if a year column exists.
    if "data_year" in tier1.columns:
        tier1["data_year"] = pd.to_numeric(tier1["data_year"], errors="coerce")
        tier1 = tier1.sort_values("data_year", ascending=False)
    elif "historical_year" in tier1.columns:
        tier1["historical_year"] = pd.to_numeric(tier1["historical_year"], errors="coerce")
        tier1 = tier1.sort_values("historical_year", ascending=False)

    dedupe_keys = ["zip_code", "state_key"] if "state_name" in tier1.columns else ["zip_code"]
    tier1 = tier1.drop_duplicates(subset=dedupe_keys, keep="first")

    out = gdf.copy()
    out["zipcode"] = out["zipcode"].map(_norm_zip5)
    out["state"] = out["state"].astype(str).str.strip()
    _state_map = {
        "al": "alabama",
        "fl": "florida",
        "ga": "georgia",
        "alabama": "alabama",
        "florida": "florida",
        "georgia": "georgia",
    }
    out["state_key"] = out["state"].str.lower().map(lambda s: _state_map.get(s, s))

    base_cols = [c for c in tier1.columns if c not in ("zip_code", "state_name", "state_key")]
    exact = None
    if "state_name" in tier1.columns:
        # First pass: exact ZIP + normalized state match.
        exact = out.merge(
            tier1,
            how="left",
            left_on=["zipcode", "state_key"],
            right_on=["zip_code", "state_key"],
            suffixes=("", "__t1_exact"),
        )

    # Second pass: ZIP-only fallback so every ZIP gets Tier 1 if available.
    zip_only = tier1.drop_duplicates(subset=["zip_code"], keep="first")
    merged = out.merge(
        zip_only,
        how="left",
        left_on="zipcode",
        right_on="zip_code",
        suffixes=("", "__t1_zip"),
    )

    # Overlay exact-match values first, then ZIP fallback, then original.
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

    # Drop temporary merge helper columns.
    for c in (
        "zip_code",
        "zip_code__t1_zip",
        "state_key",
        "state_name",
    ):
        merged.drop(columns=[c], inplace=True, errors="ignore")

    states_present = []
    if "state_name" in tier1.columns:
        states_present = sorted(
            s for s in tier1["state_name"].dropna().astype(str).str.strip().unique().tolist() if s
        )
    else:
        matched_states = merged.loc[merged["zipcode"].notna(), "state"].dropna().astype(str).str.strip()
        states_present = sorted(s for s in matched_states.unique().tolist() if s)

    print(f"  Tier 1 source: {_TIER1_PARQUET_PATH}")
    print(f"  Tier 1 states from ZIP records: {states_present if states_present else 'none detected'}")
    return merged


def _add_place_names(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Attach a human-readable place label by ZIP for map tooltip display."""
    out = gdf.copy()
    if "zipcode" not in out.columns:
        return out
    out["zipcode"] = out["zipcode"].astype(str).str.zfill(5)
    try:
        import pgeocode

        nomi = pgeocode.Nominatim("us")
        unique_zips = out["zipcode"].dropna().astype(str).str.zfill(5).unique().tolist()
        geo = nomi.query_postal_code(unique_zips)
        if "postal_code" not in geo.columns:
            return out
        geo["postal_code"] = geo["postal_code"].astype(str).str.zfill(5)
        city_col = "place_name" if "place_name" in geo.columns else None
        state_col = "state_name" if "state_name" in geo.columns else None
        if not city_col:
            return out
        geo[city_col] = geo[city_col].fillna("").astype(str).str.strip()
        if state_col:
            geo[state_col] = geo[state_col].fillna("").astype(str).str.strip()
            geo["place_name"] = geo.apply(
                lambda r: (
                    f"{r[city_col]}, {r[state_col]}"
                    if r[city_col] and r[state_col]
                    else r[city_col]
                ),
                axis=1,
            )
        else:
            geo["place_name"] = geo[city_col]
        lookup = dict(zip(geo["postal_code"], geo["place_name"]))
        out["place_name"] = out["zipcode"].map(lookup).fillna("")
    except Exception:
        out["place_name"] = ""
    return out


def load_entities() -> pd.DataFrame | None:
    if not os.path.exists(ENTITIES_PATH):
        print("  entities.parquet not found — skipping entity layer")
        return None

    df = pd.read_parquet(ENTITIES_PATH)
    print(f"  Loaded {len(df):,} entities")

    if "lat" not in df.columns or "lon" not in df.columns:
        df = _geocode_entities(df)

    df = df.dropna(subset=["lat", "lon"])
    print(f"  Entities with coordinates: {len(df):,}")
    return df


def _geocode_entities(df: pd.DataFrame) -> pd.DataFrame:
    try:
        import pgeocode

        nomi = pgeocode.Nominatim("us")
        zips = df["zip"].dropna().unique().tolist()
        geo = nomi.query_postal_code(zips)
        lookup = dict(
            zip(
                geo["postal_code"].astype(str).str.zfill(5),
                zip(geo["latitude"], geo["longitude"]),
            )
        )
        df["lat"] = df["zip"].map(lambda z: lookup.get(z, (None, None))[0])
        df["lon"] = df["zip"].map(lambda z: lookup.get(z, (None, None))[1])
        print(f"  Geocoded {df['lat'].notna().sum():,}/{len(df):,} entities")
    except ImportError:
        print("  pgeocode not installed — no entity coordinates")
        df["lat"] = None
        df["lon"] = None
    return df


print("Loading base map ...")
gdf = load_data()
print(f"  {len(gdf):,} ZCTAs loaded")

print("Loading entity data ...")
ENTITIES_DF = load_entities()
