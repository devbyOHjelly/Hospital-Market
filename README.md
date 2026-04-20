## Repository structure

```text
Hospital-Market/                          # project root
├── .venv/                                # local Python env
├── .env                                  # secret variables
├── .gitignore                            # what Git skips: venvs, .env, caches, huge raw downloads
├── app.yaml                              # Databricks / platform app config when you deploy there
├── README.md                             # this file
├── requirements.txt                      # pip install -r … from repo root after initializing local Python env
├── run_databricks_app.py                 # hosted path: pipeline then Dash on port 8000
├── backend/                              # backend folder: data pipeline
└── frontend/                             # frontend folder: UI and Dash server
    
```

## Local Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Add your Agent API key
echo "OPENROUTER_API_KEY=your_key_here" > .env

# 3. (Optional) Rebuild the map geopackage from Tier 1 parquet + ZCTA shapes
#    Edit backend/configs/config.yml (paths + hospital_potential) first.
cd backend
python pipeline.py

# 4. Launch the Dash app (from repository root)
cd ..
python frontend/dash_app.py
```