"""
pipeline.py
Entity pipeline orchestrator (v0.2 — national registry + market views).

Outputs:
    data/gold/entities.parquet   — national entity registry
    data/gold/scores.parquet     — rubric scores
    data/gold/links.parquet      — entity resolution link table
    data/views/<market_id>/entities.parquet — per-market entity slice
    data/views/<market_id>/scores.parquet   — per-market score slice
    data/census_demographics.parquet
    data/zcta_hospital_potential.gpkg

Usage:
    cd backend
    python pipeline.py                      # default: states from config.yml
    python pipeline.py --states FL          # single state override
"""

from __future__ import annotations
import argparse
import os
import sys
import time
from pathlib import Path

import pandas as pd
import yaml
import requests
from io import StringIO

from transform import nppes_to_entities, cms_hospitals_to_entities
from resolve import resolve_entities, ResolutionConfig
from market import (
    load_zip_county_crosswalk, apply_zip_to_county,
    load_cbsa_delineation, attach_cbsa, build_market_view,
)
from formula.scoring import score_entities, compute_rubric_scores
from census import fetch_tier1_demographics
from io_utils import find_latest
from tier2 import build_tier2_demographics

DATA_DIR = Path(__file__).parent / 'data'
RAW_DIR = DATA_DIR / 'raw'
GOLD_DIR = DATA_DIR / 'gold'
VIEWS_DIR = DATA_DIR / 'views'
CENSUS_PATH = DATA_DIR / 'census_demographics.parquet'
TIER2_PATH = DATA_DIR / 'tier2_demographics.parquet'
CONFIG_PATH = Path(__file__).parent / 'configs' / 'config.yml'

_NPPES_WANT = {
    'npi':           ['NPI'],
    'entity_type':   ['Entity Type Code'],
    'legal_name':    ['Provider Organization Name', 'Legal Business Name'],
    'first_name':    ['Provider First Name'],
    'last_name':     ['Provider Last Name'],
    'state':         ['Practice Location', 'State'],
    'zip':           ['Practice Location', 'Postal Code'],
    'taxonomy':      ['Taxonomy Code_1', 'Healthcare Provider Taxonomy'],
    'city':          ['Practice Location', 'City'],
    'address':       ['Practice Location', 'Address', 'First Line', 'Line 1'],
}


def _load_config() -> dict:
    """Load pipeline config from configs/config.yml."""
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
            return yaml.safe_load(f) or {}
    return {}


def _resolve_path(cfg_path: str) -> Path:
    """Resolve a config-relative path to an absolute path under backend/."""
    p = Path(cfg_path)
    if p.is_absolute():
        return p
    return Path(__file__).parent / p


def _get_nppes_dir(cfg: dict) -> Path:
    """Get NPPES directory from config, falling back to default."""
    raw_dir = cfg.get('sources', {}).get('nppes', {}).get('raw_dir', '')
    if raw_dir:
        return _resolve_path(raw_dir)
    return RAW_DIR / 'NPPES_Data_Dissemination_February_2026'


def _get_nppes_glob(cfg: dict) -> str:
    return cfg.get('sources', {}).get('nppes', {}).get(
        'monthly_file_glob', 'npidata_pfile_*.csv'
    )


def _get_crosswalk_path(cfg: dict) -> Path:
    """Get ZIP→County crosswalk path from config."""
    p = cfg.get('reference_data', {}).get('hud_zip_crosswalk', {}).get('cache_file', '')
    if p:
        return _resolve_path(p)
    return RAW_DIR / 'reference' / 'hud_zip_county_crosswalk.csv'


def _get_cbsa_path(cfg: dict) -> Path:
    """Get County→CBSA delineation path from config."""
    p = cfg.get('reference_data', {}).get('cbsa_delineation', {}).get('local_file', '')
    if p:
        return _resolve_path(p)
    return RAW_DIR / 'reference' / 'county_to_cbsa.csv'


def _find_nppes_file(cfg: dict) -> str:
    nppes_dir = _get_nppes_dir(cfg)
    glob_pattern = _get_nppes_glob(cfg)
    pattern = str(nppes_dir / glob_pattern)
    result = find_latest(pattern)
    if result is None:
        raise FileNotFoundError(f'No NPPES main file found matching {pattern}')
    if 'fileheader' in Path(result).name.lower():
        import glob as glob_mod
        files = [f for f in glob_mod.glob(pattern) if 'fileheader' not in f.lower()]
        if not files:
            raise FileNotFoundError(f'No NPPES main file found matching {pattern}')
        result = sorted(files, key=os.path.getmtime, reverse=True)[0]
    return result


def _match_columns(actual_cols: list[str]) -> tuple[list[str], dict[str, str], str]:
    """Match _NPPES_WANT keywords against actual CSV columns."""
    usecols = []
    rename = {}
    state_col = None

    for key, keywords in _NPPES_WANT.items():
        best = None
        for col in actual_cols:
            col_up = col.upper()
            if all(kw.upper() in col_up for kw in keywords):
                best = col
                break
        if best:
            usecols.append(best)
            rename[best] = key
            if key == 'state':
                state_col = best

    return usecols, rename, state_col


def _load_nppes_chunked(cfg: dict, states: list[str] | None,
                        chunk_size: int = 500_000) -> pd.DataFrame:
    """Read the NPPES CSV in chunks, filtering by state to save memory."""
    path = _find_nppes_file(cfg)
    print(f'  Reading NPPES: {path}')
    print(f'  State filter: {states or "ALL (no filter)"}')

    header = pd.read_csv(path, nrows=0, dtype=str).columns.tolist()
    usecols, rename, state_col = _match_columns(header)
    print(f'  Matched {len(usecols)}/{len(_NPPES_WANT)} desired columns')
    if not state_col:
        raise ValueError(f'Cannot find state column in NPPES. Columns: {header[:20]}...')

    frames = []
    total_rows = 0

    for i, chunk in enumerate(pd.read_csv(
        path, dtype=str, usecols=usecols, chunksize=chunk_size, low_memory=False,
    )):
        total_rows += len(chunk)
        if states:
            chunk = chunk[chunk[state_col].str.strip().str.upper().isin(
                [s.upper() for s in states]
            )]
        if len(chunk) > 0:
            frames.append(chunk)
        if (i + 1) % 5 == 0:
            kept = sum(len(f) for f in frames)
            print(f'    ... processed {total_rows:,} rows, kept {kept:,}')

    if not frames:
        raise ValueError(f'No NPPES records found for states: {states}')

    result = pd.concat(frames, ignore_index=True)
    result.rename(columns=rename, inplace=True)
    print(f'  NPPES loaded: {len(result):,} records (from {total_rows:,} total)')
    return result


def _fetch_cms_hospitals(cfg: dict) -> pd.DataFrame:
    """Fetch CMS Hospital General Information via the provider data API."""
    print('  Fetching CMS Hospital General Information ...')
    cms_cfg = cfg.get('sources', {}).get('cms_hospital_general_info', {})
    dataset_id = cms_cfg.get('api', {}).get('dataset_id', 'xubh-q36u')

    raw_file = cms_cfg.get('raw_file', '')
    if raw_file:
        resolved = _resolve_path(raw_file)
        if resolved.exists():
            df = pd.read_csv(str(resolved), dtype=str)
            print(f'  CMS hospitals loaded (local): {len(df):,} records')
            return df

    meta_url = f'https://data.cms.gov/provider-data/api/1/metastore/schemas/dataset/items/{dataset_id}'
    try:
        meta = requests.get(meta_url, timeout=30).json()
        download_url = meta['distribution'][0]['downloadURL']
    except Exception:
        download_url = (
            f'https://data.cms.gov/provider-data/api/1/datastore/query/'
            f'{dataset_id}/0?size=10000&format=csv'
        )

    resp = requests.get(download_url, timeout=120)
    resp.raise_for_status()
    df = pd.read_csv(StringIO(resp.text), dtype=str)
    print(f'  CMS hospitals loaded: {len(df):,} records')
    return df


def run_pipeline(states: list[str] | None = None) -> dict:
    """Run the full entity pipeline (v0.2 — national registry + market views)."""
    t0 = time.time()
    cfg = _load_config()
    print('=' * 60)
    print('ENTITY PIPELINE v0.2')
    print('=' * 60)

    if not cfg.get('outputs', {}).get('write_parquet', True):
        print('WARNING: outputs.write_parquet is false — dry run only')

    # 1. Load & transform NPPES (optional fallback if raw file is missing)
    print('\n[1/8] Loading NPPES ...')
    nppes_entities = pd.DataFrame()
    nppes_enabled = bool(cfg.get('sources', {}).get('nppes', {}).get('enabled', True))
    if nppes_enabled:
        try:
            nppes_raw = _load_nppes_chunked(cfg, states)
            nppes_entities = nppes_to_entities(nppes_raw)
            del nppes_raw
            print(f'  NPPES entities: {len(nppes_entities):,}')
        except (FileNotFoundError, ValueError) as e:
            print(f'  WARNING: NPPES unavailable — continuing without NPPES ({e})')
    else:
        print('  SKIP: NPPES disabled in config')

    # 2. Load & transform CMS hospitals
    print('\n[2/8] Loading CMS Hospital data ...')
    cms_raw = _fetch_cms_hospitals(cfg)
    cms_entities = cms_hospitals_to_entities(cms_raw)
    if states:
        cms_entities = cms_entities[
            cms_entities['state'].str.upper().isin([s.upper() for s in states])
        ].copy()
    del cms_raw
    print(f'  CMS entities: {len(cms_entities):,}')

    # 3. Entity resolution
    print('\n[3/8] Resolving entities ...')
    res_cfg_dict = cfg.get('processing', {}).get('entity_resolution', {})
    res_cfg = ResolutionConfig(
        name_threshold=int(res_cfg_dict.get('name_similarity_threshold', 90)),
        require_state_match=bool(res_cfg_dict.get('require_state_match', True)),
    )
    if len(cms_entities) > 0 and len(nppes_entities) > 0:
        entities, links = resolve_entities(nppes_entities, cms_entities, res_cfg)
    elif len(nppes_entities) > 0:
        entities = nppes_entities.copy()
        entities['entity_guid'] = entities['npi']
        entities['resolution_confidence'] = 0.7
        links = pd.DataFrame()
    else:
        entities = cms_entities.copy()
        entities['entity_guid'] = entities['ccn']
        entities['resolution_confidence'] = 0.7
        links = pd.DataFrame()
    print(f'  Resolved entities: {len(entities):,}')
    print(f'  Links: {len(links):,}')

    # 4. Geographic enrichment (ZIP → County → CBSA)
    print('\n[4/8] Geographic enrichment ...')
    crosswalk = None
    crosswalk_path = _get_crosswalk_path(cfg)
    if crosswalk_path.exists():
        crosswalk = load_zip_county_crosswalk(str(crosswalk_path))
        entities = apply_zip_to_county(entities, crosswalk)
        print(f'  ZIP→County: {entities["county_fips"].notna().sum():,} matched')
        print(f'  Crosswalk:  {crosswalk_path}')
    else:
        print(f'  SKIP: crosswalk not found at {crosswalk_path}')

    cbsa_path = _get_cbsa_path(cfg)
    if cbsa_path.exists() and 'county_fips' in entities.columns:
        delineation = load_cbsa_delineation(str(cbsa_path))
        entities = attach_cbsa(entities, delineation)
        print(f'  County→CBSA: {entities["cbsa"].notna().sum():,} matched')
        print(f'  Delineation: {cbsa_path}')
    else:
        print(f'  SKIP: CBSA delineation not available at {cbsa_path}')

    # 5. Fetch Census demographics (needed for Tier 1 scoring)
    print('\n[5/8] Fetching Census demographics (Tier 1) ...')
    census_df = None
    if CENSUS_PATH.exists():
        census_df = pd.read_parquet(str(CENSUS_PATH))
        print(f'  Loaded cached: {CENSUS_PATH} ({len(census_df):,} ZCTAs)')
    else:
        try:
            census_df = fetch_tier1_demographics()
            if census_df is not None and not census_df.empty:
                census_df.to_parquet(str(CENSUS_PATH), index=False)
                print(f'  Saved: {CENSUS_PATH} ({len(census_df):,} ZCTAs)')
            else:
                print('  SKIP: No Census data (set CENSUS_API_KEY in .env)')
        except Exception as e:
            print(f'  WARNING: Census fetch failed — {e}')

    # 5b. Fetch Tier 2 demographics (NPPES supply, CMS, SAHIE)
    print('\n[5b/8] Building Tier 2 demographics ...')
    tier2_df = None
    _rebuild_tier2 = True
    if TIER2_PATH.exists():
        _cached = pd.read_parquet(str(TIER2_PATH))
        if len(_cached) > 0 and len(_cached.columns) > 3:
            tier2_df = _cached
            _rebuild_tier2 = False
            print(f'  Loaded cached: {TIER2_PATH} ({len(tier2_df):,} ZIPs, {len(tier2_df.columns)} cols)')
        else:
            print(f'  Cache looks empty/broken ({len(_cached)} rows, {len(_cached.columns)} cols) — rebuilding')
    if _rebuild_tier2:
        try:
            tier2_df = build_tier2_demographics(
                entities, census_df, crosswalk=crosswalk, cfg=cfg,
            )
            print(f'  Tier 2 built: {len(tier2_df):,} ZIPs')
        except Exception as e:
            print(f'  WARNING: Tier 2 build failed — {e}')

    # 6. Score entities (Tier 1 + 2 + 3 model)
    print('\n[6/8] Scoring entities ...')
    entities = score_entities(entities, census_df=census_df, tier2_df=tier2_df, cfg=cfg)
    print(f'  Tier 1 range: {entities["tier1_score"].min():.1f} – '
          f'{entities["tier1_score"].max():.1f}')
    print(f'  Tier 2 range: {entities["tier2_score"].min():.1f} – '
          f'{entities["tier2_score"].max():.1f}')
    print(f'  Entity score: {entities["entity_score"].min():.1f} – '
          f'{entities["entity_score"].max():.1f}')

    # 6b. Rubric 4-dimension scores for scores.parquet
    scores = compute_rubric_scores(entities, cfg)
    print(f'  Rubric scores: {len(scores):,} entities scored')

    # 7. Write gold outputs
    write = cfg.get('outputs', {}).get('write_parquet', True)

    print('\n[7/8] Writing gold outputs ...')
    if write:
        GOLD_DIR.mkdir(parents=True, exist_ok=True)
        entities.to_parquet(str(GOLD_DIR / 'entities.parquet'), index=False)
        print(f'  Saved: {GOLD_DIR / "entities.parquet"} ({len(entities):,} entities)')

        scores.to_parquet(str(GOLD_DIR / 'scores.parquet'), index=False)
        print(f'  Saved: {GOLD_DIR / "scores.parquet"} ({len(scores):,} scores)')

        if not links.empty:
            links.to_parquet(str(GOLD_DIR / 'links.parquet'), index=False)
            print(f'  Saved: {GOLD_DIR / "links.parquet"} ({len(links):,} links)')
    else:
        print('  SKIP: write_parquet is false')

    # 7b. Generate market views from config
    markets = cfg.get('markets', [])
    views_written = 0
    if markets and write:
        VIEWS_DIR.mkdir(parents=True, exist_ok=True)
        for market in markets:
            mid = market.get('market_id', 'unknown')
            print(f'  Building market view: {mid} ...')
            try:
                mv = build_market_view(entities, market)
                mv_scores = scores[scores['entity_guid'].isin(mv['entity_guid'])].copy()
                out_dir = VIEWS_DIR / mid
                out_dir.mkdir(parents=True, exist_ok=True)
                mv.to_parquet(str(out_dir / 'entities.parquet'), index=False)
                mv_scores.to_parquet(str(out_dir / 'scores.parquet'), index=False)
                print(f'    {mid}: {len(mv):,} entities, {len(mv_scores):,} scores')
                views_written += 1
            except Exception as e:
                print(f'    WARNING: market view {mid} failed — {e}')

    # 8. Build base map (.gpkg)
    print('\n[8/8] Building base map ...')
    try:
        from build_base_map import build as build_map_data, ABBR_TO_NAME
        state_names = None
        if states:
            state_names = {ABBR_TO_NAME[s.upper()] for s in states
                          if s.upper() in ABBR_TO_NAME}
        build_map_data(state_filter=state_names)
    except Exception as e:
        print(f'  WARNING: base map build failed — {e}')
        print(f'  You can run it manually: python build_base_map.py --states ...')

    elapsed = time.time() - t0
    state_list = sorted(entities["state"].dropna().unique().tolist())
    print(f'\n{"=" * 60}')
    print(f'Pipeline v0.2 complete in {elapsed:.1f}s')
    print(f'  Entities: {len(entities):,}')
    print(f'  Scores:   {len(scores):,}')
    print(f'  Links:    {len(links):,}')
    print(f'  Views:    {views_written}')
    print(f'  States:   {state_list}')
    print(f'  Gold:     {GOLD_DIR}')
    print(f'{"=" * 60}')

    return {
        'entities_national': len(entities),
        'scores_national': len(scores),
        'links': len(links),
        'market_views': views_written,
        'elapsed_seconds': round(elapsed, 1),
    }


def main():
    cfg = _load_config()
    default_states = cfg.get('project', {}).get('default_states', ['FL', 'GA', 'AL'])
    ap = argparse.ArgumentParser(description='Run entity pipeline')
    ap.add_argument('--states', nargs='*', default=None,
                    help=f'State filter (default: {default_states})')
    args = ap.parse_args()
    states = args.states if args.states is not None else default_states
    run_pipeline(states)


if __name__ == '__main__':
    main()
