#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys

from learning_archive.bootstrap import ArchiveBootstrapError, bootstrap_archive_repository


def main() -> int:
    schema = Path("schemas/learning_archive_match_v1.schema.json")
    if not schema.exists():
        print(f"FAIL missing schema: {schema}", file=sys.stderr)
        return 2
    try:
        commit = bootstrap_archive_repository(schema.read_bytes())
    except ArchiveBootstrapError as exc:
        print(f"FAIL archive bootstrap: {exc}", file=sys.stderr)
        return 1
    print(commit)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
