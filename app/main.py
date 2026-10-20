"""DensiMap web app: Atlas publishes the layers as vector tiles, MapLibre styles them."""

import os
from collections import defaultdict
from contextlib import asynccontextmanager
from pathlib import Path

from atlas import Atlas
from atlas.layers.models import LayerServices
from fastapi import FastAPI, Request
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from psycopg import sql

from densimap.config import DEFAULT_CONFIG, load_config

config = load_config(Path(os.environ.get("DENSIMAP_CONFIG", DEFAULT_CONFIG)))
geo = Atlas(os.environ["DATABASE_URL"])
WEB = Path(__file__).resolve().parent.parent / "web"
# Tiles only change when the ETL runs; browsers may reuse them this long.
TILE_MAX_AGE = int(os.environ.get("TILE_MAX_AGE", "3600"))
LAYERS = {
    "establishments": ("analytics.establishments", "Establecimientos DENUE"),
    "hexagons": ("analytics.hexagons", "Hexágonos de densidad"),
    "hexagon_centers": ("analytics.hexagon_centers", "Centros de hexágono"),
    "municipalities": ("analytics.municipalities", "Municipios de la ZMG"),
}

SUMMARY_QUERIES = {
    "run": "SELECT dataset_version, completed_at FROM meta.pipeline_runs"
    " WHERE status = 'completed' ORDER BY completed_at DESC LIMIT 1",
    "municipalities": "SELECT code, name, area_km2 FROM analytics.municipalities ORDER BY name",
    "extent": "SELECT ST_XMin(b) AS minx, ST_YMin(b) AS miny, ST_XMax(b) AS maxx, ST_YMax(b) AS maxy"
    " FROM (SELECT ST_Extent(ST_Transform(geometry, 4326)) AS b FROM analytics.municipalities) e",
    "counts": "SELECT category, municipality_code, count(*) AS n FROM analytics.establishments"
    " GROUP BY 1, 2",
    "hexagons": "SELECT category, size_m, max(count) AS max_count, max(density_km2) AS max_density,"
    " percentile_cont(ARRAY[0.2, 0.4, 0.6, 0.8]) WITHIN GROUP (ORDER BY density_km2) AS breaks"
    " FROM analytics.hexagons GROUP BY 1, 2",
}


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with geo.lifespan(app):
        for name, (source, title) in LAYERS.items():
            await geo.register_layer(
                source, name=name, title=title, services=LayerServices(mvt=True)
            )
        yield


app = FastAPI(title="DensiMap", lifespan=lifespan)
app.include_router(geo.router)
app.mount("/static", StaticFiles(directory=WEB), name="static")


@app.middleware("http")
async def cache_tiles(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith("/atlas/tiles/") and response.status_code == 200:
        response.headers["Cache-Control"] = f"public, max-age={TILE_MAX_AGE}"
    return response


@app.get("/")
def index():
    return FileResponse(WEB / "index.html")


@app.get("/health")
def health():
    return {"ready": True}


@app.get("/densimap/categories")
async def categories():
    """Catalog and density summary that the map needs to build legends and explanations."""
    rows = {
        key: await geo.context.db.fetch_all(sql.SQL(query))
        for key, query in SUMMARY_QUERIES.items()
    }
    counts: dict[str, dict[str, int]] = defaultdict(dict)
    for row in rows["counts"]:
        counts[row["category"]][row["municipality_code"]] = row["n"]
    hexagons: dict[str, dict[int, dict]] = defaultdict(dict)
    for row in rows["hexagons"]:
        hexagons[row["category"]][row["size_m"]] = {
            "breaks": row["breaks"],
            "max_count": row["max_count"],
            "max_density": row["max_density"],
        }
    run = rows["run"][0] if rows["run"] else {}
    extent = rows["extent"][0] if rows["extent"] else None
    return {
        "study_area": config.study_area,
        "attribution": config.source.attribution,
        "edition": run.get("dataset_version"),
        "loaded_at": run.get("completed_at"),
        "extent": [extent[k] for k in ("minx", "miny", "maxx", "maxy")] if extent else None,
        "hexagon_sizes": config.hexagon_sizes,
        "municipalities": rows["municipalities"],
        "categories": [
            {
                "slug": c.slug,
                "name": c.name,
                "group": c.group,
                "color": c.color,
                "scian": c.scian,
                "total": sum(counts[c.slug].values()),
                "by_municipality": counts[c.slug],
                "hexagons": hexagons[c.slug],
            }
            for c in config.categories
        ],
    }
