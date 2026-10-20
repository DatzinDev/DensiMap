"""Command line: python -m densimap [--offline PATH] [--database-url URL]."""

import argparse
import os
import sys
from collections import Counter
from pathlib import Path

from densimap.config import DEFAULT_CONFIG, ConfigurationError, load_config
from densimap.extract import ExtractionError, describe, download, read_rows
from densimap.load import LoadError, load
from densimap.transform import transform


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="densimap", description=__doc__)
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    parser.add_argument(
        "--offline", type=Path, help="existing DENUE zip or CSV instead of downloading"
    )
    parser.add_argument("--database-url", default=os.environ.get("DATABASE_URL"))
    args = parser.parse_args(argv)
    try:
        config = load_config(args.config)
        snapshot = describe(args.offline) if args.offline else download(config.source)
        result = transform(read_rows(snapshot.path, config.source), config)
    except (ConfigurationError, ExtractionError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"snapshot {snapshot.path} sha256={snapshot.sha256[:12]} edition={snapshot.dataset_version}"
    )
    print(
        f"scanned={result.scanned} accepted={len(result.accepted)} rejected={len(result.rejected)}"
    )
    for slug, count in Counter(e.category for e in result.accepted).most_common():
        print(f"  {slug}: {count}")
    if not args.database_url:
        return 0
    try:
        metrics = load(args.database_url, config, snapshot, result)
    except LoadError as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    print(
        f"run {metrics.run_id}: accepted={metrics.accepted} rejected={metrics.rejected}"
        f" inserted={metrics.inserted} updated={metrics.updated} retired={metrics.retired}"
        f" hexagons={metrics.hexagons}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
