import os
import sys
import re
import pandas as pd
import geopandas as gpd
from config import DATA_PATH, ENTITIES_PATH, BACKEND_DIR

_DEFAULT_STATES = {"Florida", "Georgia", "Alabama"}


def _auto_build_gpkg(empty_mode: bool = False):
    """Try to build the .gpkg automatically (FL, GA, AL)."""
    sys.path.insert(0, BACKEND_DIR)
    try:
        from build_base_map import build as build_map_data

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
    gdf = _merge_tier1_excels(gdf)
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


def _merge_tier1_excels(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Overlay raw Tier 1 Excel values onto the map dataframe by ZIP/state."""
    tier1_dir = os.path.join(BACKEND_DIR, "data", "raw", "tier1")
    if not os.path.isdir(tier1_dir):
        return gdf

    files = [
        os.path.join(tier1_dir, f)
        for f in os.listdir(tier1_dir)
        if f.lower().endswith(".xlsx")
    ]
    if not files:
        return gdf

    frames = []
    for fp in files:
        try:
            df = pd.read_excel(fp)
        except Exception:
            continue
        if df is None or df.empty:
            continue

        df.columns = [_to_snake(c) for c in df.columns]
        if "zip_code" not in df.columns and "zipcode" in df.columns:
            df["zip_code"] = df["zipcode"]
        if "county_fips" in df.columns and "county_flips" not in df.columns:
            df["county_flips"] = df["county_fips"]
        if "zip_code" not in df.columns:
            continue

        df["zip_code"] = df["zip_code"].astype(str).str.zfill(5)
        if "state_name" in df.columns:
            df["state_name"] = df["state_name"].astype(str).str.strip()
        else:
            base = os.path.basename(fp).split("_")[0]
            df["state_name"] = base
        df["state_key"] = df["state_name"].astype(str).str.strip().str.lower()

        if "data_year" in df.columns:
            df["data_year"] = pd.to_numeric(df["data_year"], errors="coerce")
            df = df.sort_values("data_year", ascending=False)
        elif "historical_year" in df.columns:
            df["historical_year"] = pd.to_numeric(df["historical_year"], errors="coerce")
            df = df.sort_values("historical_year", ascending=False)

        df = df.drop_duplicates(subset=["zip_code", "state_key"], keep="first")
        frames.append(df)

    if not frames:
        return gdf

    tier1 = pd.concat(frames, ignore_index=True)
    if tier1.empty:
        return gdf

    out = gdf.copy()
    out["zipcode"] = out["zipcode"].astype(str).str.zfill(5)
    out["state"] = out["state"].astype(str).str.strip()
    out["state_key"] = out["state"].str.lower()
    merged = out.merge(
        tier1,
        how="left",
        left_on=["zipcode", "state_key"],
        right_on=["zip_code", "state_key"],
        suffixes=("", "__t1"),
    )

    for col in tier1.columns:
        if col in ("zip_code", "state_name", "state_key"):
            continue
        t1_col = f"{col}__t1"
        if t1_col in merged.columns:
            if col in merged.columns:
                merged[col] = merged[t1_col].combine_first(merged[col])
            else:
                merged[col] = merged[t1_col]
            merged.drop(columns=[t1_col], inplace=True, errors="ignore")

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
