CREATE EXTENSION IF NOT EXISTS postgis;

CREATE SCHEMA IF NOT EXISTS meta;
CREATE SCHEMA IF NOT EXISTS staging;
CREATE SCHEMA IF NOT EXISTS analytics;

CREATE TABLE meta.pipeline_runs (
    run_id UUID PRIMARY KEY,
    source TEXT NOT NULL,
    source_file TEXT NOT NULL,
    sha256 CHAR(64) NOT NULL,
    dataset_version TEXT,
    status TEXT NOT NULL CHECK (status IN ('started', 'completed', 'failed')),
    accepted INTEGER,
    rejected INTEGER,
    inserted INTEGER,
    updated INTEGER,
    retired INTEGER,
    started_at TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP,
    completed_at TIMESTAMPTZ
);

-- Rejected DENUE rows of a run, kept for audit with the original record.
CREATE TABLE staging.rejected_records (
    record_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id UUID NOT NULL REFERENCES meta.pipeline_runs (run_id),
    denue_id TEXT,
    category TEXT,
    reason TEXT NOT NULL,
    raw JSONB NOT NULL
);

CREATE TABLE analytics.municipalities (
    code CHAR(3) PRIMARY KEY,
    name TEXT NOT NULL,
    area_km2 DOUBLE PRECISION NOT NULL CHECK (area_km2 > 0),
    geometry GEOMETRY(MultiPolygon, 6368) NOT NULL
);

CREATE INDEX municipalities_geometry_idx ON analytics.municipalities USING GIST (geometry);

CREATE TABLE analytics.establishments (
    denue_id BIGINT PRIMARY KEY,
    category TEXT NOT NULL,
    scian_code CHAR(6) NOT NULL,
    activity TEXT NOT NULL,
    name TEXT,
    legal_name TEXT,
    staff TEXT,
    municipality_code CHAR(3) NOT NULL REFERENCES analytics.municipalities (code),
    municipality TEXT NOT NULL,
    settlement TEXT,
    postal_code TEXT,
    opened DATE,
    geometry GEOMETRY(Point, 4326) NOT NULL,
    run_id UUID NOT NULL REFERENCES meta.pipeline_runs (run_id)
);

CREATE INDEX establishments_geometry_idx ON analytics.establishments USING GIST (geometry);
CREATE INDEX establishments_category_idx ON analytics.establishments (category);

-- Counts per category on hexagonal grids of several edge sizes, rebuilt by every load.
CREATE TABLE analytics.hexagons (
    hexagon_id BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    category TEXT NOT NULL,
    size_m INTEGER NOT NULL CHECK (size_m > 0),
    count INTEGER NOT NULL CHECK (count > 0),
    density_km2 DOUBLE PRECISION NOT NULL,
    geometry GEOMETRY(Polygon, 6368) NOT NULL
);

CREATE INDEX hexagons_geometry_idx ON analytics.hexagons USING GIST (geometry);
CREATE INDEX hexagons_category_size_idx ON analytics.hexagons (category, size_m);

-- Hexagon centroids for proportional symbols; a table so tiles use a spatial index.
CREATE TABLE analytics.hexagon_centers (
    hexagon_id BIGINT PRIMARY KEY REFERENCES analytics.hexagons (hexagon_id) ON DELETE CASCADE,
    category TEXT NOT NULL,
    size_m INTEGER NOT NULL,
    count INTEGER NOT NULL,
    density_km2 DOUBLE PRECISION NOT NULL,
    geometry GEOMETRY(Point, 6368) NOT NULL
);

CREATE INDEX hexagon_centers_geometry_idx ON analytics.hexagon_centers USING GIST (geometry);
CREATE INDEX hexagon_centers_category_size_idx ON analytics.hexagon_centers (category, size_m);
