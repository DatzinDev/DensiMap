"""Load and validate the non-secret DensiMap configuration."""

import re
from dataclasses import dataclass
from pathlib import Path

import yaml

DEFAULT_CONFIG = Path("config/densimap.yaml")


class ConfigurationError(ValueError):
    """Raised when the configuration is incomplete or invalid."""


@dataclass(frozen=True, slots=True)
class Municipality:
    code: str
    name: str


@dataclass(frozen=True, slots=True)
class Category:
    slug: str
    name: str
    group: str
    color: str
    scian: tuple[str, ...]
    exclude: tuple[str, ...] = ()

    def matches(self, scian_code: str) -> bool:
        return scian_code.startswith(self.scian) and not scian_code.startswith(self.exclude)


@dataclass(frozen=True, slots=True)
class Source:
    name: str
    url: str
    member: str
    encoding: str
    attribution: str
    license: str
    timeout_seconds: float
    max_retries: int
    retry_backoff_seconds: float


@dataclass(frozen=True, slots=True)
class Config:
    study_area: str
    municipalities: tuple[Municipality, ...]
    boundaries: Path
    source: Source
    hexagon_sizes: tuple[int, ...]
    categories: tuple[Category, ...]

    def category_for(self, scian_code: str) -> Category | None:
        return next((c for c in self.categories if c.matches(scian_code)), None)

    @property
    def municipality_codes(self) -> frozenset[str]:
        return frozenset(m.code for m in self.municipalities)


def load_config(path: Path = DEFAULT_CONFIG) -> Config:
    try:
        document = yaml.safe_load(path.read_text(encoding="utf-8"))
        area = document["study_area"]
        config = Config(
            study_area=str(area["name"]),
            municipalities=tuple(
                Municipality(code=str(m["code"]), name=str(m["name"]))
                for m in area["municipalities"]
            ),
            boundaries=Path(area["boundaries"]),
            source=Source(**document["source"]),
            hexagon_sizes=tuple(int(size) for size in document["hexagon_sizes"]),
            categories=tuple(
                Category(
                    slug=str(c["slug"]),
                    name=str(c["name"]),
                    group=str(c["group"]),
                    color=str(c["color"]),
                    scian=tuple(str(code) for code in c["scian"]),
                    exclude=tuple(str(code) for code in c.get("exclude", ())),
                )
                for c in document["categories"]
            ),
        )
    except (OSError, yaml.YAMLError, KeyError, TypeError, ValueError) as error:
        raise ConfigurationError(f"Invalid configuration {path}: {error}") from error
    _validate(config)
    return config


def _validate(config: Config) -> None:
    if not config.municipalities or not config.categories or not config.hexagon_sizes:
        raise ConfigurationError("municipalities, categories and hexagon_sizes are required")
    if any(not re.fullmatch(r"\d{3}", m.code) for m in config.municipalities):
        raise ConfigurationError("municipality codes must be three digits")
    if any(size <= 0 for size in config.hexagon_sizes):
        raise ConfigurationError("hexagon sizes must be positive")
    slugs = [c.slug for c in config.categories]
    if len(set(slugs)) != len(slugs):
        raise ConfigurationError("category slugs must be unique")
    for category in config.categories:
        if not re.fullmatch(r"[a-z][a-z0-9_]*", category.slug):
            raise ConfigurationError(f"invalid category slug: {category.slug}")
        if not re.fullmatch(r"#[0-9a-fA-F]{6}", category.color):
            raise ConfigurationError(f"invalid color for {category.slug}")
        if not category.scian or any(
            not re.fullmatch(r"\d{2,6}", code) for code in category.scian + category.exclude
        ):
            raise ConfigurationError(f"invalid SCIAN codes for {category.slug}")
        # Overlap: a prefix of this category that another category would also accept.
        for other in config.categories:
            if other is not category and any(other.matches(code) for code in category.scian):
                raise ConfigurationError(f"categories {category.slug} and {other.slug} overlap")
