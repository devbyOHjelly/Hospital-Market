from __future__ import annotations
from pathlib import Path
from backend.map.scoring_from_config import compute_hospital_potential, merge_tier1_onto_gdf
import argparse
import os
import zipfile
from pathlib import Path
import geopandas as gpd
import pandas as pd
import requests
import yaml

BACKEND_DIR = Path(__file__).resolve().parents[1]
DATA_DIR = BACKEND_DIR / "data"
CONFIG_PATH = BACKEND_DIR / "configs" / "config.yml"

ZCTA_URLS = [
    "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_zcta520_500k.zip",
    "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_us_zcta520_500k.zip",
]
STATE_URLS = [
    "https://www2.census.gov/geo/tiger/GENZ2020/shp/cb_2020_us_state_500k.zip",
    "https://www2.census.gov/geo/tiger/GENZ2022/shp/cb_2022_us_state_500k.zip",
]

ABBR_TO_NAME = {
    "AL": "Alabama", "AK": "Alaska", "AZ": "Arizona", "AR": "Arkansas",
    "CA": "California", "CO": "Colorado", "CT": "Connecticut", "DE": "Delaware",
    "DC": "District of Columbia", "FL": "Florida", "GA": "Georgia", "HI": "Hawaii",
    "ID": "Idaho", "IL": "Illinois", "IN": "Indiana", "IA": "Iowa", "KS": "Kansas",
    "KY": "Kentucky", "LA": "Louisiana", "ME": "Maine", "MD": "Maryland",
    "MA": "Massachusetts", "MI": "Michigan", "MN": "Minnesota", "MS": "Mississippi",
    "MO": "Missouri", "MT": "Montana", "NE": "Nebraska", "NV": "Nevada",
    "NH": "New Hampshire", "NJ": "New Jersey", "NM": "New Mexico", "NY": "New York",
    "NC": "North Carolina", "ND": "North Dakota", "OH": "Ohio", "OK": "Oklahoma",
    "OR": "Oregon", "PA": "Pennsylvania", "RI": "Rhode Island", "SC": "South Carolina",
    "SD": "South Dakota", "TN": "Tennessee", "TX": "Texas", "UT": "Utah",
    "VT": "Vermont", "VA": "Virginia", "WA": "Washington", "WV": "West Virginia",
    "WI": "Wisconsin", "WY": "Wyoming",
}
ALL_STATE_NAMES = set(ABBR_TO_NAME.values())

def _load_cfg() -> dict:
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}
    return {}

def _resolve(p: str) -> Path:
    path = Path(p)
    if path.is_absolute():
        return path
    return BACKEND_DIR / path

def _download(urls: list[str], dest_path: Path, label: str) -> None:
    if dest_path.exists():
        print(f"  {label} already cached.")
        return
    print(f"  Downloading {label} ...")
    for url in urls:
        print(f"    Trying {url}")
        resp = requests.get(url, stream=True, timeout=120)
        if resp.status_code == 200:
            with open(dest_path, "wb") as f:
                for chunk in resp.iter_content(chunk_size=1_000_000):
                    f.write(chunk)
            print("    Done.")
            return
        print(f"    HTTP {resp.status_code}, trying next ...")
    raise RuntimeError(f"Could not download {label}.")

def _extract(zip_path: Path, dest_dir: Path) -> None:
    if not dest_dir.exists():
        dest_dir.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(dest_dir)

def _find_shp(directory: Path) -> Path:
    for f in directory.iterdir():
        if f.suffix.lower() == ".shp":
            return f
    raise FileNotFoundError(f"No .shp file in {directory}")

def build(
    empty_mode: bool = False,
    state_filter: set[str] | None = None,
    cfg: dict | None = None,
) -> Path:
    cfg = cfg or _load_cfg()
    paths = cfg.get("paths", {})
    tier1_path = _resolve(
        paths.get("tier1_parquet", "data/raw/final_tier1_all_percentiles.parquet")
    )
    output_path = _resolve(paths.get("output_gpkg", "data/zcta_hospital_potential.gpkg"))

    target_states = state_filter if state_filter else ALL_STATE_NAMES
    print("=" * 60)
    print("BUILD BASE MAP — ZCTA polygons + Tier 1 parquet")
    if state_filter:
        print(f"  States: {', '.join(sorted(target_states))}")
    print("=" * 60)

    zcta_zip = DATA_DIR / "zcta_500k.zip"
    state_zip = DATA_DIR / "state_500k.zip"
    zcta_shp = DATA_DIR / "zcta_shp"
    state_shp = DATA_DIR / "state_shp"

    _download(ZCTA_URLS, zcta_zip, "ZCTA boundaries (~30 MB)")
    _download(STATE_URLS, state_zip, "State boundaries (~3 MB)")
    _extract(zcta_zip, zcta_shp)
    _extract(state_zip, state_shp)

    print("\nLoading ZCTA shapefile ...")
    gdf = gpd.read_file(_find_shp(zcta_shp))
    zip_col = None
    for col in ["ZCTA5CE20", "ZCTA5CE10", "ZCTA5CE", "GEOID20", "GEOID"]:
        if col in gdf.columns:
            zip_col = col
            break
    if not zip_col:
        raise RuntimeError(f"Cannot find ZIP column. Found: {list(gdf.columns)}")
    print(f"  ZIP column: {zip_col}  |  Total ZCTAs: {len(gdf):,}")

    print("Loading state boundaries ...")
    states_gdf = gpd.read_file(_find_shp(state_shp))
    state_name_col = None
    for col in ["NAME", "NAME20"]:
        if col in states_gdf.columns:
            state_name_col = col
            break
    if not state_name_col:
        raise RuntimeError(f"No state name column. Found: {list(states_gdf.columns)}")

    states_gdf = states_gdf[states_gdf[state_name_col].isin(target_states)].copy()

    print("Assigning states to ZCTAs (spatial join) ...")
    gdf = gdf.to_crs(epsg=4326)
    states_gdf = states_gdf.to_crs(epsg=4326)

    pts = gdf[[zip_col, "geometry"]].copy()
    pts["geometry"] = pts.geometry.representative_point()
    joined = gpd.sjoin(
        pts,
        states_gdf[[state_name_col, "geometry"]],
        how="left",
        predicate="within",
    )
    joined = joined.drop_duplicates(subset=[zip_col])
    gdf["state"] = joined.set_index(zip_col)[state_name_col].reindex(gdf[zip_col].values).values
    gdf = gdf[gdf["state"].isin(target_states)].copy()
    gdf = gdf.rename(columns={zip_col: "zipcode"})
    gdf["zipcode"] = gdf["zipcode"].astype(str).str.zfill(5)
    print(f"  ZCTAs with state assignment: {len(gdf):,}")

    print("Simplifying geometries ...")
    gdf["geometry"] = gdf.geometry.simplify(tolerance=0.005, preserve_topology=True)

    ent_cfg = cfg.get("entity_layer", {})
    gdf["entity_count"] = int(ent_cfg.get("entity_count", 0))
    gdf["hospital_count"] = int(ent_cfg.get("hospital_count", 0))
    gdf["avg_entity_score"] = float(ent_cfg.get("avg_entity_score", 0.0))
    gdf["avg_confidence"] = float(ent_cfg.get("avg_confidence", 0.0))

    if empty_mode:
        gdf["hospital_potential"] = 0.0
    elif not tier1_path.exists():
        print(f"\n  WARNING: Tier 1 parquet missing: {tier1_path}")
        gdf["hospital_potential"] = float(cfg.get("hospital_potential", {}).get("fallback", 50.0))
    else:
        print(f"\nMerging Tier 1 parquet: {tier1_path} ...")
        tier1 = pd.read_parquet(str(tier1_path))
        attrs = pd.DataFrame(gdf.drop(columns=["geometry"]))
        merged = merge_tier1_onto_gdf(attrs, tier1)
        hp_cfg = cfg.get("hospital_potential", {})
        merged["hospital_potential"] = compute_hospital_potential(merged, hp_cfg)
        merged["geometry"] = gdf.geometry.values
        gdf = gpd.GeoDataFrame(merged, geometry="geometry", crs=gdf.crs)
        print(
            f"  hospital_potential: {gdf['hospital_potential'].min():.1f} – "
            f"{gdf['hospital_potential'].max():.1f}"
        )

    if cfg.get("outputs", {}).get("write_gpkg", True):
        output_path.parent.mkdir(parents=True, exist_ok=True)
        print(f"\nSaving to {output_path} ...")
        gdf.to_file(str(output_path), driver="GPKG")

    print(f"\n{'=' * 60}")
    print(f"  Total ZCTAs: {len(gdf):,}")
    print(f"  Output: {output_path}")
    print(f"{'=' * 60}")
    return output_path

DEFAULT_STATES = ["FL", "GA", "AL"]

def main() -> None:
    cfg = _load_cfg()
    default_states = cfg.get("project", {}).get("default_states", DEFAULT_STATES)
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="+", metavar="ST", default=None)
    ap.add_argument("--empty", action="store_true", help="0 scores, skip Tier 1 merge")
    args = ap.parse_args()

    abbrs = args.states if args.states is not None else default_states
    sf = set()
    for abbr in abbrs:
        name = ABBR_TO_NAME.get(str(abbr).upper())
        if not name:
            ap.error(f"Unknown state abbreviation: {abbr}")
        sf.add(name)

    build(empty_mode=args.empty, state_filter=sf, cfg=cfg)

if __name__ == "__main__":
    main()