"""
utils.py
Text normalization helpers for entity resolution and transform.
"""

import re
import unicodedata

STOPWORDS = frozenset([
    'the', 'and', 'of', 'inc', 'llc', 'pllc', 'ltd', 'corp', 'corporation',
    'company', 'co', 'hospital', 'hospitals', 'medical', 'center', 'health',
    'healthcare', 'system', 'systems', 'group', 'associates', 'clinic',
    'clinics', 'practice', 'services', 'network', 'foundation', 'regional',
])

US_STATE_ABBR = {
    'ALABAMA': 'AL', 'ALASKA': 'AK', 'ARIZONA': 'AZ', 'ARKANSAS': 'AR',
    'CALIFORNIA': 'CA', 'COLORADO': 'CO', 'CONNECTICUT': 'CT', 'DELAWARE': 'DE',
    'DISTRICT OF COLUMBIA': 'DC', 'FLORIDA': 'FL', 'GEORGIA': 'GA', 'HAWAII': 'HI',
    'IDAHO': 'ID', 'ILLINOIS': 'IL', 'INDIANA': 'IN', 'IOWA': 'IA',
    'KANSAS': 'KS', 'KENTUCKY': 'KY', 'LOUISIANA': 'LA', 'MAINE': 'ME',
    'MARYLAND': 'MD', 'MASSACHUSETTS': 'MA', 'MICHIGAN': 'MI', 'MINNESOTA': 'MN',
    'MISSISSIPPI': 'MS', 'MISSOURI': 'MO', 'MONTANA': 'MT', 'NEBRASKA': 'NE',
    'NEVADA': 'NV', 'NEW HAMPSHIRE': 'NH', 'NEW JERSEY': 'NJ', 'NEW MEXICO': 'NM',
    'NEW YORK': 'NY', 'NORTH CAROLINA': 'NC', 'NORTH DAKOTA': 'ND', 'OHIO': 'OH',
    'OKLAHOMA': 'OK', 'OREGON': 'OR', 'PENNSYLVANIA': 'PA', 'RHODE ISLAND': 'RI',
    'SOUTH CAROLINA': 'SC', 'SOUTH DAKOTA': 'SD', 'TENNESSEE': 'TN', 'TEXAS': 'TX',
    'UTAH': 'UT', 'VERMONT': 'VT', 'VIRGINIA': 'VA', 'WASHINGTON': 'WA',
    'WEST VIRGINIA': 'WV', 'WISCONSIN': 'WI', 'WYOMING': 'WY',
}

ABBR_TO_STATE = {v: k for k, v in US_STATE_ABBR.items()}


def normalize_text(s: str) -> str:
    if s is None:
        return ''
    s = unicodedata.normalize('NFKD', str(s)).encode('ascii', 'ignore').decode('ascii')
    s = s.lower()
    s = re.sub(r'[^a-z0-9\s]', ' ', s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s


def normalize_name(name: str) -> str:
    s = normalize_text(name)
    toks = [t for t in s.split() if t not in STOPWORDS]
    return ' '.join(toks)


def normalize_zip(z) -> str:
    if z is None:
        return ''
    z = str(z).strip()
    m = re.match(r'^(\d{5})', z)
    return m.group(1) if m else ''


def normalize_state(st) -> str:
    if st is None:
        return ''
    st = str(st).strip().upper()
    if len(st) == 2 and st.isalpha():
        return st
    return US_STATE_ABBR.get(st, st[:2] if len(st) >= 2 else '')
