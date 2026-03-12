from __future__ import annotations
import pandas as pd
from backend.modules.shared.utils import normalize_name, normalize_state, normalize_zip

NPPES_RENAME = {
    'NPI': 'npi',
    'Entity Type Code': 'entity_type_code',
    'Provider Organization Name (Legal Business Name)': 'legal_name',
    'Provider First Name': 'first_name',
    'Provider Last Name (Legal Name)': 'last_name',
    'Provider Business Practice Location Address - State Name': 'state',
    'Provider Business Practice Location Address - Postal Code': 'zip',
    'Healthcare Provider Taxonomy Code_1': 'taxonomy_code',
    'Provider Business Practice Location Address City Name': 'city',
    'Provider Business Practice Location Address - Address Line 1': 'address',
    'entity_type': 'entity_type_code',
    'taxonomy': 'taxonomy_code',
}

CMS_RENAME = {
    'Facility ID': 'ccn',
    'Facility Name': 'display_name',
    'State': 'state',
    'ZIP Code': 'zip',
    'Hospital Type': 'hospital_type',
    'Hospital Ownership': 'ownership',
    'Emergency Services': 'emergency_services',
    'Hospital overall rating': 'hospital_rating',
    'Address': 'address',
    'City/Town': 'city',
    'County Name': 'county_name',
}

def nppes_to_entities(nppes_main: pd.DataFrame) -> pd.DataFrame:
    df = nppes_main.copy()
    for k, v in NPPES_RENAME.items():
        if k in df.columns:
            df.rename(columns={k: v}, inplace=True)

    df['display_name'] = df.get('legal_name')
    mask = df['display_name'].isna() | (df['display_name'].astype(str).str.strip() == '')
    if 'first_name' in df.columns and 'last_name' in df.columns:
        df.loc[mask, 'display_name'] = (
            df.loc[mask, 'first_name'].fillna('') + ' ' +
            df.loc[mask, 'last_name'].fillna('')
        ).str.strip()

    df['norm_name'] = df['display_name'].apply(normalize_name)
    df['state'] = df['state'].apply(normalize_state)
    df['zip'] = df['zip'].apply(normalize_zip)
    df['source'] = 'nppes'

    keep = [
        'npi', 'entity_type_code', 'display_name', 'norm_name',
        'state', 'zip', 'taxonomy_code', 'city', 'address', 'source',
    ]
    keep = [c for c in keep if c in df.columns]
    return df[keep].drop_duplicates(subset=['npi'])


def cms_hospitals_to_entities(hosp_df: pd.DataFrame) -> pd.DataFrame:
    df = hosp_df.copy()
    for k, v in CMS_RENAME.items():
        if k in df.columns:
            df.rename(columns={k: v}, inplace=True)

    df['norm_name'] = df['display_name'].apply(normalize_name)
    df['state'] = df['state'].apply(normalize_state)
    df['zip'] = df['zip'].apply(normalize_zip)
    df['source'] = 'cms_hospital'
    df['entity_type'] = 'hospital'

    if 'hospital_rating' in df.columns:
        df['hospital_rating'] = pd.to_numeric(df['hospital_rating'], errors='coerce')

    keep = [
        'ccn', 'display_name', 'norm_name', 'state', 'zip', 'entity_type',
        'hospital_type', 'ownership', 'emergency_services', 'hospital_rating',
        'city', 'address', 'county_name', 'source',
    ]
    keep = [c for c in keep if c in df.columns]
    return df[keep].drop_duplicates(subset=['ccn'])