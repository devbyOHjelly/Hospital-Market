# Hospital-Market
## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. (Optional) Add your Agent API key
echo "OPENROUTER_API_KEY=your_key_here" > .env

# 3. (Optional) Rebuild the map geopackage from Tier 1 parquet + ZCTA shapes
#    Edit backend/configs/config.yml (paths + hospital_potential) first.
cd backend
python pipeline.py

# 4. Launch the dashboard
cd ..
shiny run frontend/app.py
```