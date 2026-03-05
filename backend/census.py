"""
census.py
Fetch Tier 1 demographic + economic data from Census ACS 5-Year API at ZCTA level.

Requires a free Census API key: https://api.census.gov/data/key_signup.html
Set it as environment variable CENSUS_API_KEY or in .env file.

All 13 Tier 1 factors:
 1. Total population            (B01003_001E)
 2. 5-year population growth    (compare 2 vintages)
 3. Age distribution            (B01001 buckets → pct_under_18, pct_18_64, pct_65_plus)
 4. Racial/ethnic composition   (B02001 + B03003 → pct_white, pct_black, pct_hispanic, pct_asian)
 5. Median age                  (B01002_001E)
 6. Median household income     (B19013_001E)
 7. Education attainment        (B15003 → bachelors_or_higher_pct)
 8. Birth rate proxy            (B13016_001E women who had birth in past 12 months)
 9. In-migration/net flow       (B07001 → in_migration_pct)
10. GDP                         (not available at ZCTA — use income per capita as proxy)
11. Unemployment rate           (B23025 → unemployment_rate)
12. Personal income per capita  (B19301_001E)
13. Industry composition        (B24030 top sectors → top_industry)
"""

import os
import time
from pathlib import Path

import pandas as pd
import requests

def _load_env():
    env_path = Path(__file__).parent.parent / ".env"
    if env_path.exists():
        for line in env_path.read_text().splitlines():
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())

_load_env()

CENSUS_KEY = os.environ.get("CENSUS_API_KEY", "")
BASE_URL = "https://api.census.gov/data/{year}/acs/acs5"

# ACS variables we need (all from 5-year estimates)
VARIABLES = {
    # Population
    "B01003_001E": "total_population",
    # Median age
    "B01002_001E": "median_age",
    # Median household income
    "B19013_001E": "median_household_income",
    # Per capita income
    "B19301_001E": "per_capita_income",
    # Age buckets (total, under 5, 5-17, 18-64 via subtraction, 65+)
    "B01001_001E": "_age_total",
    "B01001_003E": "_male_under5",
    "B01001_004E": "_male_5_9",
    "B01001_005E": "_male_10_14",
    "B01001_006E": "_male_15_17",
    "B01001_027E": "_female_under5",
    "B01001_028E": "_female_5_9",
    "B01001_029E": "_female_10_14",
    "B01001_030E": "_female_15_17",
    "B01001_007E": "_male_18_19",
    "B01001_008E": "_male_20",
    "B01001_009E": "_male_21",
    "B01001_010E": "_male_22_24",
    "B01001_011E": "_male_25_29",
    "B01001_012E": "_male_30_34",
    "B01001_013E": "_male_35_39",
    "B01001_014E": "_male_40_44",
    "B01001_015E": "_male_45_49",
    "B01001_016E": "_male_50_54",
    "B01001_017E": "_male_55_59",
    "B01001_018E": "_male_60_61",
    "B01001_019E": "_male_62_64",
    "B01001_031E": "_female_18_19",
    "B01001_032E": "_female_20",
    "B01001_033E": "_female_21",
    "B01001_034E": "_female_22_24",
    "B01001_035E": "_female_25_29",
    "B01001_036E": "_female_30_34",
    "B01001_037E": "_female_35_39",
    "B01001_038E": "_female_40_44",
    "B01001_039E": "_female_45_49",
    "B01001_040E": "_female_50_54",
    "B01001_041E": "_female_55_59",
    "B01001_042E": "_female_60_61",
    "B01001_043E": "_female_62_64",
    "B01001_020E": "_male_65_66",
    "B01001_021E": "_male_67_69",
    "B01001_022E": "_male_70_74",
    "B01001_023E": "_male_75_79",
    "B01001_024E": "_male_80_84",
    "B01001_025E": "_male_85_plus",
    "B01001_044E": "_female_65_66",
    "B01001_045E": "_female_67_69",
    "B01001_046E": "_female_70_74",
    "B01001_047E": "_female_75_79",
    "B01001_048E": "_female_80_84",
    "B01001_049E": "_female_85_plus",
    # Race
    "B02001_001E": "_race_total",
    "B02001_002E": "_race_white",
    "B02001_003E": "_race_black",
    "B02001_005E": "_race_asian",
    # Hispanic
    "B03003_001E": "_hisp_total",
    "B03003_003E": "_hisp_yes",
    # Education (25+ population)
    "B15003_001E": "_edu_total",
    "B15003_022E": "_edu_bachelors",
    "B15003_023E": "_edu_masters",
    "B15003_024E": "_edu_professional",
    "B15003_025E": "_edu_doctorate",
    # Fertility (women 15-50 who had birth)
    "B13016_001E": "_birth_total_women",
    "B13016_002E": "_birth_had_birth",
    # Mobility (population 1 year+, moved from different state/abroad)
    "B07001_001E": "_mob_total",
    "B07001_065E": "_mob_from_diff_state",
    "B07001_081E": "_mob_from_abroad",
    # Employment
    "B23025_001E": "_emp_total_16plus",
    "B23025_005E": "_emp_unemployed",
    "B23025_002E": "_emp_in_labor_force",
}

# Industry composition (C24030 — Male workers as proxy for area industry mix)
INDUSTRY_VARS = {
    "C24030_002E": "_ind_total",
    "C24030_003E": "_ind_agriculture",
    "C24030_006E": "_ind_construction",
    "C24030_007E": "_ind_manufacturing",
    "C24030_009E": "_ind_retail",
    "C24030_014E": "_ind_finance",
    "C24030_017E": "_ind_professional",
    "C24030_021E": "_ind_education_health",
    "C24030_024E": "_ind_arts_entertainment",
    "C24030_027E": "_ind_other_services",
    "C24030_028E": "_ind_public_admin",
}

STATE_FIPS = {
    "AL": "01", "AK": "02", "AZ": "04", "AR": "05", "CA": "06",
    "CO": "08", "CT": "09", "DE": "10", "DC": "11", "FL": "12",
    "GA": "13", "HI": "15", "ID": "16", "IL": "17", "IN": "18",
    "IA": "19", "KS": "20", "KY": "21", "LA": "22", "ME": "23",
    "MD": "24", "MA": "25", "MI": "26", "MN": "27", "MS": "28",
    "MO": "29", "MT": "30", "NE": "31", "NV": "32", "NH": "33",
    "NJ": "34", "NM": "35", "NY": "36", "NC": "37", "ND": "38",
    "OH": "39", "OK": "40", "OR": "41", "PA": "42", "RI": "44",
    "SC": "45", "SD": "46", "TN": "47", "TX": "48", "UT": "49",
    "VT": "50", "VA": "51", "WA": "53", "WV": "54", "WI": "55",
    "WY": "56",
}


def _fetch_acs(year: int, variables: dict[str, str]) -> pd.DataFrame:
    """Fetch ACS variables for all ZCTAs. Returns raw DataFrame."""
    var_list = list(variables.keys())

    # Census API allows max ~50 vars per call, split if needed
    chunk_size = 48
    chunks = [var_list[i:i + chunk_size] for i in range(0, len(var_list), chunk_size)]

    dfs = []
    for chunk in chunks:
        var_str = ",".join(chunk)
        url = BASE_URL.format(year=year)
        params = {
            "get": f"NAME,{var_str}",
            "for": "zip code tabulation area:*",
        }
        if CENSUS_KEY:
            params["key"] = CENSUS_KEY

        print(f"    Fetching {len(chunk)} variables from ACS {year} ...")
        resp = requests.get(url, params=params, timeout=120)

        if resp.status_code == 204 or not resp.text.strip():
            print(f"    WARNING: Empty response for ACS {year}")
            return pd.DataFrame()

        if resp.status_code != 200:
            print(f"    WARNING: Census API returned {resp.status_code}: {resp.text[:200]}")
            return pd.DataFrame()

        data = resp.json()
        header = data[0]
        rows = data[1:]
        df = pd.DataFrame(rows, columns=header)
        dfs.append(df)
        time.sleep(0.5)

    if not dfs:
        return pd.DataFrame()

    result = dfs[0]
    for df in dfs[1:]:
        merge_on = [c for c in ["NAME", "zip code tabulation area"] if c in df.columns]
        result = result.merge(df, on=merge_on, how="outer")

    return result


def fetch_tier1_demographics(year: int = 2022, prev_year: int = 2017) -> pd.DataFrame:
    """
    Fetch all Tier 1 factors at ZCTA level. Returns a DataFrame with
    zipcode as index and all 13 demographic/economic columns.
    """
    if not CENSUS_KEY:
        print("  WARNING: CENSUS_API_KEY not set. Get a free key at:")
        print("  https://api.census.gov/data/key_signup.html")
        print("  Then add CENSUS_API_KEY=your_key to your .env file")
        return pd.DataFrame()

    print(f"\n  Fetching ACS {year} data (current) ...")
    current = _fetch_acs(year, VARIABLES)
    if current.empty:
        return pd.DataFrame()

    # Industry vars fetched separately (different table, may fail on some vintages)
    try:
        print(f"  Fetching industry composition ...")
        ind = _fetch_acs(year, INDUSTRY_VARS)
        if not ind.empty:
            zcta_key = "zip code tabulation area"
            merge_on = [c for c in [zcta_key, "NAME"] if c in ind.columns and c in current.columns]
            if merge_on:
                current = current.merge(ind, on=merge_on, how="left")
    except Exception as e:
        print(f"  WARNING: Industry fetch failed ({e}) — skipping")

    all_vars = {**VARIABLES, **INDUSTRY_VARS}

    # Fetch prior vintage for growth calculation
    print(f"  Fetching ACS {prev_year} data (for growth rate) ...")
    growth_vars = {"B01003_001E": "total_population"}
    prior = _fetch_acs(prev_year, growth_vars)

    # Normalize
    zcta_col = "zip code tabulation area"
    if zcta_col not in current.columns:
        print(f"  ERROR: No ZCTA column found. Columns: {list(current.columns)[:10]}")
        return pd.DataFrame()

    current = current.rename(columns={zcta_col: "zipcode"})
    current["zipcode"] = current["zipcode"].astype(str).str.zfill(5)

    # Convert numeric columns and rename raw codes to aliases
    for col in all_vars.keys():
        if col in current.columns:
            current[col] = pd.to_numeric(current[col], errors="coerce")
    for var_code, alias in all_vars.items():
        if alias.startswith("_") and var_code in current.columns:
            current[alias] = current[var_code]

    df = pd.DataFrame()
    df["zipcode"] = current["zipcode"]

    # 1. Total population
    df["total_population"] = current["B01003_001E"]

    # 5. Median age
    df["median_age"] = current["B01002_001E"].where(current["B01002_001E"] >= 0)

    # 6. Median household income (Census uses negative sentinels like -666666666 for suppressed data)
    df["median_household_income"] = current["B19013_001E"].where(current["B19013_001E"] >= 0)

    # 12. Per capita income
    df["per_capita_income"] = current["B19301_001E"].where(current["B19301_001E"] >= 0)

    # 3. Age distribution
    age_total = current.get("_age_total", current["B01003_001E"]).fillna(1).replace(0, 1)
    under_18 = (
        current.get("_male_under5", 0).fillna(0) + current.get("_male_5_9", 0).fillna(0) +
        current.get("_male_10_14", 0).fillna(0) + current.get("_male_15_17", 0).fillna(0) +
        current.get("_female_under5", 0).fillna(0) + current.get("_female_5_9", 0).fillna(0) +
        current.get("_female_10_14", 0).fillna(0) + current.get("_female_15_17", 0).fillna(0)
    )
    over_65 = (
        current.get("_male_65_66", 0).fillna(0) + current.get("_male_67_69", 0).fillna(0) +
        current.get("_male_70_74", 0).fillna(0) + current.get("_male_75_79", 0).fillna(0) +
        current.get("_male_80_84", 0).fillna(0) + current.get("_male_85_plus", 0).fillna(0) +
        current.get("_female_65_66", 0).fillna(0) + current.get("_female_67_69", 0).fillna(0) +
        current.get("_female_70_74", 0).fillna(0) + current.get("_female_75_79", 0).fillna(0) +
        current.get("_female_80_84", 0).fillna(0) + current.get("_female_85_plus", 0).fillna(0)
    )
    age_18_44 = (
        current.get("_male_18_19", 0).fillna(0) + current.get("_male_20", 0).fillna(0) +
        current.get("_male_21", 0).fillna(0) + current.get("_male_22_24", 0).fillna(0) +
        current.get("_male_25_29", 0).fillna(0) + current.get("_male_30_34", 0).fillna(0) +
        current.get("_male_35_39", 0).fillna(0) + current.get("_male_40_44", 0).fillna(0) +
        current.get("_female_18_19", 0).fillna(0) + current.get("_female_20", 0).fillna(0) +
        current.get("_female_21", 0).fillna(0) + current.get("_female_22_24", 0).fillna(0) +
        current.get("_female_25_29", 0).fillna(0) + current.get("_female_30_34", 0).fillna(0) +
        current.get("_female_35_39", 0).fillna(0) + current.get("_female_40_44", 0).fillna(0)
    )
    age_45_64 = (
        current.get("_male_45_49", 0).fillna(0) + current.get("_male_50_54", 0).fillna(0) +
        current.get("_male_55_59", 0).fillna(0) + current.get("_male_60_61", 0).fillna(0) +
        current.get("_male_62_64", 0).fillna(0) +
        current.get("_female_45_49", 0).fillna(0) + current.get("_female_50_54", 0).fillna(0) +
        current.get("_female_55_59", 0).fillna(0) + current.get("_female_60_61", 0).fillna(0) +
        current.get("_female_62_64", 0).fillna(0)
    )
    df["pct_under_18"] = (under_18 / age_total * 100).round(1)
    df["pct_18_44"] = (age_18_44 / age_total * 100).round(1)
    df["pct_45_64"] = (age_45_64 / age_total * 100).round(1)
    df["pct_65_plus"] = (over_65 / age_total * 100).round(1)
    df["pct_18_64"] = (100 - df["pct_under_18"] - df["pct_65_plus"]).round(1)

    # 4. Racial/ethnic composition
    race_total = current.get("_race_total", age_total).fillna(1).replace(0, 1)
    df["pct_white"] = (current.get("_race_white", 0).fillna(0) / race_total * 100).round(1)
    df["pct_black"] = (current.get("_race_black", 0).fillna(0) / race_total * 100).round(1)
    df["pct_asian"] = (current.get("_race_asian", 0).fillna(0) / race_total * 100).round(1)
    hisp_total = current.get("_hisp_total", age_total).fillna(1).replace(0, 1)
    df["pct_hispanic"] = (current.get("_hisp_yes", 0).fillna(0) / hisp_total * 100).round(1)
    df["pct_other"] = (100 - df["pct_white"] - df["pct_black"] - df["pct_asian"] - df["pct_hispanic"]).clip(lower=0).round(1)

    # 7. Education attainment
    edu_total = current.get("_edu_total", pd.Series(1)).fillna(1).replace(0, 1)
    bachelors_plus = (
        current.get("_edu_bachelors", 0).fillna(0) +
        current.get("_edu_masters", 0).fillna(0) +
        current.get("_edu_professional", 0).fillna(0) +
        current.get("_edu_doctorate", 0).fillna(0)
    )
    df["bachelors_or_higher_pct"] = (bachelors_plus / edu_total * 100).round(1)

    # 8. Birth rate proxy (women who had birth / total women 15-50)
    birth_total = current.get("_birth_total_women", pd.Series(1)).fillna(1).replace(0, 1)
    birth_had = current.get("_birth_had_birth", 0).fillna(0)
    df["birth_rate_per_1000"] = (birth_had / birth_total * 1000).round(1)

    # 9. In-migration rate
    mob_total = current.get("_mob_total", pd.Series(1)).fillna(1).replace(0, 1)
    in_mig = (
        current.get("_mob_from_diff_state", 0).fillna(0) +
        current.get("_mob_from_abroad", 0).fillna(0)
    )
    df["in_migration_pct"] = (in_mig / mob_total * 100).round(2)

    # 11. Unemployment rate
    labor_force = current.get("_emp_in_labor_force", pd.Series(1)).fillna(1).replace(0, 1)
    unemployed = current.get("_emp_unemployed", 0).fillna(0)
    df["unemployment_rate"] = (unemployed / labor_force * 100).round(1)

    # 2. Population growth (current vs prior vintage)
    if not prior.empty and zcta_col.replace("zipcode", "zip code tabulation area") in prior.columns or "zip code tabulation area" in prior.columns:
        pcol = "zip code tabulation area" if "zip code tabulation area" in prior.columns else zcta_col
        prior = prior.rename(columns={pcol: "zipcode"})
        prior["zipcode"] = prior["zipcode"].astype(str).str.zfill(5)
        prior["B01003_001E"] = pd.to_numeric(prior["B01003_001E"], errors="coerce")
        prior = prior.rename(columns={"B01003_001E": "pop_prior"})
        df = df.merge(prior[["zipcode", "pop_prior"]], on="zipcode", how="left")
        safe_prior = df["pop_prior"].fillna(1).replace(0, 1)
        df["population_growth_5yr_pct"] = (
            (df["total_population"] - df["pop_prior"]) / safe_prior * 100
        ).round(1)
        df.drop(columns=["pop_prior"], inplace=True)
    else:
        df["population_growth_5yr_pct"] = 0.0

    # 13. Top industry
    ind_cols = {v: k for k, v in INDUSTRY_VARS.items() if v != "_ind_total"}
    ind_labels = {
        "_ind_agriculture": "Agriculture",
        "_ind_construction": "Construction",
        "_ind_manufacturing": "Manufacturing",
        "_ind_retail": "Retail",
        "_ind_finance": "Finance",
        "_ind_professional": "Professional/Tech",
        "_ind_education_health": "Education & Health",
        "_ind_arts_entertainment": "Arts/Entertainment",
        "_ind_other_services": "Other Services",
        "_ind_public_admin": "Public Administration",
    }
    ind_df = pd.DataFrame()
    for alias, var_code in ind_cols.items():
        if var_code in current.columns:
            ind_df[alias] = pd.to_numeric(current[var_code], errors="coerce").fillna(0)

    if not ind_df.empty and len(ind_df.columns) > 0:
        df["top_industry"] = ind_df.idxmax(axis=1).map(ind_labels).fillna("Unknown")
    else:
        df["top_industry"] = "Unknown"

    # 10. GDP — not available at ZCTA level, use per_capita_income as proxy
    df["gdp_proxy_per_capita_income"] = df["per_capita_income"]

    # Clean up
    df = df.drop(columns=["NAME"], errors="ignore")
    df = df[df["total_population"].notna() & (df["total_population"] > 0)]

    print(f"\n  Census data: {len(df):,} ZCTAs with demographics")
    return df


def fetch_and_save(output_path: str, year: int = 2022, prev_year: int = 2017):
    """Fetch and save Census demographics to parquet."""
    df = fetch_tier1_demographics(year, prev_year)
    if df.empty:
        print("  No Census data fetched.")
        return df
    df.to_parquet(output_path, index=False)
    print(f"  Saved: {output_path}")
    return df
