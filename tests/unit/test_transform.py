import zipfile
from datetime import date
from pathlib import Path

from densimap.config import DEFAULT_CONFIG, load_config
from densimap.extract import describe, read_rows
from densimap.transform import transform

FIXTURE = Path("tests/fixtures/denue_sample.csv")
CONFIG = load_config(DEFAULT_CONFIG)


def test_fixture_rows_are_selected_by_municipality_and_category():
    result = transform(read_rows(FIXTURE, CONFIG.source), CONFIG)
    assert result.scanned == 9
    accepted = {e.denue_id: e for e in result.accepted}
    # 1004 is naturista (464113, no category) and 1005 is Puerto Vallarta: both skipped.
    assert set(accepted) == {1001, 1002, 1003, 1007, 1008}
    assert accepted[1001].category == "cafeterias"
    assert accepted[1001].name == "CAFÉ DE PRUEBA"
    assert accepted[1001].opened == date(2019, 11, 1)
    assert accepted[1008].name is None
    assert accepted[1008].opened is None
    assert {(r.denue_id, r.reason) for r in result.rejected} == {
        ("1006", "invalid_coordinates"),
        ("1001", "duplicate_id"),
    }


def test_rows_are_read_from_the_bulk_zip(tmp_path: Path):
    archive = tmp_path / "denue_14_csv.zip"
    with zipfile.ZipFile(archive, "w") as handle:
        handle.write(FIXTURE, CONFIG.source.member)
        handle.writestr(
            "metadatos/metadatos_denue.txt",
            "﻿Title: Directorio Estadístico Nacional de Unidades Económicas (DENUE) 05_2026",
        )
    assert describe(archive).dataset_version == "05_2026"
    assert len(list(read_rows(archive, CONFIG.source))) == 9
