"""Opt-in SHADOW Base worker entrypoint. Never modifies Supabase or other services.

Run only after the DB query/index preflight and operator approval. The durable
production signal/event store is a separate milestone; JSONL is local shadow
telemetry, never a user-facing confirmed signal source.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
from uuid import UUID

from .journal import CheckpointJsonlJournal
from .reader import SnapshotReadError, SupabaseMoneywayReader, _parse_time, _iso
from .scheduler import FixtureRef, process_due_jobs


class CatalogReadError(RuntimeError):
    pass


class SupabaseFixtureCatalog:
    """Bounded, paginated UID-based public fixture discovery; GET only."""

    def __init__(self, reader: SupabaseMoneywayReader, *, page_size: int = 500,
                 max_pages: int = 100):
        if not 1 <= page_size <= 1000 or max_pages < 1:
            raise ValueError("invalid fixture pagination")
        self.reader, self.page_size, self.max_pages = reader, page_size, max_pages

    def list_between(self, start: datetime, end: datetime, *,
                     progress_hook: Callable[[], None] | None = None) -> list[FixtureRef]:
        if start.tzinfo is None or end.tzinfo is None or start >= end:
            raise ValueError("invalid fixture time window")
        fixtures: dict[str, FixtureRef] = {}
        for page in range(self.max_pages):
            if progress_hook is not None:
                progress_hook()
            rows = self.reader._get("fixtures", [
                ("select", "fixture_uid,match_id_hash,kickoff_utc"),
                ("kickoff_utc", "gte." + _iso(start)),
                ("kickoff_utc", "lte." + _iso(end)),
                ("order", "kickoff_utc.asc,fixture_uid.asc"),
                ("limit", str(self.page_size)),
                ("offset", str(page * self.page_size)),
            ])
            for row in rows:
                try:
                    uid = str(UUID(str(row["fixture_uid"])))
                    kick = _parse_time(row["kickoff_utc"])
                    if not start <= kick <= end:
                        raise ValueError("kickoff outside window")
                    fixture = FixtureRef(uid, kick, str(row.get("match_id_hash") or ""))
                except (ValueError, TypeError, KeyError) as exc:
                    raise CatalogReadError("invalid fixture discovery row") from exc
                if uid in fixtures:
                    raise CatalogReadError("fixture UID duplicated across pages")
                fixtures[uid] = fixture
            if len(rows) < self.page_size:
                return sorted(fixtures.values(), key=lambda f: (f.kickoff_utc, f.fixture_uid))
        raise CatalogReadError("fixture pagination cap reached; cannot infer complete universe")


def scan_once(reader: SupabaseMoneywayReader, journal: CheckpointJsonlJournal,
              *, now: datetime | None = None, max_jobs: int = 25,
              backfill_days: int = 3, catalog: Any = None) -> dict:
    """Batch-limited scan. Re-list past fixtures on every cycle; journal skips done.

    Backfill horizon is explicit. It is not a guarantee beyond this period:
    production requires database-backed checkpoint queue and stronger indexing.
    """
    at = now or datetime.now(timezone.utc)
    if not 1 <= backfill_days <= 30 or not 1 <= max_jobs <= 200:
        raise ValueError("invalid shadow scan bounds")
    catalog = catalog or SupabaseFixtureCatalog(reader)
    fixtures = catalog.list_between(at - timedelta(days=backfill_days), at + timedelta(hours=74))
    stats = process_due_jobs(fixtures, at, reader, journal, limit=max_jobs)
    stats["fixtures_discovered"] = len(fixtures)
    stats["shadow_only"] = True
    return stats


def run_forever(reader, journal, *, interval_seconds: int = 30, max_jobs: int = 25,
                backfill_days: int = 3, sleep=time.sleep, clock=None):
    if not 15 <= interval_seconds <= 3600:
        raise ValueError("poll interval outside safety bounds")
    clock = clock or (lambda: datetime.now(timezone.utc))
    while True:
        started = time.monotonic()
        try:
            result = scan_once(reader, journal, now=clock(), max_jobs=max_jobs,
                               backfill_days=backfill_days)
            print(json.dumps({"status": "SHADOW_SCAN", **result}, sort_keys=True), flush=True)
        except Exception as exc:
            # Deliberately only class name, never URLs, auth headers or tokens.
            print(json.dumps({"status": "SHADOW_ERROR", "type": type(exc).__name__}),
                  file=sys.stderr, flush=True)
        sleep(max(0, interval_seconds - (time.monotonic() - started)))


def main(argv=None):
    parser = argparse.ArgumentParser(description="SXF Base shadow checkpoint worker")
    parser.add_argument("--once", action="store_true", help="one bounded dry-run cycle")
    parser.add_argument("--journal", required=True, help="local append-only shadow JSONL file")
    parser.add_argument("--backfill-days", type=int, default=3)
    parser.add_argument("--max-jobs", type=int, default=25)
    args = parser.parse_args(argv)
    if os.environ.get("SXF_BASE_SHADOW_SCAN_APPROVED") != "yes":
        parser.error("shadow scan disabled: SXF_BASE_SHADOW_SCAN_APPROVED=yes required")
    if os.environ.get("SXF_BASE_COMPOSITE_INDEX_VERIFIED") != "yes":
        parser.error("index/load preflight required: SXF_BASE_COMPOSITE_INDEX_VERIFIED=yes")
    base = os.environ.get("SUPABASE_URL", "")
    credential = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base or not credential:
        parser.error("server-only Supabase credentials required")
    reader = SupabaseMoneywayReader(base, credential)
    journal = CheckpointJsonlJournal(args.journal)
    if args.once:
        print(json.dumps(scan_once(reader, journal, max_jobs=args.max_jobs,
                                   backfill_days=args.backfill_days), sort_keys=True))
    else:
        run_forever(reader, journal, max_jobs=args.max_jobs, backfill_days=args.backfill_days)


if __name__ == "__main__":  # pragma: no cover
    main()
