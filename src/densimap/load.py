"""Persist a run in PostGIS: idempotent establishments plus rebuilt hexagon aggregates."""

import json
import uuid
from dataclasses import dataclass
from pathlib import Path

import psycopg
from psycopg.types.json import Jsonb

from densimap.config import Config
from densimap.extract import Snapshot
from densimap.transform import TransformResult

COLUMNS = (
    "denue_id",
    "category",
    "scian_code",
    "activity",
    "name",
    "legal_name",
    "staff",
    "municipality_code",
    "municipality",
    "settlement",
    "postal_code",
    "opened",
)
ASSIGNMENTS = ", ".join(f"{column} = EXCLUDED.{column}" for column in COLUMNS[1:])
CHANGED = (
    f"({', '.join('e.' + c for c in COLUMNS[1:])}, ST_AsBinary(e.geometry))"
    f" IS DISTINCT FROM ({', '.join('EXCLUDED.' + c for c in COLUMNS[1:])},"
    " ST_AsBinary(EXCLUDED.geometry))"
)

UPSERT_MUNICIPALITY = """
INSERT INTO analytics.municipalities (code, name, area_km2, geometry)
VALUES (%s, %s, %s, ST_Multi(ST_Transform(ST_SetSRID(ST_GeomFromGeoJSON(%s), 4326), 6368)))
ON CONFLICT (code) DO UPDATE
SET name = EXCLUDED.name, area_km2 = EXCLUDED.area_km2, geometry = EXCLUDED.geometry
"""

# DENUE assigns a municipality code, but its coordinates can still fall outside the ZMG.
REJECT_OUTSIDE = """
WITH outside AS (
    DELETE FROM incoming AS i
    WHERE NOT EXISTS (
        SELECT 1 FROM analytics.municipalities AS m
        WHERE ST_Intersects(m.geometry, ST_Transform(ST_SetSRID(ST_MakePoint(i.longitude, i.latitude), 4326), 6368))
    )
    RETURNING i.*
)
INSERT INTO staging.rejected_records (run_id, denue_id, category, reason, raw)
SELECT %s, denue_id::text, category, 'outside_study_area', to_jsonb(outside) FROM outside
"""

UPSERT_ESTABLISHMENTS = f"""
INSERT INTO analytics.establishments AS e ({", ".join(COLUMNS)}, geometry, run_id)
SELECT {", ".join(COLUMNS)}, ST_SetSRID(ST_MakePoint(longitude, latitude), 4326), %s
FROM incoming
ON CONFLICT (denue_id) DO UPDATE
SET {ASSIGNMENTS}, geometry = EXCLUDED.geometry, run_id = EXCLUDED.run_id
WHERE {CHANGED}
RETURNING (xmax = 0) AS inserted
"""

RETIRE_ABSENT = """
DELETE FROM analytics.establishments AS e
WHERE NOT EXISTS (SELECT 1 FROM incoming AS i WHERE i.denue_id = e.denue_id)
"""

# Each point falls in exactly one cell: ties on shared edges go to the lowest (i, j).
BUILD_HEXAGONS = """
INSERT INTO analytics.hexagons (category, size_m, count, density_km2, geometry)
SELECT category, size_m, count(*), count(*) / (ST_Area(hexagon) / 1e6), hexagon
FROM (
    SELECT e.category, s.size_m,
           ST_SetSRID(ST_Hexagon(s.size_m, cell.i, cell.j), 6368) AS hexagon
    FROM analytics.establishments AS e
    CROSS JOIN unnest(%s::integer[]) AS s(size_m)
    CROSS JOIN LATERAL (
        SELECT g.i, g.j FROM ST_HexagonGrid(s.size_m, ST_Transform(e.geometry, 6368)) AS g
        ORDER BY g.i, g.j LIMIT 1
    ) AS cell
) AS cells
GROUP BY category, size_m, hexagon
"""

BUILD_CENTERS = """
INSERT INTO analytics.hexagon_centers (hexagon_id, category, size_m, count, density_km2, geometry)
SELECT hexagon_id, category, size_m, count, density_km2, ST_Centroid(geometry)
FROM analytics.hexagons
"""


class LoadError(RuntimeError):
    """Raised when a run cannot be persisted; the analytics layer is left untouched."""


@dataclass(frozen=True, slots=True)
class LoadMetrics:
    run_id: str
    accepted: int
    rejected: int
    inserted: int
    updated: int
    retired: int
    hexagons: int


def load(
    database_url: str, config: Config, snapshot: Snapshot, result: TransformResult
) -> LoadMetrics:
    run_id = str(uuid.uuid4())
    try:
        with psycopg.connect(database_url) as conn, conn.transaction():
            return _load(conn, run_id, config, snapshot, result)
    except (psycopg.Error, LoadError) as error:
        with psycopg.connect(database_url) as conn:
            _start_run(conn, run_id, config, snapshot, status="failed")
        raise LoadError(f"Run {run_id} failed: {error}") from error


def _start_run(
    conn: psycopg.Connection, run_id: str, config: Config, snapshot: Snapshot, *, status: str
) -> None:
    conn.execute(
        "INSERT INTO meta.pipeline_runs (run_id, source, source_file, sha256, dataset_version,"
        " status, completed_at) VALUES (%s, %s, %s, %s, %s, %s,"
        " CASE WHEN %s = 'failed' THEN CURRENT_TIMESTAMP END)",
        (
            run_id,
            config.source.name,
            snapshot.path.name,
            snapshot.sha256,
            snapshot.dataset_version,
            status,
            status,
        ),
    )


def _load(
    conn: psycopg.Connection,
    run_id: str,
    config: Config,
    snapshot: Snapshot,
    result: TransformResult,
) -> LoadMetrics:
    _start_run(conn, run_id, config, snapshot, status="started")
    _load_municipalities(conn, config)
    conn.execute(
        "CREATE TEMP TABLE incoming ON COMMIT DROP AS"
        f" SELECT {', '.join(COLUMNS)}, 0::float8 AS longitude, 0::float8 AS latitude"
        " FROM analytics.establishments WITH NO DATA"
    )
    with conn.cursor().copy(
        f"COPY incoming ({', '.join(COLUMNS)}, longitude, latitude) FROM STDIN"
    ) as copy:
        for e in result.accepted:
            copy.write_row([getattr(e, c) for c in COLUMNS] + [e.longitude, e.latitude])
    outside = conn.execute(REJECT_OUTSIDE, (run_id,)).rowcount
    with conn.cursor() as cur:
        cur.executemany(
            "INSERT INTO staging.rejected_records (run_id, denue_id, category, reason, raw)"
            " VALUES (%s, %s, %s, %s, %s)",
            [(run_id, r.denue_id, r.category, r.reason, Jsonb(r.raw)) for r in result.rejected],
        )
    accepted = len(result.accepted) - outside
    if accepted == 0:
        # An empty or broken snapshot must never retire the whole analytics layer.
        raise LoadError("no accepted establishments; refusing to replace analytics")
    flags = [row[0] for row in conn.execute(UPSERT_ESTABLISHMENTS, (run_id,)).fetchall()]
    retired = conn.execute(RETIRE_ABSENT).rowcount
    conn.execute("DELETE FROM analytics.hexagons")
    hexagons = conn.execute(BUILD_HEXAGONS, (list(config.hexagon_sizes),)).rowcount
    conn.execute(BUILD_CENTERS)
    metrics = LoadMetrics(
        run_id=run_id,
        accepted=accepted,
        rejected=len(result.rejected) + outside,
        inserted=sum(flags),
        updated=len(flags) - sum(flags),
        retired=retired,
        hexagons=hexagons,
    )
    conn.execute(
        "UPDATE meta.pipeline_runs SET status = 'completed', completed_at = CURRENT_TIMESTAMP,"
        " accepted = %s, rejected = %s, inserted = %s, updated = %s, retired = %s"
        " WHERE run_id = %s",
        (
            metrics.accepted,
            metrics.rejected,
            metrics.inserted,
            metrics.updated,
            metrics.retired,
            run_id,
        ),
    )
    return metrics


def _load_municipalities(conn: psycopg.Connection, config: Config) -> None:
    features = json.loads(Path(config.boundaries).read_text(encoding="utf-8"))["features"]
    codes = {f["properties"]["code"] for f in features}
    missing = config.municipality_codes - codes
    if missing:
        raise LoadError(f"boundaries lack municipalities {sorted(missing)}")
    with conn.cursor() as cur:
        cur.executemany(
            UPSERT_MUNICIPALITY,
            [
                (p["code"], p["name"], p["area_km2"], json.dumps(f["geometry"]))
                for f in features
                if (p := f["properties"])["code"] in config.municipality_codes
            ],
        )
