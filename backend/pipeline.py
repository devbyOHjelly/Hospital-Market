from __future__ import annotations
from pathlib import Path
from backend.map.build_base_map import ABBR_TO_NAME, build, _load_cfg
import argparse
import sys
import time

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

def run_pipeline(states: list[str] | None = None) -> dict:
    t0 = time.time()
    cfg = _load_cfg()
    print("=" * 60)
    print("PIPELINE — base map (Tier 1 parquet + ZCTA polygons)")
    print("=" * 60)

    if not cfg.get("outputs", {}).get("write_gpkg", True):
        print("WARNING: outputs.write_gpkg is false — no file written")

    state_names = None
    if states:
        state_names = {ABBR_TO_NAME[s.upper()] for s in states if s.upper() in ABBR_TO_NAME}

    out = build(empty_mode=False, state_filter=state_names, cfg=cfg)

    elapsed = time.time() - t0
    print(f"\nDone in {elapsed:.1f}s → {out}")
    return {"output_gpkg": str(out), "elapsed_seconds": round(elapsed, 1)}

def main() -> None:
    cfg = _load_cfg()
    default_states = cfg.get("project", {}).get("default_states", ["FL", "GA", "AL"])
    ap = argparse.ArgumentParser(description="Build zcta_hospital_potential.gpkg from Tier 1 parquet")
    ap.add_argument("--states", nargs="*", default=None, help=f"State abbreviations (default: {default_states})")
    args = ap.parse_args()
    st = args.states if args.states is not None else default_states
    run_pipeline(st)

if __name__ == "__main__":
    main()