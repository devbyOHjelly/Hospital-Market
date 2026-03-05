"""
io_utils.py
Data loading utilities — local file discovery, CMS API fetch, local-or-fetch pattern.

Adapted from asset_intel_starter_kit_v02/src/asset_intel/io.py
"""

from __future__ import annotations
import glob
import os
from pathlib import Path
from typing import Optional, Dict

import pandas as pd
import requests


def read_csv_any(path: str, **kwargs) -> pd.DataFrame:
    return pd.read_csv(path, low_memory=False, **kwargs)


def find_latest(glob_pattern: str) -> Optional[str]:
    """Find the most-recently-modified file matching a glob pattern."""
    files = sorted(glob.glob(glob_pattern))
    if not files:
        return None
    return sorted(files, key=lambda f: os.path.getmtime(f), reverse=True)[0]


def load_nppes(raw_dir: str, monthly_glob: str = 'npidata_pfile_*.csv') -> Dict[str, pd.DataFrame]:
    """Load the latest NPPES monthly file from a directory."""
    main_file = find_latest(str(Path(raw_dir) / monthly_glob))
    if main_file is None:
        raise FileNotFoundError(f'No NPPES file found in {raw_dir} with {monthly_glob}')
    npi = read_csv_any(main_file, dtype=str)
    meta = pd.DataFrame({'main_file': [main_file]})
    return {'npi': npi, 'meta': meta}


def fetch_socrata_csv(
    dataset_id: str,
    base_url: str = 'https://data.cms.gov/provider-data/api/',
    app_token: str = '',
) -> pd.DataFrame:
    """Download a CSV from the CMS Socrata API."""
    headers = {'X-App-Token': app_token} if app_token else {}
    url = f"{base_url}views/{dataset_id}/rows.csv?accessType=DOWNLOAD"
    r = requests.get(url, headers=headers, timeout=120)
    r.raise_for_status()
    from io import StringIO
    return pd.read_csv(StringIO(r.text), dtype=str)


def load_local_or_fetch(path: str, fetch_fn, *args, **kwargs) -> pd.DataFrame:
    """Return local CSV if it exists, otherwise call the fetch function."""
    if path and os.path.exists(path):
        return read_csv_any(path, dtype=str)
    return fetch_fn(*args, **kwargs)
