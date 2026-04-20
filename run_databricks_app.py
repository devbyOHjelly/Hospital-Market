from __future__ import annotations
import os
import subprocess
import sys
from pathlib import Path

# =============================================================================
# DATABRICKS — volume paths (full /Volumes/... paths). Leave "" for repo defaults.
# =============================================================================

# Base map GeoPackage (required for the map). Too large for app source — put on a volume.
VOLUME_GPKG = "/Volumes/datascience/default/hospitalmarketanalysis/zcta_hospital_potential.gpkg"
# Example: VOLUME_GPKG = "/Volumes/main/market_intel/files/zcta_hospital_potential.gpkg"

# Entity layer parquet. App reads backend/data/gold/entities.parquet by default.
VOLUME_ENTITIES = "/Volumes/datascience/default/hospitalmarketanalysis/entities.parquet"
# Example: VOLUME_ENTITIES = "/Volumes/main/market_intel/files/entities.parquet"

# Tier 1 scores parquet (Dash overlay + pipeline input when you run the pipeline).
VOLUME_TIER1 = "/Volumes/datascience/default/hospitalmarketanalysis/final_tier1_all_percentiles.parquet"
# Example: VOLUME_TIER1 = "/Volumes/main/market_intel/files/final_tier1_all_percentiles.parquet"

# Optional. When the pipeline runs, Census zips and zcta_shp/state_shp extract here.
# Pre-upload zcta_500k.zip + state_500k.zip to this folder if the app cannot reach the internet.
# Leave "" to use backend/data/ (not recommended if that tree is not in the app bundle).
VOLUME_DATA_CACHE = ""
# Example:
# VOLUME_DATA_CACHE = "/Volumes/main/market_intel/cache"

# --- Pipeline control ---
# Databricks Apps often cannot resolve www2.census.gov (DNS / egress). If your gpkg is
# already on a volume, keep SKIP_PIPELINE True. Set False only when you can rebuild:
# attach this UC volume as an App resource, grant read on the gpkg path, and either
# allowlist census egress or pre-stage Tiger zips under VOLUME_DATA_CACHE.
SKIP_PIPELINE = True

# If True and SKIP_PIPELINE is False: skip pipeline only when HOSPITAL_MARKET_GPKG exists
# inside *this* container (requires the volume to be mounted on the app).
SKIP_PIPELINE_IF_GPKG_EXISTS = True


def _volume_env_overrides() -> dict[str, str]:
    out: dict[str, str] = {}

    if VOLUME_GPKG.strip():
        out["HOSPITAL_MARKET_GPKG"] = VOLUME_GPKG.strip()
    if VOLUME_ENTITIES.strip():
        out["HOSPITAL_MARKET_ENTITIES"] = VOLUME_ENTITIES.strip()
    if VOLUME_TIER1.strip():
        out["HOSPITAL_MARKET_TIER1"] = VOLUME_TIER1.strip()
    if VOLUME_DATA_CACHE.strip():
        out["HOSPITAL_MARKET_DATA_DIR"] = VOLUME_DATA_CACHE.strip()

    if SKIP_PIPELINE:
        out["HOSPITAL_MARKET_SKIP_PIPELINE"] = "1"
    elif SKIP_PIPELINE_IF_GPKG_EXISTS:
        out["HOSPITAL_MARKET_SKIP_PIPELINE_IF_GPKG"] = "1"

    return out


def _resolved_gpkg_path(env: dict[str, str]) -> Path:
    override = env.get("HOSPITAL_MARKET_GPKG", "").strip()
    if override:
        return Path(override)
    root = Path(__file__).resolve().parent
    return root / "backend" / "data" / "zcta_hospital_potential.gpkg"


def _should_skip_pipeline(env: dict[str, str]) -> bool:
    if env.get("HOSPITAL_MARKET_SKIP_PIPELINE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    if env.get("HOSPITAL_MARKET_SKIP_PIPELINE_IF_GPKG", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return _resolved_gpkg_path(env).is_file()
    return False


def _repo_root() -> Path:
    return Path(__file__).resolve().parent


def _env_with_repo_on_path(base: dict[str, str], root: Path) -> dict[str, str]:
    """So `import backend` works in child processes (Databricks cwd / import order)."""
    root_s = str(root)
    existing = (base.get("PYTHONPATH") or "").strip()
    merged = f"{root_s}{os.pathsep}{existing}" if existing else root_s
    return {**base, "PYTHONPATH": merged}


def main() -> None:
    additions = _volume_env_overrides()
    root = _repo_root()
    proc_env: dict[str, str] = _env_with_repo_on_path(
        {**os.environ, **{k: str(v) for k, v in additions.items()}},
        root,
    )

    if not _should_skip_pipeline(proc_env):
        gpkg = proc_env.get("HOSPITAL_MARKET_GPKG", "").strip()
        if gpkg and not Path(gpkg).is_file():
            print(
                "WARNING: HOSPITAL_MARKET_GPKG is set but this process cannot read that file "
                f"({gpkg!r}). The pipeline will run. Attach the Unity Catalog volume to the app "
                "or set SKIP_PIPELINE = True if the map is already built. Without egress to "
                "www2.census.gov, put zcta_500k.zip and state_500k.zip under VOLUME_DATA_CACHE.",
                flush=True,
            )
        subprocess.run(
            [sys.executable, "backend/pipeline.py"],
            check=True,
            cwd=root,
            env=proc_env,
        )

    subprocess.run(
        [sys.executable, "frontend/dash_app.py"],
        check=True,
        cwd=root,
        env={**proc_env, "PORT": "8000"},
    )


if __name__ == "__main__":
    main()
