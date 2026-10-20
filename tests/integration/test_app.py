import json
import os
from pathlib import Path

import pytest

from densimap.config import DEFAULT_CONFIG, load_config
from densimap.extract import describe, read_rows
from densimap.load import load
from densimap.transform import transform

DATABASE_URL = os.environ.get("DENSIMAP_TEST_DATABASE_URL")
pytestmark = pytest.mark.skipif(not DATABASE_URL, reason="DENSIMAP_TEST_DATABASE_URL not set")
FIXTURE = Path("tests/fixtures/denue_sample.csv")


@pytest.fixture(scope="module")
def client():
    from fastapi.testclient import TestClient

    config = load_config(DEFAULT_CONFIG)
    load(
        DATABASE_URL,
        config,
        describe(FIXTURE),
        transform(read_rows(FIXTURE, config.source), config),
    )
    os.environ["DATABASE_URL"] = DATABASE_URL
    from app.main import app

    with TestClient(app) as test_client:
        yield test_client


def test_summary_explains_each_category(client):
    body = client.get("/densimap/categories").json()
    cafeterias = next(c for c in body["categories"] if c["slug"] == "cafeterias")
    assert cafeterias["total"] == 1
    assert cafeterias["by_municipality"] == {"039": 1}
    assert set(cafeterias["hexagons"]) == {"250", "500", "1000", "2000"}
    assert len(body["municipalities"]) == 9
    assert body["extent"][0] < -103 < body["extent"][2]


@pytest.mark.parametrize(
    "layer", ["establishments", "hexagons", "hexagon_centers", "municipalities"]
)
def test_layers_are_served_as_cacheable_vector_tiles(client, layer):
    predicate = json.dumps({"op": "eq", "field": "category", "value": "cafeterias"})
    params = {} if layer == "municipalities" else {"ATLAS_FILTER": predicate}
    response = client.get(f"/atlas/tiles/{layer}/10/217/451.mvt", params=params)
    assert response.status_code == 200
    assert response.headers["content-type"] == "application/vnd.mapbox-vector-tile"
    assert response.headers["cache-control"].startswith("public, max-age=")
    assert response.content
