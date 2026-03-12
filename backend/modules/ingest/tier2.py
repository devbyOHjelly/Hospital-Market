"""
tier2.py
Fetch and compute Tier 2 market factors from free public APIs and existing
NPPES data.  All results are aggregated to the ZIP level.

Sources:
    1. NPPES entities (already ingested) → physician supply, facility counts
    2. CMS Hospital Cost Report API      → beds, discharges, utilization, financials
    3. CMS Medicare Geographic Variation  → beneficiary count, MA penetration, ED visits
    4. Census SAHIE API                   → uninsured rate (county → ZIP via crosswalk)
    5. Census ACS B27010                  → Medicaid / public coverage penetration
    6. CMS Outpatient Provider Data       → hospital outpatient visits
    7. Computed HHI                       → market concentration from hospital ownership
"""

from __future__ import annotations
import os
import time
from pathlib import Path

import numpy as np
import pandas as pd
import requests
from io import StringIO

# ---------------------------------------------------------------------------
# Taxonomy prefixes for physician classification
# ---------------------------------------------------------------------------

PRIMARY_CARE_PREFIXES = [
    '207Q',       # Family Medicine
    '208D',       # General Practice
    '2080',       # Pediatrics (base)
]
PRIMARY_CARE_EXACT = [
    '207R00000X',  # Internal Medicine (general only — NOT subspecialties)
]

FACILITY_TAXONOMY = {
    '282N': 'hospital',
    '261Q': 'asc',
    '291U': 'lab',
    '261QR': 'imaging',
    '261QU': 'urgent_care',
    '314': 'snf',
    '251E': 'home_health',
}


def _load_env():
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


_load_env()

CENSUS_KEY = os.environ.get("CENSUS_API_KEY", "")


# ---------------------------------------------------------------------------
# 1. NPPES-derived metrics (physician supply + facility counts)
# ---------------------------------------------------------------------------

def compute_nppes_supply(
    entities: pd.DataFrame,
    census_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """Count physicians and facilities per ZIP from NPPES entities."""
    df = entities.copy()
    df["zip"] = df["zip"].astype(str).str.zfill(5)

    tax_col = None
    for candidate in ["taxonomy_code", "taxonomy"]:
        if candidate in df.columns:
            tax_col = candidate
            break
    tax = df[tax_col].fillna("") if tax_col else pd.Series("", index=df.index)

    et_col = None
    for candidate in ["entity_type_code", "entity_type"]:
        if candidate in df.columns:
            et_col = candidate
            break
    et = df[et_col].astype(str) if et_col else pd.Series("", index=df.index)
    is_individual = (et == "1") | (et.str.lower() == "individual")

    is_pcp = pd.Series(False, index=df.index)
    for prefix in PRIMARY_CARE_PREFIXES:
        is_pcp |= tax.str.startswith(prefix)
    for exact in PRIMARY_CARE_EXACT:
        is_pcp |= (tax == exact)
    is_pcp &= is_individual

    is_specialist = is_individual & ~is_pcp & tax.str.startswith("20")

    pcp_counts = df.loc[is_pcp].groupby("zip").size().rename("pcp_count")
    spec_counts = df.loc[is_specialist].groupby("zip").size().rename("specialist_count")

    facility_counts = {}
    for prefix, label in FACILITY_TAXONOMY.items():
        mask = tax.str.startswith(prefix)
        if mask.any():
            facility_counts[f"facility_{label}"] = df.loc[mask].groupby("zip").size()

    result = pd.DataFrame(index=pcp_counts.index.union(spec_counts.index))
    result["pcp_count"] = pcp_counts
    result["specialist_count"] = spec_counts
    for col, series in facility_counts.items():
        result[col] = series
    result = result.fillna(0).astype(int).reset_index().rename(columns={"index": "zip"})
    if result.columns[0] != "zip":
        result = result.rename(columns={result.columns[0]: "zip"})

    if census_df is not None and not census_df.empty:
        pop = census_df[["zipcode", "total_population"]].copy()
        pop["zipcode"] = pop["zipcode"].astype(str).str.zfill(5)
        pop["total_population"] = pd.to_numeric(pop["total_population"], errors="coerce")
        result = result.merge(pop, left_on="zip", right_on="zipcode", how="left")
        result.drop(columns=["zipcode"], errors="ignore", inplace=True)
        safe_pop = result["total_population"].replace(0, np.nan)
        result["pcp_per_100k"] = np.round(result["pcp_count"] / safe_pop * 100_000, 1)
        result["specialist_per_100k"] = np.round(result["specialist_count"] / safe_pop * 100_000, 1)
        result.drop(columns=["total_population"], inplace=True)
    else:
        result["pcp_per_100k"] = np.nan
        result["specialist_per_100k"] = np.nan

    facility_type_cols = [c for c in result.columns if c.startswith("facility_")]
    result["facility_total"] = result[facility_type_cols].sum(axis=1) if facility_type_cols else 0

    return result


# ---------------------------------------------------------------------------
# 2. CMS Hospital Cost Report
# ---------------------------------------------------------------------------

_COST_REPORT_UUID = "44060663-47d8-4ced-a115-b53b4c270acb"


def fetch_cms_cost_report(cache_path: str | None = None) -> pd.DataFrame:
    """Fetch CMS Hospital Provider Cost Report data."""
    if cache_path and os.path.exists(cache_path):
        print(f"  Cost report: loaded cache ({cache_path})")
        return pd.read_parquet(cache_path)

    print("  Fetching CMS Hospital Cost Report ...")
    url = f"https://data.cms.gov/data-api/v1/dataset/{_COST_REPORT_UUID}/data"
    frames = []
    offset = 0
    page_size = 500

    while True:
        try:
            resp = requests.get(
                url, params={"offset": offset, "size": page_size}, timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  WARNING: Cost report fetch failed at offset {offset} — {e}")
            break

        if not data:
            break
        frames.append(pd.DataFrame(data))
        print(f"    ... fetched {offset + len(data):,} rows")
        offset += page_size
        if len(data) < page_size:
            break
        time.sleep(0.3)

    if not frames:
        print("  WARNING: No cost report data retrieved")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    print(f"  Cost report: {len(df):,} rows")

    col_map = {}
    for col in df.columns:
        cl = col.lower().strip().replace(" ", "_")
        col_map[col] = cl
    df.rename(columns=col_map, inplace=True)

    want = {
        "provider_ccn": None, "hospital_name": None, "state_code": None,
        "zip_code": None, "total_beds": None, "total_discharges": None,
        "total_days": None, "net_patient_revenue": None,
        "total_operating_expenses": None,
    }
    for key in list(want.keys()):
        for c in df.columns:
            if key in c or c in key:
                want[key] = c
                break

    available = {k: v for k, v in want.items() if v is not None}
    if not available:
        print(f"  WARNING: Could not map cost report columns. Found: {list(df.columns)[:20]}")
        return pd.DataFrame()

    out = pd.DataFrame()
    for logical, actual in available.items():
        out[logical] = df[actual]

    for col in ["total_beds", "total_discharges", "total_days",
                "net_patient_revenue", "total_operating_expenses"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if "zip_code" in out.columns:
        out["zip_code"] = out["zip_code"].astype(str).str[:5].str.zfill(5)

    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(cache_path, index=False)
        print(f"  Cached: {cache_path}")

    return out


def _aggregate_cost_report_to_zip(cost: pd.DataFrame) -> pd.DataFrame:
    """Aggregate hospital cost report data to ZIP level."""
    if cost.empty or "zip_code" not in cost.columns:
        return pd.DataFrame(columns=["zip"])

    g = cost.groupby("zip_code").agg(
        total_beds=("total_beds", "sum") if "total_beds" in cost.columns else ("zip_code", "size"),
        total_discharges=("total_discharges", "sum") if "total_discharges" in cost.columns else ("zip_code", "size"),
        total_days=("total_days", "sum") if "total_days" in cost.columns else ("zip_code", "size"),
        net_patient_revenue=("net_patient_revenue", "sum") if "net_patient_revenue" in cost.columns else ("zip_code", "size"),
        total_operating_expenses=("total_operating_expenses", "sum") if "total_operating_expenses" in cost.columns else ("zip_code", "size"),
    ).reset_index().rename(columns={"zip_code": "zip"})

    if "total_beds" in g.columns and "total_days" in g.columns:
        safe_beds = g["total_beds"].replace(0, np.nan)
        g["bed_utilization_rate"] = np.round(g["total_days"] / (safe_beds * 365) * 100, 1)

    if "net_patient_revenue" in g.columns and "total_operating_expenses" in g.columns:
        safe_rev = g["net_patient_revenue"].replace(0, np.nan)
        g["operating_margin_pct"] = np.round(
            (g["net_patient_revenue"] - g["total_operating_expenses"]) / safe_rev * 100, 1
        )

    return g


# ---------------------------------------------------------------------------
# 3. CMS Medicare Geographic Variation (county-level)
# ---------------------------------------------------------------------------

def fetch_medicare_geo_variation(cache_path: str | None = None) -> pd.DataFrame:
    """Fetch county-level Medicare Geographic Variation data from CMS."""
    if cache_path and os.path.exists(cache_path):
        print(f"  Medicare Geo: loaded cache ({cache_path})")
        return pd.read_parquet(cache_path)

    print("  Fetching CMS Medicare Geographic Variation (county) ...")
    url = (
        "https://data.cms.gov/data-api/v1/dataset/"
        "3588f13a-be3f-4e09-8e70-1dafa2e6fa44/data"
    )

    frames = []
    offset = 0
    page_size = 500

    while True:
        try:
            resp = requests.get(
                url, params={"offset": offset, "size": page_size}, timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  WARNING: Medicare Geo fetch failed at offset {offset} — {e}")
            break

        if not data:
            break
        frames.append(pd.DataFrame(data))
        print(f"    ... fetched {offset + len(data):,} rows")
        offset += page_size
        if len(data) < page_size:
            break
        time.sleep(0.3)

    if not frames:
        print("  WARNING: No Medicare Geo data retrieved")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    print(f"  Medicare Geo: {len(df):,} rows")

    col_map = {}
    for col in df.columns:
        col_map[col] = col.lower().strip().replace(" ", "_")
    df.rename(columns=col_map, inplace=True)

    out = pd.DataFrame()
    field_map = {
        "county_fips": ["fips", "county_fips", "bene_county_code", "state_and_county_fips_code"],
        "bene_count": ["bene_count", "total_beneficiaries", "beneficiaries_with_part_a_and_part_b",
                       "tot_benes"],
        "ma_penetration": ["ma_participation_rate", "ma_penetration",
                           "ma_prtcptn_rate", "percent_of_beneficiaries_in_ma"],
        "er_visits_per_1k": ["er_visits_per_1000_benes", "er_visits_per_1000",
                             "er_visits_per_1,000_beneficiaries"],
        "ip_stays_per_1k": ["ip_cvrd_stays_per_1000_benes", "ip_stays_per_1000",
                            "acute_hospital_readmission_rate"],
    }

    for logical, candidates in field_map.items():
        for c in candidates:
            if c in df.columns:
                out[logical] = df[c]
                break

    for col in ["bene_count", "ma_penetration", "er_visits_per_1k", "ip_stays_per_1k"]:
        if col in out.columns:
            out[col] = pd.to_numeric(out[col], errors="coerce")

    if "county_fips" in out.columns:
        out["county_fips"] = out["county_fips"].astype(str).str.zfill(5)

    county_only = out[out["county_fips"].str.len() == 5].copy() if "county_fips" in out.columns else out
    county_only = county_only.drop_duplicates(subset=["county_fips"]) if "county_fips" in county_only.columns else county_only

    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        county_only.to_parquet(cache_path, index=False)
        print(f"  Cached: {cache_path}")

    return county_only


# ---------------------------------------------------------------------------
# 4. Census SAHIE — Uninsured rate (county-level)
# ---------------------------------------------------------------------------

def fetch_sahie_uninsured(
    api_key: str = "",
    year: int = 2022,
    cache_path: str | None = None,
) -> pd.DataFrame:
    """Fetch county-level uninsured rate from Census SAHIE API."""
    if cache_path and os.path.exists(cache_path):
        print(f"  SAHIE: loaded cache ({cache_path})")
        return pd.read_parquet(cache_path)

    key = api_key or CENSUS_KEY
    if not key:
        print("  SKIP: SAHIE — no Census API key")
        return pd.DataFrame()

    print(f"  Fetching SAHIE uninsured rate ({year}) ...")
    url = (
        f"https://api.census.gov/data/timeseries/healthins/sahie"
        f"?get=PCTUI_PT,NUI_PT,NIC_PT"
        f"&for=county:*"
        f"&time={year}"
        f"&AGECAT=0&RACECAT=0&SEXCAT=0&IPRCAT=0"
        f"&key={key}"
    )

    try:
        resp = requests.get(url, timeout=60)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  WARNING: SAHIE fetch failed — {e}")
        return pd.DataFrame()

    if len(data) < 2:
        print("  WARNING: SAHIE returned no data")
        return pd.DataFrame()

    df = pd.DataFrame(data[1:], columns=data[0])
    df["county_fips"] = df["state"].str.zfill(2) + df["county"].str.zfill(3)
    df["uninsured_rate"] = pd.to_numeric(df["PCTUI_PT"], errors="coerce")

    out = df[["county_fips", "uninsured_rate"]].dropna(subset=["uninsured_rate"]).copy()
    print(f"  SAHIE: {len(out):,} counties")

    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(cache_path, index=False)
        print(f"  Cached: {cache_path}")

    return out


# ---------------------------------------------------------------------------
# 5. Census ACS — Medicaid / public coverage (ZCTA-level)
# ---------------------------------------------------------------------------

_MEDICAID_VARS = {
    "C27007_001E": "_total",         # total civilian noninstitutionalized pop
    "C27007_003E": "_u19_medicaid",  # under 19, with Medicaid/means-tested
    "C27007_006E": "_1964_medicaid", # 19-64, with Medicaid/means-tested
    "C27007_009E": "_65p_medicaid",  # 65+, with Medicaid/means-tested
}


def fetch_acs_medicaid(
    api_key: str = "",
    year: int = 2022,
    cache_path: str | None = None,
) -> pd.DataFrame:
    """Fetch ZCTA-level Medicaid / public coverage from Census ACS C27007."""
    if cache_path and os.path.exists(cache_path):
        print(f"  ACS Medicaid: loaded cache ({cache_path})")
        return pd.read_parquet(cache_path)

    key = api_key or CENSUS_KEY
    if not key:
        print("  SKIP: ACS Medicaid — no Census API key")
        return pd.DataFrame()

    print(f"  Fetching ACS Medicaid coverage ({year}) ...")
    var_str = ",".join(_MEDICAID_VARS.keys())
    url = (
        f"https://api.census.gov/data/{year}/acs/acs5"
        f"?get={var_str}"
        f"&for=zip%20code%20tabulation%20area:*"
        f"&key={key}"
    )

    try:
        resp = requests.get(url, timeout=120)
        resp.raise_for_status()
        data = resp.json()
    except Exception as e:
        print(f"  WARNING: ACS Medicaid fetch failed — {e}")
        return pd.DataFrame()

    if len(data) < 2:
        print("  WARNING: ACS Medicaid returned no rows")
        return pd.DataFrame()

    df = pd.DataFrame(data[1:], columns=data[0])
    rename = {k: v for k, v in _MEDICAID_VARS.items()}
    df.rename(columns=rename, inplace=True)

    zcta_col = [c for c in df.columns if "zip" in c.lower() or "zcta" in c.lower()]
    if zcta_col:
        df["zip"] = df[zcta_col[0]].astype(str).str.zfill(5)
    else:
        print(f"  WARNING: No ZCTA column found. Cols: {list(df.columns)}")
        return pd.DataFrame()

    for col in _MEDICAID_VARS.values():
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce")

    total = df["_total"].replace(0, np.nan)
    medicaid_count = (
        df["_u19_medicaid"].fillna(0)
        + df["_1964_medicaid"].fillna(0)
        + df["_65p_medicaid"].fillna(0)
    )
    df["medicaid_pct"] = np.round(medicaid_count / total * 100, 1)

    out = df[["zip", "medicaid_pct"]].dropna(subset=["medicaid_pct"]).copy()
    print(f"  ACS Medicaid: {len(out):,} ZCTAs")

    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        out.to_parquet(cache_path, index=False)
        print(f"  Cached: {cache_path}")

    return out


# ---------------------------------------------------------------------------
# 6. CMS Outpatient — Hospital outpatient visits (hospital-level → ZIP agg)
# ---------------------------------------------------------------------------

_OUTPATIENT_UUID = "4e40fce0-92c7-4e3e-80a0-a6e3cb7f4998"


def fetch_cms_outpatient(cache_path: str | None = None) -> pd.DataFrame:
    """Fetch CMS Hospital Outpatient data and aggregate to ZIP level."""
    if cache_path and os.path.exists(cache_path):
        print(f"  Outpatient: loaded cache ({cache_path})")
        return pd.read_parquet(cache_path)

    print("  Fetching CMS Outpatient Provider data ...")
    url = f"https://data.cms.gov/data-api/v1/dataset/{_OUTPATIENT_UUID}/data"
    frames = []
    offset = 0
    page_size = 500

    while True:
        try:
            resp = requests.get(
                url, params={"offset": offset, "size": page_size}, timeout=60
            )
            resp.raise_for_status()
            data = resp.json()
        except Exception as e:
            print(f"  WARNING: Outpatient fetch failed at offset {offset} — {e}")
            break

        if not data:
            break
        frames.append(pd.DataFrame(data))
        offset += page_size
        if len(data) < page_size:
            break
        time.sleep(0.3)

    if not frames:
        print("  WARNING: No outpatient data retrieved")
        return pd.DataFrame()

    df = pd.concat(frames, ignore_index=True)
    col_map = {c: c.lower().strip().replace(" ", "_") for c in df.columns}
    df.rename(columns=col_map, inplace=True)

    zip_col = None
    for c in df.columns:
        if "zip" in c:
            zip_col = c
            break

    visit_col = None
    for c in df.columns:
        if any(kw in c for kw in ["outpatient", "services", "claims", "visits", "total"]):
            visit_col = c
            break

    if not zip_col:
        print(f"  WARNING: No ZIP column in outpatient data. Cols: {list(df.columns)[:20]}")
        return pd.DataFrame()

    df["_zip"] = df[zip_col].astype(str).str[:5].str.zfill(5)

    if visit_col:
        df["_visits"] = pd.to_numeric(df[visit_col], errors="coerce").fillna(0)
        agg = df.groupby("_zip")["_visits"].sum().reset_index()
        agg.columns = ["zip", "outpatient_visits"]
    else:
        agg = df.groupby("_zip").size().reset_index(name="outpatient_visits")

    print(f"  Outpatient: {len(agg):,} ZIPs")

    if cache_path:
        Path(cache_path).parent.mkdir(parents=True, exist_ok=True)
        agg.to_parquet(cache_path, index=False)
        print(f"  Cached: {cache_path}")

    return agg


def _compute_outpatient_per_1k(
    outpatient: pd.DataFrame,
    census_df: pd.DataFrame | None,
) -> pd.DataFrame:
    """Convert raw outpatient counts to per-1,000 population."""
    if outpatient.empty or "zip" not in outpatient.columns:
        return pd.DataFrame(columns=["zip", "outpatient_visits_per_1k"])

    result = outpatient.copy()
    if census_df is not None and not census_df.empty:
        pop = census_df[["zipcode", "total_population"]].copy()
        pop["zipcode"] = pop["zipcode"].astype(str).str.zfill(5)
        pop["total_population"] = pd.to_numeric(pop["total_population"], errors="coerce")
        result = result.merge(pop, left_on="zip", right_on="zipcode", how="left")
        result.drop(columns=["zipcode"], errors="ignore", inplace=True)
        safe_pop = result["total_population"].replace(0, np.nan)
        result["outpatient_visits_per_1k"] = np.round(
            result["outpatient_visits"] / safe_pop * 1000, 1
        )
        result.drop(columns=["total_population"], inplace=True)
    else:
        result["outpatient_visits_per_1k"] = np.nan

    return result[["zip", "outpatient_visits_per_1k"]].dropna(subset=["outpatient_visits_per_1k"])


# ---------------------------------------------------------------------------
# 7. Market Concentration (HHI) — computed from entity ownership data
# ---------------------------------------------------------------------------

def compute_market_hhi(entities: pd.DataFrame) -> pd.DataFrame:
    """
    Compute a Herfindahl-Hirschman Index (HHI) per ZIP from hospital ownership.
    HHI ranges 0-10000: <1500 = competitive, 1500-2500 = moderate, >2500 = concentrated.
    """
    df = entities.copy()
    df["zip"] = df["zip"].astype(str).str.zfill(5)

    if "ownership" not in df.columns:
        print("  SKIP: HHI — no ownership column")
        return pd.DataFrame(columns=["zip", "hhi_market_concentration"])

    if "entity_type" in df.columns:
        hosp = df[df["entity_type"] == "hospital"].copy()
    else:
        hosp = pd.DataFrame()
    if hosp.empty:
        hosp = df.copy()

    hosp["_own_group"] = hosp["ownership"].fillna("Unknown").str.strip().str.lower()

    def _zip_hhi(group):
        counts = group["_own_group"].value_counts()
        total = counts.sum()
        if total == 0:
            return np.nan
        shares = (counts / total * 100) ** 2
        return shares.sum()

    hhi = hosp.groupby("zip").apply(_zip_hhi, include_groups=False).reset_index(name="hhi_market_concentration")
    hhi["hhi_market_concentration"] = np.round(hhi["hhi_market_concentration"], 0)
    print(f"  HHI: {len(hhi):,} ZIPs")
    return hhi


# ---------------------------------------------------------------------------
# 8. Orchestrator
# ---------------------------------------------------------------------------

def _join_county_to_zip(
    county_df: pd.DataFrame,
    crosswalk: pd.DataFrame,
) -> pd.DataFrame:
    """Broadcast county-level data to ZIP codes via the crosswalk."""
    if county_df.empty or "county_fips" not in county_df.columns:
        return pd.DataFrame()
    xw = crosswalk[["zip", "county_fips"]].drop_duplicates("zip")
    return xw.merge(county_df, on="county_fips", how="left").drop(columns=["county_fips"])


def build_tier2_demographics(
    entities: pd.DataFrame,
    census_df: pd.DataFrame | None,
    crosswalk: pd.DataFrame | None,
    cfg: dict | None = None,
) -> pd.DataFrame:
    """
    Build a ZIP-level Tier 2 demographics DataFrame from all available sources.
    Returns a DataFrame with 'zip' as key and all Tier 2 metric columns.
    """
    cfg = cfg or {}
    t2_cfg = cfg.get("tier2_sources", {})

    data_dir = Path(__file__).parent / "data"

    def _cache(section: str, default: str) -> str | None:
        sec = t2_cfg.get(section, {})
        if not sec.get("enabled", True):
            return None
        p = sec.get("cache_file", default)
        if p:
            full = Path(__file__).parent / p if not Path(p).is_absolute() else Path(p)
            return str(full)
        return str(data_dir / "raw" / "reference" / default)

    print("\n  --- Tier 2: NPPES physician supply ---")
    nppes_metrics = compute_nppes_supply(entities, census_df)
    print(f"  NPPES metrics: {len(nppes_metrics):,} ZIPs")

    print("\n  --- Tier 2: CMS Cost Report ---")
    cost_cache = _cache("cms_cost_report", "cms_cost_report.parquet")
    cost_raw = pd.DataFrame()
    if cost_cache:
        try:
            cost_raw = fetch_cms_cost_report(cache_path=cost_cache)
        except Exception as e:
            print(f"  WARNING: Cost report failed — {e}")
    cost_zip = _aggregate_cost_report_to_zip(cost_raw)
    print(f"  Cost report ZIPs: {len(cost_zip):,}")

    print("\n  --- Tier 2: Medicare Geographic Variation ---")
    med_cache = _cache("medicare_geo_variation", "medicare_geo_variation.parquet")
    med_county = pd.DataFrame()
    if med_cache:
        try:
            med_county = fetch_medicare_geo_variation(cache_path=med_cache)
        except Exception as e:
            print(f"  WARNING: Medicare Geo failed — {e}")
    med_zip = pd.DataFrame()
    if crosswalk is not None and not med_county.empty:
        med_zip = _join_county_to_zip(med_county, crosswalk)
        print(f"  Medicare Geo ZIPs: {len(med_zip):,}")

    print("\n  --- Tier 2: SAHIE uninsured rate ---")
    sahie_cache = _cache("sahie", "sahie_uninsured.parquet")
    sahie_county = pd.DataFrame()
    if sahie_cache:
        try:
            sahie_county = fetch_sahie_uninsured(cache_path=sahie_cache)
        except Exception as e:
            print(f"  WARNING: SAHIE failed — {e}")
    sahie_zip = pd.DataFrame()
    if crosswalk is not None and not sahie_county.empty:
        sahie_zip = _join_county_to_zip(sahie_county, crosswalk)
        print(f"  SAHIE ZIPs: {len(sahie_zip):,}")

    # 5. Medicaid coverage from ACS
    print("\n  --- Tier 2: ACS Medicaid / Public Coverage ---")
    medicaid_cache = _cache("acs_medicaid", "acs_medicaid.parquet")
    medicaid_df = pd.DataFrame()
    if medicaid_cache:
        try:
            medicaid_df = fetch_acs_medicaid(cache_path=medicaid_cache)
        except Exception as e:
            print(f"  WARNING: ACS Medicaid failed — {e}")

    # 6. CMS Outpatient data
    print("\n  --- Tier 2: CMS Outpatient ---")
    outpatient_cache = _cache("cms_outpatient", "cms_outpatient.parquet")
    outpatient_raw = pd.DataFrame()
    if outpatient_cache:
        try:
            outpatient_raw = fetch_cms_outpatient(cache_path=outpatient_cache)
        except Exception as e:
            print(f"  WARNING: CMS Outpatient failed — {e}")
    outpatient_zip = pd.DataFrame()
    if not outpatient_raw.empty:
        outpatient_zip = _compute_outpatient_per_1k(outpatient_raw, census_df)
        print(f"  Outpatient ZIPs: {len(outpatient_zip):,}")

    # 7. HHI market concentration
    print("\n  --- Tier 2: Market Concentration (HHI) ---")
    hhi_df = compute_market_hhi(entities)

    # Merge everything on ZIP
    result = nppes_metrics.copy()
    if not cost_zip.empty and "zip" in cost_zip.columns:
        result = result.merge(cost_zip, on="zip", how="outer")
    if not med_zip.empty and "zip" in med_zip.columns:
        result = result.merge(med_zip, on="zip", how="outer")
    if not sahie_zip.empty and "zip" in sahie_zip.columns:
        result = result.merge(sahie_zip, on="zip", how="outer")
    if not medicaid_df.empty and "zip" in medicaid_df.columns:
        result = result.merge(medicaid_df, on="zip", how="outer")
    if not outpatient_zip.empty and "zip" in outpatient_zip.columns:
        result = result.merge(outpatient_zip, on="zip", how="outer")
    if not hhi_df.empty and "zip" in hhi_df.columns:
        result = result.merge(hhi_df, on="zip", how="outer")

    result["zip"] = result["zip"].astype(str).str.zfill(5)

    # Derive normalized metrics (per-100K and penetration %) from existing API fields.
    if census_df is not None and not census_df.empty:
        pop = census_df[["zipcode", "total_population"]].copy()
        pop["zipcode"] = pop["zipcode"].astype(str).str.zfill(5)
        pop["total_population"] = pd.to_numeric(pop["total_population"], errors="coerce")
        result = result.merge(pop, left_on="zip", right_on="zipcode", how="left")
        result.drop(columns=["zipcode"], inplace=True, errors="ignore")

        safe_pop = result["total_population"].replace(0, np.nan)
        if "total_beds" in result.columns:
            result["inpatient_beds_per_100k"] = np.round(
                pd.to_numeric(result["total_beds"], errors="coerce") / safe_pop * 100_000, 1
            )
        if "total_discharges" in result.columns:
            result["inpatient_discharges_per_100k"] = np.round(
                pd.to_numeric(result["total_discharges"], errors="coerce") / safe_pop * 100_000, 1
            )
        if "bene_count" in result.columns:
            result["medicare_beneficiary_penetration_pct"] = np.round(
                pd.to_numeric(result["bene_count"], errors="coerce") / safe_pop * 100, 2
            )
        if "er_visits_per_1k" in result.columns and "bene_count" in result.columns:
            # Medicare ED visits are reported per 1K beneficiaries; convert to estimated visits
            # then normalize by total ZIP population for a per-100K market view.
            est_ed_visits = (
                pd.to_numeric(result["er_visits_per_1k"], errors="coerce")
                * pd.to_numeric(result["bene_count"], errors="coerce")
                / 1000.0
            )
            result["ed_visits_per_100k"] = np.round(est_ed_visits / safe_pop * 100_000, 1)

    # Cache the merged result
    tier2_path = data_dir / "tier2_demographics.parquet"
    tier2_path.parent.mkdir(parents=True, exist_ok=True)
    result.to_parquet(str(tier2_path), index=False)
    print(f"\n  Tier 2 saved: {tier2_path} ({len(result):,} ZIPs, {len(result.columns)} columns)")
    print(f"  Columns: {list(result.columns)}")

    return result