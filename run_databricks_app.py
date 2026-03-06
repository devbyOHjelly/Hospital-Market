import subprocess
import sys


def main() -> None:
    # 1) Build/update data artifacts before serving the app.
    subprocess.run([sys.executable, "backend/pipeline.py"], check=True)

    # 2) Start Shiny app (foreground process for Databricks Apps).
    subprocess.run(
        [
            sys.executable,
            "-m",
            "shiny",
            "run",
            "--host",
            "0.0.0.0",
            "--port",
            "8000",
            "frontend/app.py",
        ],
        check=True,
    )


if __name__ == "__main__":
    main()