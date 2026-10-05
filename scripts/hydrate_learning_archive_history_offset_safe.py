#!/usr/bin/env python3
"""Run historical Learning Archive hydration with offset-safe timestamp reads.

Legacy SXF history tables store ``scraped_at`` as ISO text with explicit offsets.
PostgREST text comparisons against a UTC ``Z`` cutoff are therefore not a safe
chronological filter. This runner imports the canonical hydrator, replaces only
its Supabase history reader, fetches rows by fixture identity, parses timestamps
client-side, and applies the strict pre-kickoff cutoff as timezone-aware datetimes.
"""
from __future__ import annotations

import argparse
import importlib.util
import json
from pathlib import Path
import sys
from typing import Any


def _load_hydrator(path: Path):
    spec = importlib.util.spec_from_file_location("sxf_historical_hydrator", path)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"cannot load hydrator: {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def run(hydrator_path: Path, request_path: Path, dotenv: Path) -> dict[str, Any]:
    h = _load_hydrator(hydrator_path)

    class OffsetSafeSupabaseSource(h.SupabaseSource):
        def table_history(self, table, timestamp_field, match_hash, kickoff_at):
            # IMPORTANT: scraped_at is text in legacy history tables. Do not send
            # a UTC-Z text cutoff to PostgREST; offsets such as +03:00 would be
            # compared lexicographically and valid rows could be dropped.
            raw_rows = []
            offset = 0
            while True:
                page = self._get(table, {
                    "select": "*",
                    "match_id_hash": f"eq.{match_hash}",
                    "order": f"{timestamp_field}.asc",
                    "limit": str(h.PAGE_SIZE),
                    "offset": str(offset),
                })
                raw_rows.extend(page)
                if len(raw_rows) > h.MAX_ROWS_PER_TABLE:
                    raise h.HydrationError(
                        f"{table} exceeded safety row limit for {match_hash}"
                    )
                if len(page) < h.PAGE_SIZE:
                    break
                offset += h.PAGE_SIZE

            rows = []
            for row in raw_rows:
                ts = h._row_timestamp(row)
                if ts < kickoff_at:
                    rows.append(row)
            rows.sort(key=lambda row: (
                h._row_timestamp(row),
                str(row.get("id") or ""),
            ))
            return rows

    h.SupabaseSource = OffsetSafeSupabaseSource
    h._load_dotenv_literal(dotenv)
    return h.hydrate(request_path)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("request")
    parser.add_argument("--hydrator", required=True)
    parser.add_argument("--dotenv", default="/opt/smartxflow/.env")
    args = parser.parse_args()
    try:
        result = run(Path(args.hydrator), Path(args.request), Path(args.dotenv))
    except Exception as exc:
        print(json.dumps({"status": "FAILED", "error": str(exc)}, ensure_ascii=False), flush=True)
        return 1
    print(json.dumps(result, ensure_ascii=False, sort_keys=True), flush=True)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
