"""
resolve.py
Entity resolution — match NPPES providers to CMS hospitals using
exact identifier matching and fuzzy name matching.

Performance: Only fuzzy-matches NPPES *organizations* (not individual
practitioners) against CMS hospitals. Individual providers pass through
with their own entity_guid.
"""

from __future__ import annotations
import uuid
from dataclasses import dataclass
from typing import Tuple
import numpy as np
import pandas as pd

try:
    from rapidfuzz import fuzz
    _HAS_RAPIDFUZZ = True
except Exception:
    import difflib
    _HAS_RAPIDFUZZ = False


@dataclass
class ResolutionConfig:
    name_threshold: int = 90
    require_state_match: bool = True


def _sim(a: str, b: str) -> int:
    a = a or ''
    b = b or ''
    if _HAS_RAPIDFUZZ:
        return int(fuzz.token_set_ratio(a, b))
    return int(100 * difflib.SequenceMatcher(None, a, b).ratio())


def resolve_entities(
    primary: pd.DataFrame,
    secondary: pd.DataFrame,
    cfg: ResolutionConfig,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Resolve entities across NPPES (primary) and CMS hospitals (secondary).

    Strategy for speed:
    - Pass 1: exact NPI/CCN join (vectorized, instant)
    - Pass 2: fuzzy name match, but ONLY for NPPES organizations
      (entity_type_code == '2'), not individual practitioners
    - Unmatched records get their own entity_guid without expensive groupby
    """
    p = primary.copy()
    s = secondary.copy()
    links = []

    print(f'    Primary: {len(p):,} rows, Secondary: {len(s):,} rows')

    # --- Pass 1: exact identifier matching (vectorized) ---
    matched_p_idx = set()
    matched_s_idx = set()

    for idcol in ('npi', 'ccn'):
        if idcol in p.columns and idcol in s.columns:
            p_valid = p[p[idcol].notna() & (p[idcol].astype(str).str.strip() != '')]
            s_valid = s[s[idcol].notna() & (s[idcol].astype(str).str.strip() != '')]
            merged = p_valid[[idcol]].merge(
                s_valid[[idcol]], on=idcol, how='inner',
            )
            matched_ids = set(merged[idcol].tolist())
            for idx, row in p_valid.iterrows():
                if row[idcol] in matched_ids and idx not in matched_p_idx:
                    s_match = s_valid[s_valid[idcol] == row[idcol]]
                    if not s_match.empty:
                        links.append({
                            'p_idx': idx,
                            's_idx': s_match.index[0],
                            'match_type': f'exact_{idcol}',
                            'confidence': 1.0,
                        })
                        matched_p_idx.add(idx)
                        matched_s_idx.add(s_match.index[0])

    print(f'    Pass 1 (exact ID): {len(links)} matches')

    # --- Pass 2: fuzzy name match (ONLY organizations, not individual providers) ---
    if 'entity_type_code' in p.columns:
        p_orgs = p[
            (~p.index.isin(matched_p_idx)) &
            (p['entity_type_code'].astype(str).str.strip() == '2')
        ]
    else:
        p_orgs = p[~p.index.isin(matched_p_idx)]

    s_rem = s[~s.index.isin(matched_s_idx)]

    print(f'    Pass 2: fuzzy matching {len(p_orgs):,} orgs against {len(s_rem):,} hospitals')

    if len(p_orgs) > 0 and len(s_rem) > 0:
        key_cols = [c for c in ['state', 'zip'] if c in s_rem.columns]
        s_index = {}
        if key_cols:
            for k, grp in s_rem.groupby(key_cols):
                s_index[k] = grp
        else:
            s_index[('all',)] = s_rem

        fuzzy_count = 0
        for idx, pr in p_orgs.iterrows():
            k = tuple(pr[c] for c in key_cols) if key_cols else ('all',)
            cand = s_index.get(k)
            if cand is None or cand.empty:
                continue
            best_idx, best_score = None, -1
            for sidx, sr in cand.iterrows():
                if (cfg.require_state_match and 'state' in pr and 'state' in sr
                        and pr['state'] != sr['state']):
                    continue
                score = _sim(str(pr.get('norm_name', '')), str(sr.get('norm_name', '')))
                if score > best_score:
                    best_idx, best_score = sidx, score
            if best_idx is not None and best_score >= cfg.name_threshold:
                links.append({
                    'p_idx': idx,
                    's_idx': best_idx,
                    'match_type': 'fuzzy_name_zip',
                    'confidence': min(1.0, best_score / 100.0),
                })
                fuzzy_count += 1

        print(f'    Pass 2 (fuzzy): {fuzzy_count} matches')

    link_df = pd.DataFrame(links)

    # --- Build output: merge matched pairs, pass-through unmatched ---
    print(f'    Building gold entities ...')

    matched_p_idx = set(link_df['p_idx'].tolist()) if not link_df.empty else set()
    matched_s_idx = set(link_df['s_idx'].tolist()) if not link_df.empty else set()

    gold_rows = []

    # Matched pairs: merge attributes from both sources
    for _, link in link_df.iterrows():
        pr = p.loc[link['p_idx']]
        sr = s.loc[link['s_idx']]
        guid = str(uuid.uuid4())
        merged = {}
        merged['entity_guid'] = guid
        merged['resolution_confidence'] = link['confidence']
        merged['source'] = 'nppes|cms_hospital'

        for col in ['display_name', 'norm_name', 'state', 'zip', 'city', 'address',
                     'npi', 'ccn', 'entity_type', 'hospital_type', 'ownership',
                     'emergency_services', 'county_name', 'taxonomy_code',
                     'entity_type_code']:
            val = _pick(pr.get(col), sr.get(col))
            if val is not None:
                merged[col] = val

        if 'hospital_rating' in sr.index and pd.notna(sr.get('hospital_rating')):
            merged['hospital_rating'] = sr['hospital_rating']
        elif 'hospital_rating' in pr.index and pd.notna(pr.get('hospital_rating')):
            merged['hospital_rating'] = pr['hospital_rating']

        gold_rows.append(merged)

    # Unmatched primary (NPPES) — pass through
    p_unmatched = p[~p.index.isin(matched_p_idx)]
    if len(p_unmatched) > 0:
        pu = p_unmatched.copy()
        pu['entity_guid'] = [str(uuid.uuid4()) for _ in range(len(pu))]
        pu['resolution_confidence'] = 0.7
        if 'source' not in pu.columns:
            pu['source'] = 'nppes'
        gold_rows_p = pu.to_dict('records')
    else:
        gold_rows_p = []

    # Unmatched secondary (CMS) — pass through
    s_unmatched = s[~s.index.isin(matched_s_idx)]
    if len(s_unmatched) > 0:
        su = s_unmatched.copy()
        su['entity_guid'] = [str(uuid.uuid4()) for _ in range(len(su))]
        su['resolution_confidence'] = 0.7
        if 'source' not in su.columns:
            su['source'] = 'cms_hospital'
        gold_rows_s = su.to_dict('records')
    else:
        gold_rows_s = []

    print(f'    Matched: {len(gold_rows)}, NPPES pass-through: {len(gold_rows_p)}, '
          f'CMS pass-through: {len(gold_rows_s)}')

    entities_gold = pd.DataFrame(gold_rows + gold_rows_p + gold_rows_s)

    # Clean up temp columns
    for col in ['__row_id']:
        if col in entities_gold.columns:
            entities_gold.drop(columns=[col], inplace=True)

    return entities_gold, link_df


def _pick(a, b):
    """Pick the first non-empty value from two candidates."""
    for v in [a, b]:
        if v is not None and pd.notna(v) and str(v).strip() not in ('', 'nan', 'None'):
            return v
    return None
