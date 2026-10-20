import os
from dataclasses import replace
from pathlib import Path

import psycopg
import pytest

from densimap.config import DEFAULT_CONFIG, load_config
from densimap.extract import describe, read_rows
from densimap.load import LoadError, load
from densimap.transform import TransformResult, transform

DATABASE_URL = os.environ.get("DENSIMAP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DENSIMAP_TEST_DATABASE_URL not set")
FIXTURE = Path("tests/fixtures/denue_sample.csv")
CONFIG = load_config(DEFAULT_CONFIG)


@pytest.fixture
def db():
    with psycopg.connect(DATABASE_URL, autocommit=True) as conn:
        conn.execute(
            "TRUNCATE analytics.hexagons, analytics.hexagon_centers, analytics.establishments,"
            " staging.rejected_records, meta.pipeline_runs CASCADE"
        )
        yield conn


def run(result=None):
    snapshot = describe(FIXTURE)
    return load(
        DATABASE_URL,
        CONFIG,
        snapshot,
        result or transform(read_rows(FIXTURE, CONFIG.source), CONFIG),
    )


def test_load_is_idempotent_and_rejects_points_outside_the_zmg(db):
    first = run()
    assert (first.accepted, first.inserted, first.updated, first.retired) == (4, 4, 0, 0)
    reasons = db.execute(
        "SELECT denue_id, reason FROM staging.rejected_records ORDER BY 1"
    ).fetchall()
    assert ("1007", "outside_study_area") in reasons
    second = run()
    assert (second.inserted, second.updated, second.retired) == (0, 0, 0)
    assert db.execute("SELECT count(*) FROM analytics.establishments").fetchone()[0] == 4


def test_absent_establishments_are_retired(db):
    run()
    result = transform(read_rows(FIXTURE, CONFIG.source), CONFIG)
    result.accepted = [e for e in result.accepted if e.denue_id != 1002]
    assert run(result).retired == 1


def test_changed_establishments_are_updated(db):
    run()
    result = transform(read_rows(FIXTURE, CONFIG.source), CONFIG)
    result.accepted = [
        replace(e, name="NUEVO") if e.denue_id == 1001 else e for e in result.accepted
    ]
    assert run(result).updated == 1


def test_every_point_counts_once_per_hexagon_size(db):
    run()
    totals = db.execute(
        "SELECT size_m, sum(count) FROM analytics.hexagons GROUP BY size_m ORDER BY size_m"
    ).fetchall()
    assert totals == [(size, 4) for size in CONFIG.hexagon_sizes]
    centers = db.execute("SELECT count(*) FROM analytics.hexagon_centers").fetchone()[0]
    assert centers == db.execute("SELECT count(*) FROM analytics.hexagons").fetchone()[0]


def test_empty_run_is_refused_and_recorded_as_failed(db):
    run()
    with pytest.raises(LoadError):
        run(TransformResult())
    assert db.execute("SELECT count(*) FROM analytics.establishments").fetchone()[0] == 4
    statuses = db.execute("SELECT status FROM meta.pipeline_runs ORDER BY started_at").fetchall()
    assert statuses[-1] == ("failed",)
