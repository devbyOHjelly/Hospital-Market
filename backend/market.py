"""
market.py
Geographic enrichment (ZIP→County→CBSA) and market view filtering.
"""

from __future__ import annotations
from pathlib import Path
import pandas as pd


# ---------------------------------------------------------------------------
# ZIP → County
# ---------------------------------------------------------------------------

def load_zip_county_crosswalk(path: str) -> pd.DataFrame:
    """Read zcta_county_crosswalk.csv and return a clean (zip, county_fips) frame."""
    df = pd.read_csv(path, dtype=str)
    cols = {c.lower(): c for c in df.columns}

    zip_col = None
    for cand in ['zip', 'zip_code', 'zcta', 'zcta5']:
        if cand in cols:
            zip_col = cols[cand]
            break
    county_col = None
    for cand in ['county_fips', 'county', 'geoid', 'fips']:
        if cand in cols:
            county_col = cols[cand]
            break

    if zip_col is None or county_col is None:
        raise ValueError(
            f'Cannot find ZIP/county columns in crosswalk. Found: {list(df.columns)}'
        )

    out = df[[zip_col, county_col]].copy()
    out.columns = ['zip', 'county_fips']
    out['zip'] = out['zip'].str.strip().str.zfill(5)
    out['county_fips'] = out['county_fips'].str.strip().str.zfill(5)

    weight_cols = [c for c in df.columns
                   if c.lower() in ('res_ratio', 'tot_ratio', 'bus_ratio', 'weight', 'ratio')]
    if weight_cols:
        out['_w'] = pd.to_numeric(df[weight_cols[0]], errors='coerce')
        out = out.sort_values(['zip', '_w'], ascending=[True, False]).drop_duplicates('zip')
        out.drop(columns='_w', inplace=True)
    else:
        out = out.drop_duplicates('zip')

    return out.reset_index(drop=True)


def apply_zip_to_county(entities: pd.DataFrame, crosswalk: pd.DataFrame) -> pd.DataFrame:
    """Merge county_fips onto entities via ZIP."""
    return entities.merge(crosswalk, on='zip', how='left')


# ---------------------------------------------------------------------------
# County → CBSA (Census delineation Excel)
# ---------------------------------------------------------------------------

def load_cbsa_delineation(path: str) -> pd.DataFrame:
    """
    Parse the Census CBSA delineation Excel (list1_2023.xlsx).
    Returns a DataFrame with columns (county_fips, cbsa, cbsa_title).
    """
    ext = Path(path).suffix.lower()
    if ext in ('.xlsx', '.xls'):
        raw = pd.read_excel(path, dtype=str, header=None)
        header_row = None
        for i in range(min(10, len(raw))):
            row_vals = raw.iloc[i].astype(str).str.lower().tolist()
            if any('cbsa' in v for v in row_vals) and any('fips' in v for v in row_vals):
                header_row = i
                break
        if header_row is None:
            header_row = 0
        raw.columns = raw.iloc[header_row].astype(str).str.strip()
        raw = raw.iloc[header_row + 1:].reset_index(drop=True)
    else:
        raw = pd.read_csv(path, dtype=str)

    cols_lower = {c.lower().strip(): c for c in raw.columns}

    cbsa_col = None
    for cand in ['cbsa code', 'cbsa', 'cbsacode']:
        if cand in cols_lower:
            cbsa_col = cols_lower[cand]
            break

    state_fips_col = None
    for cand in ['fips state code', 'state fips', 'statefp']:
        if cand in cols_lower:
            state_fips_col = cols_lower[cand]
            break

    county_fips_col = None
    for cand in ['fips county code', 'county fips', 'countyfp']:
        if cand in cols_lower:
            county_fips_col = cols_lower[cand]
            break

    title_col = None
    for cand in ['cbsa title', 'cbsa_title', 'title']:
        if cand in cols_lower:
            title_col = cols_lower[cand]
            break

    if cbsa_col is None:
        raise ValueError(f'Cannot find CBSA code column. Found: {list(raw.columns)}')

    if state_fips_col and county_fips_col:
        out = raw[[cbsa_col, state_fips_col, county_fips_col]].copy()
        out.columns = ['cbsa', 'state_fips', 'county_fips_part']
        out = out.dropna(subset=['cbsa', 'state_fips', 'county_fips_part'])
        out['county_fips'] = (
            out['state_fips'].str.strip().str.zfill(2) +
            out['county_fips_part'].str.strip().str.zfill(3)
        )
        out = out[['county_fips', 'cbsa']].copy()
    elif 'county_fips' in cols_lower:
        fips_col = cols_lower['county_fips']
        out = raw[[fips_col, cbsa_col]].copy()
        out.columns = ['county_fips', 'cbsa']
    else:
        raise ValueError(
            f'Cannot find county FIPS columns. Found: {list(raw.columns)}'
        )

    out['cbsa'] = out['cbsa'].str.strip()
    out['county_fips'] = out['county_fips'].str.strip().str.zfill(5)

    if title_col:
        titles = raw[[cbsa_col, title_col]].copy()
        titles.columns = ['cbsa', 'cbsa_title']
        titles = titles.drop_duplicates('cbsa')
        out = out.merge(titles, on='cbsa', how='left')

    return out.drop_duplicates().reset_index(drop=True)


def attach_cbsa(entities: pd.DataFrame, delineation: pd.DataFrame) -> pd.DataFrame:
    """Merge CBSA code onto entities via county_fips."""
    merge_cols = ['county_fips', 'cbsa']
    if 'cbsa_title' in delineation.columns:
        merge_cols.append('cbsa_title')
    return entities.merge(
        delineation[merge_cols].drop_duplicates('county_fips'),
        on='county_fips',
        how='left',
    )


# ---------------------------------------------------------------------------
# Market views
# ---------------------------------------------------------------------------

def build_market_view(entities: pd.DataFrame, market: dict) -> pd.DataFrame:
    """Filter entities into a market view by CBSA, county, ZIP, and/or state."""
    df = entities.copy()
    cbsa_codes = set(market.get('cbsa_codes') or [])
    counties = set(market.get('counties') or [])
    zips = set(market.get('zips') or [])
    states = set(market.get('states') or [])

    mask = pd.Series(False, index=df.index)
    reasons = []
    if cbsa_codes and 'cbsa' in df.columns:
        m = df['cbsa'].isin(cbsa_codes)
        mask |= m
        reasons.append(('in_cbsa', m))
    if counties and 'county_fips' in df.columns:
        m = df['county_fips'].isin(counties)
        mask |= m
        reasons.append(('in_county', m))
    if zips and 'zip' in df.columns:
        m = df['zip'].isin(zips)
        mask |= m
        reasons.append(('in_zip', m))

    out = df[mask].copy()
    if states and 'state' in out.columns:
        out = out[out['state'].isin(states)].copy()

    def reason_for(i):
        rs = [name for name, m in reasons if bool(m.loc[i])]
        return '|'.join(rs) if rs else 'unknown'

    out['inclusion_reason'] = [reason_for(i) for i in out.index]
    out['market_id'] = market.get('market_id')
    return out
