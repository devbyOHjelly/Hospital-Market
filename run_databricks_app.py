import os
import subprocess
import sys
from pathlib import Path


def _resolved_gpkg_path() -> Path:
    override = os.environ.get("HOSPITAL_MARKET_GPKG", "").strip()
    if override:
        return Path(override)
    root = Path(__file__).resolve().parent
    return root / "backend" / "data" / "zcta_hospital_potential.gpkg"


def _should_skip_pipeline() -> bool:
    if os.environ.get("HOSPITAL_MARKET_SKIP_PIPELINE", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return True
    if os.environ.get("HOSPITAL_MARKET_SKIP_PIPELINE_IF_GPKG", "").strip().lower() in (
        "1",
        "true",
        "yes",
    ):
        return _resolved_gpkg_path().is_file()
    return False


def main() -> None:
    # 1) Build/update data artifacts (omit zcta_shp from the app bundle; use
    #    HOSPITAL_MARKET_DATA_DIR on DBFS for downloads, or skip if gpkg is pre-built).
    if not _should_skip_pipeline():
        subprocess.run([sys.executable, "backend/pipeline.py"], check=True)

    # 2) Start Dash app (foreground process for Databricks Apps).
    env = {**os.environ, "PORT": "8000"}
    subprocess.run(
        [sys.executable, "frontend/dash_app.py"],
        check=True,
        env=env,
    )

if __name__ == "__main__":
    main()