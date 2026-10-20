"""Select ZMG establishments of the configured categories from raw DENUE rows."""

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from datetime import date
from math import isfinite

from densimap.config import Config


@dataclass(frozen=True, slots=True)
class Establishment:
    denue_id: int
    category: str
    scian_code: str
    activity: str
    name: str | None
    legal_name: str | None
    staff: str | None
    municipality_code: str
    municipality: str
    settlement: str | None
    postal_code: str | None
    opened: date | None
    longitude: float
    latitude: float


@dataclass(frozen=True, slots=True)
class Rejection:
    denue_id: str | None
    category: str | None
    reason: str
    raw: dict[str, str]


@dataclass(slots=True)
class TransformResult:
    accepted: list[Establishment] = field(default_factory=list)
    rejected: list[Rejection] = field(default_factory=list)
    scanned: int = 0


def transform(rows: Iterable[dict[str, str]], config: Config) -> TransformResult:
    """Rows outside the ZMG or the categories are skipped; matching rows are accepted or rejected."""
    result = TransformResult()
    municipalities = config.municipality_codes
    seen: set[int] = set()
    for row in rows:
        result.scanned += 1
        if _text(row.get("cve_mun")) not in municipalities:
            continue
        scian_code = _text(row.get("codigo_act")) or ""
        category = config.category_for(scian_code)
        if category is None:
            continue
        denue_id = _text(row.get("id"))
        reason = None
        if denue_id is None or not denue_id.isdigit():
            reason = "invalid_id"
        elif int(denue_id) in seen:
            reason = "duplicate_id"
        coordinates = _coordinates(row)
        if reason is None and coordinates is None:
            reason = "invalid_coordinates"
        if reason is not None:
            result.rejected.append(Rejection(denue_id, category.slug, reason, dict(row)))
            continue
        seen.add(int(denue_id))
        longitude, latitude = coordinates
        result.accepted.append(
            Establishment(
                denue_id=int(denue_id),
                category=category.slug,
                scian_code=scian_code,
                activity=_text(row.get("nombre_act")) or scian_code,
                name=_text(row.get("nom_estab")),
                legal_name=_text(row.get("raz_social")),
                staff=_text(row.get("per_ocu")),
                municipality_code=row["cve_mun"].strip(),
                municipality=_text(row.get("municipio")) or "",
                settlement=_text(row.get("nomb_asent")),
                postal_code=_text(row.get("cod_postal")),
                opened=_month(row.get("fecha_alta")),
                longitude=longitude,
                latitude=latitude,
            )
        )
    return result


def _text(value: str | None) -> str | None:
    value = (value or "").strip()
    return value or None


def _coordinates(row: dict[str, str]) -> tuple[float, float] | None:
    try:
        longitude, latitude = float(row["longitud"]), float(row["latitud"])
    except (KeyError, TypeError, ValueError):
        return None
    if not (isfinite(longitude) and isfinite(latitude)):
        return None
    if not (-180 <= longitude <= 180 and -90 <= latitude <= 90) or (longitude, latitude) == (0, 0):
        return None
    return longitude, latitude


def _month(value: str | None) -> date | None:
    """DENUE `fecha_alta` is YYYY-MM; anything else stays unknown, never invented."""
    match = re.fullmatch(r"(\d{4})-(\d{2})", (value or "").strip())
    if not match or not 1 <= int(match.group(2)) <= 12:
        return None
    return date(int(match.group(1)), int(match.group(2)), 1)
