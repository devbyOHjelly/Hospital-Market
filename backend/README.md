## Backend structure

```text
backend/                                  # backend root
├── pipeline.py                           # builds zcta_hospital_potential.gpkg from config + Tier 1/2/3 + shapes
├── configs/
│   └── config.yml                        # paths, hospital_potential scoring, outputs
├── agent/
│   ├── agent_config.py                   # score definitions, defaults, prompts, option aliases
│   ├── chat_client.py                    # OpenRouter API client + dataset context for the LLM
│   └── query_router.py                   # structured / tabular answers before or instead of the LLM
├── map/
│   ├── build_base_map.py                 # Folium map HTML + merge Tier 1/2/3 onto ZCTA polygons
│   └── scoring_from_config.py            # hospital_potential from config.yml
└── data/
    ├── raw/                              # Tier 1/2/3 parquet, optional NPPES CSV drops
    ├── gold/                             # curated outputs for the app
    ├── zcta_shp/                         # Census ZCTA boundaries used by the pipeline
    └── state_shp/                        # Census state boundaries used by the pipeline
```