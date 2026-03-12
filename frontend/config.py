import os
import branca.colormap as cm

TARGET_STATES = ["FL", "GA", "AL"]

# Paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(APP_DIR)
DATA_PATH = os.path.join(REPO_ROOT, "backend", "data", "zcta_hospital_potential.gpkg")
ENTITIES_PATH = os.path.join(REPO_ROOT, "backend", "data", "gold", "entities.parquet")
ZCTA_SHP_DIR = os.path.join(REPO_ROOT, "backend", "data", "zcta_shp")
STATE_SHP_DIR = os.path.join(REPO_ROOT, "backend", "data", "state_shp")
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
WWW_DIR = os.path.join(APP_DIR, "modules", "map", "www")
os.makedirs(WWW_DIR, exist_ok=True)

# Color map
COLORMAP = cm.LinearColormap(
    colors=["#ffffff", "#fff0d4", "#ffd699", "#ffb84d", "#ff7f00", "#ff7f00"],
    vmin=0,
    vmax=100,
)
import os
import branca.colormap as cm

TARGET_STATES = ["FL", "GA", "AL"]

# Paths
APP_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_ROOT = os.path.dirname(APP_DIR)
DATA_PATH = os.path.join(REPO_ROOT, "backend", "data", "zcta_hospital_potential.gpkg")
ENTITIES_PATH = os.path.join(REPO_ROOT, "backend", "data", "gold", "entities.parquet")
ZCTA_SHP_DIR = os.path.join(REPO_ROOT, "backend", "data", "zcta_shp")
STATE_SHP_DIR = os.path.join(REPO_ROOT, "backend", "data", "state_shp")
BACKEND_DIR = os.path.join(REPO_ROOT, "backend")
WWW_DIR = os.path.join(APP_DIR, "modules", "map", "www")
os.makedirs(WWW_DIR, exist_ok=True)

# Color map
COLORMAP = cm.LinearColormap(
    colors=["#ffffff", "#fff0d4", "#ffd699", "#ffb84d", "#ff7f00", "#ff7f00"],
    vmin=0,
    vmax=100,
)