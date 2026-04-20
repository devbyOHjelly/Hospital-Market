## Frontend structure

```text
frontend/                                 # frontend root
├── dash_app.py                           # Dash app, callbacks, and CLI entry
├── config.py                             # paths to data, brand colors, legend CSS helpers
├── assets/
│   └── dash_bridge.js                    # parent-page glue
├── image/
│   └── orange.jpg                        # OH image
└── modules/
    ├── dash_css.py                       # injects dashboard stylesheet
    ├── definitions_html.py               # Reference tab HTML + framework chart snippets
    ├── agent_chat.py                     # agent tab: calls backend agent
    ├── scoring_core.py                   # weights / scoring
    ├── dashboard/
    │   ├── styles.py                     # large APP_CSS (sidebar, market, settings, ranks)
    │   ├── sidebar.py                    # Selection tab HTML
    │   └── utils.py                      # small helpers
    ├── data/
    │   └── loader.py                     # reads zcta gpkg + entities parquet
    └── map/
        ├── builder.py                    # Folium → HTML string
        └── www/
            ├── map.html                  # map iframe document 
            └── .gitkeep                  # keeps www/ in git when map.html is not committed
```