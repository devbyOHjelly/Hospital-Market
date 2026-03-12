"""
build_base_map.py
Download real Census ZCTA + state boundary shapefiles, aggregate
entity pipeline output to ZIP-level metrics, and write the
zcta_hospital_potential.gpkg used by the frontend choropleth.

Usage:
    cd backend
    python build_base_map.py                # default: FL, GA, AL
    python build_base_map.py --states FL    # single state override
"""

import argparse
import os
import zipfile

import numpy as np
import pandas as pd
import geopandas as gpd
import requests

BACKEND_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
DATA_DIR = os.path.join(BACKEND_DIR, "data")
os.makedirs(DATA_DIR, exist_ok=True)

OUTPUT_PATH = os.path.join(DATA_DIR, "zcta_hospital_potential.gpkg")
ENTITIES_PATH = os.path.join(DATA_DIR, "gold", "entities.parquet")
CENSUS_PATH = os.path.join(DATA_DIR, "census_demographics.parquet")
TIER2_PATH = os.path.join(DATA_DIR, "tier2_demographics.parquet")

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


def _download(urls, dest_path, label):
    if os.path.exists(dest_path):
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
            print(f"    Done.")
            return
        print(f"    HTTP {resp.status_code}, trying next ...")
    raise RuntimeError(f"Could not download {label}.")


def _extract(zip_path, dest_dir):
    if not os.path.exists(dest_dir):
        os.makedirs(dest_dir, exist_ok=True)
        with zipfile.ZipFile(zip_path, "r") as z:
            z.extractall(dest_dir)


def _find_shp(directory):
    for f in os.listdir(directory):
        if f.endswith(".shp"):
            return os.path.join(directory, f)
    raise FileNotFoundError(f"No .shp file in {directory}")


def _rescale(arr):
    mn, mx = np.nanmin(arr), np.nanmax(arr)
    return (arr - mn) / (mx - mn) if mx > mn else np.zeros_like(arr, dtype=float)


def build(empty_mode=False, state_filter=None):
    """
    state_filter: set of full state names to include, or None for all US states.
    """
    target_states = state_filter if state_filter else ALL_STATE_NAMES
    print("=" * 60)
    print("BUILD BASE MAP — Real Census boundaries + entity scores")
    if state_filter:
        print(f"  States: {', '.join(sorted(target_states))}")
    print("=" * 60)

    zcta_zip = os.path.join(DATA_DIR, "zcta_500k.zip")
    state_zip = os.path.join(DATA_DIR, "state_500k.zip")
    zcta_shp = os.path.join(DATA_DIR, "zcta_shp")
    state_shp = os.path.join(DATA_DIR, "state_shp")

    _download(ZCTA_URLS, zcta_zip, "ZCTA boundaries (~30 MB)")
    _download(STATE_URLS, state_zip, "State boundaries (~3 MB)")
    _extract(zcta_zip, zcta_shp)
    _extract(state_zip, state_shp)

    # Load ZCTA polygons
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

    # Load state boundaries & spatial join
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
        pts, states_gdf[[state_name_col, "geometry"]],
        how="left", predicate="within",
    )
    joined = joined.drop_duplicates(subset=[zip_col])
    gdf["state"] = joined.set_index(zip_col)[state_name_col].reindex(gdf[zip_col].values).values
    gdf = gdf[gdf["state"].isin(target_states)].copy()
    gdf = gdf.rename(columns={zip_col: "zipcode"})
    gdf["zipcode"] = gdf["zipcode"].astype(str).str.zfill(5)
    print(f"  ZCTAs with state assignment: {len(gdf):,}")

    print("Simplifying geometries ...")
    gdf["geometry"] = gdf.geometry.simplify(tolerance=0.005, preserve_topology=True)

    # Aggregate entity data to ZIP level
    if not empty_mode and os.path.exists(ENTITIES_PATH):
        print(f"\nAggregating entity data from {ENTITIES_PATH} ...")
        ent = pd.read_parquet(ENTITIES_PATH)
        ent["zip"] = ent["zip"].astype(str).str.zfill(5)

        if "entity_score" not in ent.columns:
            ent["entity_score"] = 50.0
        if "resolution_confidence" not in ent.columns:
            ent["resolution_confidence"] = 0.0

        zip_agg = ent.groupby("zip").agg(
            entity_count=("entity_guid", "count"),
            avg_entity_score=("entity_score", "mean"),
            hospital_count=("entity_type", lambda x: (x == "hospital").sum()),
            avg_confidence=("resolution_confidence", "mean"),
        ).reset_index().rename(columns={"zip": "zipcode"})

        zip_agg["avg_entity_score"] = zip_agg["avg_entity_score"].round(1)
        zip_agg["avg_confidence"] = zip_agg["avg_confidence"].round(2)

        gdf = gdf.merge(zip_agg, on="zipcode", how="left")
        gdf["entity_count"] = gdf["entity_count"].fillna(0).astype(int)
        gdf["hospital_count"] = gdf["hospital_count"].fillna(0).astype(int)
        gdf["avg_entity_score"] = gdf["avg_entity_score"].fillna(0.0)
        gdf["avg_confidence"] = gdf["avg_confidence"].fillna(0.0)

        # Composite score: 60% entity density (log-scaled) + 40% avg entity score
        # Log-scale entity count so ZIPs with 1 provider still get color
        mask = gdf["entity_count"] > 0
        density = np.zeros(len(gdf), dtype=float)
        if mask.any():
            raw_counts = gdf.loc[mask, "entity_count"].values.astype(float)
            log_counts = np.log1p(raw_counts)
            mn, mx = log_counts.min(), log_counts.max()
            density[mask] = (log_counts - mn) / (mx - mn) if mx > mn else 0.5

        quality = np.zeros(len(gdf), dtype=float)
        if mask.any():
            raw_scores = gdf.loc[mask, "avg_entity_score"].values.astype(float)
            mn, mx = np.nanmin(raw_scores), np.nanmax(raw_scores)
            quality[mask] = (raw_scores - mn) / (mx - mn) if mx > mn else 0.5

        composite = 0.6 * density + 0.4 * quality
        gdf["hospital_potential"] = np.round(composite * 100, 1)

        zips_with_entities = mask.sum()
        print(f"  ZIPs with entities: {zips_with_entities:,}")
        print(f"  Total entities mapped: {gdf['entity_count'].sum():,}")
        print(f"  Hospitals mapped: {gdf['hospital_count'].sum():,}")
        print(f"  Score range: {gdf.loc[mask, 'hospital_potential'].min():.1f} – "
              f"{gdf.loc[mask, 'hospital_potential'].max():.1f}")
    else:
        if empty_mode:
            print("\n  --empty mode: creating map with zero scores")
        else:
            print(f"\n  {ENTITIES_PATH} not found — scores will be 0")
        gdf["entity_count"] = 0
        gdf["hospital_count"] = 0
        gdf["avg_entity_score"] = 0.0
        gdf["avg_confidence"] = 0.0
        gdf["hospital_potential"] = 0.0

    # Merge Census demographics if available
    if os.path.exists(CENSUS_PATH):
        print(f"\nMerging Census demographics from {CENSUS_PATH} ...")
        census = pd.read_parquet(CENSUS_PATH)
        census["zipcode"] = census["zipcode"].astype(str).str.zfill(5)
        before = len(gdf)
        gdf = gdf.merge(census, on="zipcode", how="left")
        matched = gdf["total_population"].notna().sum()
        print(f"  Census match: {matched:,}/{before:,} ZCTAs")

        # Recompute hospital_potential as composite of demographics + entity data
        has_demo = gdf["total_population"].notna() & (gdf["total_population"] > 0)
        if has_demo.any():
            demo_cols = ["total_population", "median_household_income",
                         "bachelors_or_higher_pct", "population_growth_5yr_pct",
                         "pct_65_plus", "per_capita_income", "unemployment_rate"]
            existing = [c for c in demo_cols if c in gdf.columns]
            demo_score = np.zeros(len(gdf), dtype=float)
            n_cols = 0
            for col in existing:
                vals = pd.to_numeric(gdf[col], errors="coerce").fillna(0).values.astype(float)
                mn, mx = np.nanmin(vals[has_demo]), np.nanmax(vals[has_demo])
                if mx > mn:
                    normed = np.zeros_like(vals)
                    # Unemployment: lower is better → invert
                    if col == "unemployment_rate":
                        normed[has_demo] = 1.0 - (vals[has_demo] - mn) / (mx - mn)
                    else:
                        normed[has_demo] = (vals[has_demo] - mn) / (mx - mn)
                    demo_score += normed
                    n_cols += 1
            if n_cols > 0:
                demo_score /= n_cols

            # Blend: 50% demographics, 30% entity density, 20% entity quality
            ent_mask = gdf["entity_count"] > 0
            ent_density = np.zeros(len(gdf), dtype=float)
            ent_quality = np.zeros(len(gdf), dtype=float)
            if ent_mask.any():
                log_counts = np.log1p(gdf.loc[ent_mask, "entity_count"].values.astype(float))
                emn, emx = log_counts.min(), log_counts.max()
                ent_density[ent_mask] = (log_counts - emn) / (emx - emn) if emx > emn else 0.5

                raw_q = gdf.loc[ent_mask, "avg_entity_score"].values.astype(float)
                qmn, qmx = np.nanmin(raw_q), np.nanmax(raw_q)
                ent_quality[ent_mask] = (raw_q - qmn) / (qmx - qmn) if qmx > qmn else 0.5

            gdf["hospital_potential"] = np.round(
                (0.50 * demo_score + 0.30 * ent_density + 0.20 * ent_quality) * 100, 1
            )
            print(f"  Composite score (demo+entity): {gdf['hospital_potential'].min():.1f} – "
                  f"{gdf['hospital_potential'].max():.1f}")
    else:
        print(f"\n  {CENSUS_PATH} not found — using entity-only scoring")

    # Merge Tier 2 demographics if available
    if os.path.exists(TIER2_PATH):
        print(f"\nMerging Tier 2 demographics from {TIER2_PATH} ...")
        tier2 = pd.read_parquet(TIER2_PATH)
        tier2["zip"] = tier2["zip"].astype(str).str.zfill(5)
        tier2 = tier2.rename(columns={"zip": "zipcode"})
        before = len(gdf)
        gdf = gdf.merge(tier2, on="zipcode", how="left")
        matched = gdf[[c for c in tier2.columns if c != "zipcode"][0]].notna().sum() if len(tier2.columns) > 1 else 0
        print(f"  Tier 2 match: {matched:,}/{before:,} ZCTAs")
    else:
        print(f"\n  {TIER2_PATH} not found — Tier 2 columns will be absent")

    # Keep only needed columns
    demo_keep = [
        "total_population", "population_growth_5yr_pct", "median_age",
        "median_household_income", "per_capita_income", "bachelors_or_higher_pct",
        "pct_under_18", "pct_18_44", "pct_45_64", "pct_18_64", "pct_65_plus",
        "pct_white", "pct_black", "pct_asian", "pct_hispanic",
        "unemployment_rate", "birth_rate_per_1000", "in_migration_pct",
        "top_industry",
    ]
    tier2_keep = [
        "pcp_count", "specialist_count", "pcp_per_100k", "specialist_per_100k",
        "facility_hospital", "facility_asc", "facility_lab", "facility_imaging",
        "facility_urgent_care", "facility_snf", "facility_home_health",
        "facility_total",
        "total_beds", "total_discharges", "bed_utilization_rate",
        "inpatient_beds_per_100k", "inpatient_discharges_per_100k",
        "operating_margin_pct", "net_patient_revenue", "total_operating_expenses",
        "bene_count", "medicare_beneficiary_penetration_pct", "ma_penetration",
        "er_visits_per_1k", "ed_visits_per_100k", "ip_stays_per_1k",
        "uninsured_rate",
        "medicaid_pct", "outpatient_visits_per_1k", "hhi_market_concentration",
    ]
    keep = [
        "zipcode", "state", "entity_count", "hospital_count",
        "avg_entity_score", "avg_confidence", "hospital_potential",
    ] + demo_keep + tier2_keep + ["geometry"]
    gdf = gdf[[c for c in keep if c in gdf.columns]]

    print(f"\nSaving to {OUTPUT_PATH} ...")
    gdf.to_file(OUTPUT_PATH, driver="GPKG")

    print(f"\n{'=' * 60}")
    print(f"  Total ZCTAs: {len(gdf):,}")
    states_with_data = gdf[gdf["entity_count"] > 0]["state"].nunique()
    print(f"  States with entity data: {states_with_data}")
    print(f"  Score range: {gdf['hospital_potential'].min():.1f} – "
          f"{gdf['hospital_potential'].max():.1f}")
    print(f"  Output: {OUTPUT_PATH}")
    print(f"{'=' * 60}")


DEFAULT_STATES = ["FL", "GA", "AL"]

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--states", nargs="+", metavar="ST", default=None,
                    help="State abbreviations (default: FL GA AL)")
    ap.add_argument("--empty", action="store_true",
                    help="Create base map with 0 scores (no entities needed)")
    args = ap.parse_args()

    abbrs = args.states if args.states is not None else DEFAULT_STATES
    sf = set()
    for abbr in abbrs:
        name = ABBR_TO_NAME.get(abbr.upper())
        if not name:
            ap.error(f"Unknown state abbreviation: {abbr}")
        sf.add(name)

    build(empty_mode=args.empty, state_filter=sf)
