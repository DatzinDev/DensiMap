"""Snapshot the DENUE bulk download and stream its rows."""

import csv
import hashlib
import io
import json
import re
import shutil
import time
import urllib.request
import zipfile
from collections.abc import Iterator
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path

from densimap.config import Source

RAW_DIR = Path("data/raw")


class ExtractionError(RuntimeError):
    """Raised when the DENUE snapshot cannot be obtained or read."""


@dataclass(frozen=True, slots=True)
class Snapshot:
    path: Path
    sha256: str
    retrieved_at: str
    dataset_version: str | None


def download(source: Source, raw_dir: Path = RAW_DIR) -> Snapshot:
    """Download the bulk zip into a dated folder; the file is kept as the raw snapshot."""
    retrieved_at = datetime.now(UTC)
    target = raw_dir / retrieved_at.strftime("%Y-%m-%dT%H%M%SZ") / Path(source.url).name
    target.parent.mkdir(parents=True, exist_ok=True)
    for attempt in range(source.max_retries + 1):
        try:
            with (
                urllib.request.urlopen(source.url, timeout=source.timeout_seconds) as response,
                target.open("wb") as output,
            ):
                shutil.copyfileobj(response, output)
            break
        except OSError as error:
            if attempt == source.max_retries:
                raise ExtractionError(f"Could not download {source.url}: {error}") from error
            time.sleep(source.retry_backoff_seconds * (attempt + 1))
    snapshot = describe(target, retrieved_at)
    metadata = {**asdict(snapshot), "path": str(target), "url": source.url}
    target.with_name("metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    return snapshot


def describe(path: Path, retrieved_at: datetime | None = None) -> Snapshot:
    """Identify an existing snapshot (offline mode) by content hash and DENUE edition."""
    if not path.is_file():
        raise ExtractionError(f"Snapshot not found: {path}")
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1 << 20), b""):
            digest.update(block)
    stamp = retrieved_at or datetime.fromtimestamp(path.stat().st_mtime, UTC)
    return Snapshot(path, digest.hexdigest(), stamp.isoformat(), _dataset_version(path))


def _dataset_version(path: Path) -> str | None:
    if not zipfile.is_zipfile(path):
        return None
    with zipfile.ZipFile(path) as archive:
        name = next((n for n in archive.namelist() if n.startswith("metadatos/")), None)
        if name is None:
            return None
        text = archive.read(name).decode("utf-8", "replace")
    match = re.search(r"\(DENUE\)\s+(\d{2}_\d{4})", text)
    return match.group(1) if match else None


def read_rows(path: Path, source: Source) -> Iterator[dict[str, str]]:
    """Yield DENUE rows from the bulk zip, or from a plain CSV (test fixtures)."""
    if zipfile.is_zipfile(path):
        with zipfile.ZipFile(path) as archive, archive.open(source.member) as member:
            yield from csv.DictReader(
                io.TextIOWrapper(member, encoding=source.encoding, newline="")
            )
    else:
        with path.open(encoding=source.encoding, newline="") as handle:
            yield from csv.DictReader(handle)
