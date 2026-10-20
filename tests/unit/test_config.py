from pathlib import Path

import pytest

from densimap.config import DEFAULT_CONFIG, ConfigurationError, load_config


def test_project_config_loads_nine_categories():
    config = load_config(DEFAULT_CONFIG)
    assert len(config.categories) == 9
    assert config.municipality_codes >= {"039", "120", "098", "097"}


@pytest.mark.parametrize(
    ("scian", "slug"),
    [
        ("722515", "cafeterias"),
        ("722514", "restaurantes"),
        ("464112", "farmacias"),
        ("713944", "gimnasios"),
        ("464113", None),
        ("112515", None),
    ],
)
def test_category_matching_uses_prefixes_and_exclusions(scian, slug):
    category = load_config(DEFAULT_CONFIG).category_for(scian)
    assert (category.slug if category else None) == slug


def test_overlapping_categories_are_rejected(tmp_path: Path):
    text = DEFAULT_CONFIG.read_text(encoding="utf-8").replace('exclude: ["722515"]', "exclude: []")
    path = tmp_path / "densimap.yaml"
    path.write_text(text, encoding="utf-8")
    with pytest.raises(ConfigurationError, match="overlap"):
        load_config(path)
