#!/usr/bin/env python3
"""Append-only, physical-fixture-keyed backfill for the 2026-10-05..08 gap.

DEFAULT MODE IS READ ONLY. Generates and runs bounded JSON planner SQL.
Only an explicit --apply plus a separate exact environment authorization can
INSERT into research_archive.fixtures. Never edits/deletes existing rows.
It neither copies market history nor authorizes any retention cleanup.

Uses the existing psql PGHOST/PGDATABASE/PGUSER/PGPASSWORD configuration.
Do NOT pass database credentials as CLI arguments.
"""
from __future__ import annotations

import argparse
from datetime import date
import json
import os
import subprocess
import sys

FIRST_DAY = date(2026, 10, 5)
LAST_DAY = date(2026, 10, 8)
MAX_BATCH = 25
APPROVAL_ENV = "SMARTXFLOW_ARCHIVE_FIXTURE_BACKFILL_APPROVED"
APPROVAL_VALUE = "append-only-legacy-fixture-backfill-2026-10-05-08"

# The exact same physical fixture selection is used for planning and insertion.
# All interpolated inputs are validated dates or range-limited integers.
def validate(day: str, after_id: int, limit: int) -> str:
    try:
        parsed = date.fromisoformat(day)
    except (TypeError, ValueError) as exc:
        raise ValueError("ISO calendar date required") from exc
    if not FIRST_DAY <= parsed <= LAST_DAY:
        raise ValueError("Only October 5-8, 2026 archive gap is eligible")
    if not isinstance(after_id, int) or after_id < 0:
        raise ValueError("after-id must be a nonnegative integer")
    if not isinstance(limit, int) or not 1 <= limit <= MAX_BATCH:
        raise ValueError("limit must be between 1 and 25")
    return parsed.isoformat()


def selected_sql(day: str, after_id: int, limit: int) -> str:
    return f"""SELECT s.internal_id,s.fixture_uid,s.match_id_hash,s.home_team,
                   s.away_team,s.league,s.kickoff_utc,s.fixture_date,s.created_at,
                   (s.kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date AS local_date
            FROM public.fixtures s
            WHERE s.internal_id > {after_id}
              AND s.kickoff_utc >= ('{day}'::date::timestamp AT TIME ZONE 'Europe/Istanbul')
              AND s.kickoff_utc <  (('{day}'::date+1)::timestamp AT TIME ZONE 'Europe/Istanbul')
            ORDER BY s.internal_id ASC LIMIT {limit}"""


def conflict_condition() -> str:
    # A row with the same source ID but a different physical identity is an
    # immutable conflict; a shared UID with another source ID is also unsafe.
    # Do NOT use match_id_hash alone: collisions are present in live data.
    return """EXISTS (
              SELECT 1 FROM research_archive.fixtures a
              WHERE (a.source_internal_id=s.internal_id AND (
                  a.fixture_uid IS DISTINCT FROM s.fixture_uid
                  OR a.kickoff_utc IS DISTINCT FROM s.kickoff_utc
                  OR a.local_date IS DISTINCT FROM s.local_date
                  OR a.match_id_hash IS DISTINCT FROM s.match_id_hash
                  OR a.home_team IS DISTINCT FROM s.home_team
                  OR a.away_team IS DISTINCT FROM s.away_team
                  OR a.league IS DISTINCT FROM s.league
                  OR a.source_fixture_date IS DISTINCT FROM s.fixture_date
              )) OR (a.fixture_uid=s.fixture_uid AND a.source_internal_id<>s.internal_id)
            )"""


def plan_sql(day: str, after_id: int, limit: int) -> str:
    day = validate(day, after_id, limit)
    select = selected_sql(day, after_id, limit)
    return f"""BEGIN TRANSACTION READ ONLY;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='1s';
WITH selected AS MATERIALIZED ({select}),
checks AS MATERIALIZED (
 SELECT s.internal_id,s.fixture_uid,
   ({conflict_condition()}) AS conflict,
   EXISTS (SELECT 1 FROM research_archive.fixtures a
           WHERE a.source_internal_id=s.internal_id) AS already_archived
 FROM selected s
)
SELECT jsonb_build_object(
 'mode','READ_ONLY',
 'day','{day}',
 'after_id',{after_id},
 'batch_limit',{limit},
 'selected',COUNT(*),
 'already_archived',COUNT(*) FILTER (WHERE already_archived),
 'not_archived',COUNT(*) FILTER (WHERE NOT already_archived AND NOT conflict),
 'conflicts',COUNT(*) FILTER (WHERE conflict),
 'next_after_id',COALESCE(MAX(internal_id),{after_id}),
 'has_more',COUNT(*)={limit},
 'archive_parity_proven',false,
 'cold_backup_verified',false,
 'retention_cleanup_allowed',false
)::text FROM checks;
COMMIT;"""


def apply_sql(day: str, after_id: int, limit: int) -> str:
    """Return a bounded INSERT-only transaction, never run during dry-run."""
    day = validate(day, after_id, limit)
    select = selected_sql(day, after_id, limit)
    collision = conflict_condition()
    # Repeatable read makes the identical source selection stable between the
    # collision guard and INSERT, and an advisory lock serializes THIS writer.
    return f"""BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ;
SET LOCAL statement_timeout='8s';
SET LOCAL lock_timeout='1s';
SELECT pg_advisory_xact_lock(740621,20261005);
DO $sxf_guard$
BEGIN
  IF EXISTS(
    WITH selected AS MATERIALIZED ({select})
    SELECT 1 FROM selected s
    WHERE s.fixture_uid IS NULL OR ({collision})
  ) THEN
    RAISE EXCEPTION 'SXF_ARCHIVE_PHYSICAL_IDENTITY_CONFLICT';
  END IF;
END
$sxf_guard$;
WITH selected AS MATERIALIZED ({select}),
inserted AS (
 INSERT INTO research_archive.fixtures (
     source_internal_id,match_id_hash,home_team,away_team,league,kickoff_utc,
     source_fixture_date,source_created_at,fixture_uid,local_date,archived_at
 )
 SELECT s.internal_id,s.match_id_hash,s.home_team,s.away_team,s.league,
        s.kickoff_utc,s.fixture_date,s.created_at,s.fixture_uid,s.local_date,now()
 FROM selected s
 WHERE NOT EXISTS (SELECT 1 FROM research_archive.fixtures a
                   WHERE a.source_internal_id=s.internal_id)
 ON CONFLICT (source_internal_id) DO NOTHING
 RETURNING source_internal_id
)
SELECT jsonb_build_object(
 'mode','APPEND_ONLY_APPLY',
 'day','{day}',
 'after_id',{after_id},
 'selected',(SELECT COUNT(*) FROM selected),
 'inserted',(SELECT COUNT(*) FROM inserted),
 'next_after_id',(SELECT COALESCE(MAX(internal_id),{after_id}) FROM selected),
 'archive_history_parity_proven',false,
 'cold_backup_verified',false,
 'retention_cleanup_allowed',false
)::text;
COMMIT;"""


def execute_psql(sql: str) -> dict:
    result = subprocess.run(
        ["psql","-X","-q","-t","-A","-v","ON_ERROR_STOP=1"],
        input=sql,text=True,capture_output=True,timeout=30,check=True,
    )
    lines = [x.strip() for x in result.stdout.splitlines() if x.strip().startswith("{")]
    if len(lines)!=1:
        raise ValueError("Backfill expected exactly one JSON result")
    report = json.loads(lines[0])
    if not isinstance(report,dict):
        raise ValueError("Unexpected non-object backfill response")
    return report


def main(argv: list[str] | None=None) -> int:
    ap=argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--day",required=True)
    ap.add_argument("--after-id",type=int,default=0)
    ap.add_argument("--limit",type=int,default=MAX_BATCH)
    ap.add_argument("--apply",action="store_true",help="Append-only production WRITE; requires external explicit approval")
    args=ap.parse_args(argv)
    try:
        day=validate(args.day,args.after_id,args.limit)
        if args.apply and os.environ.get(APPROVAL_ENV)!=APPROVAL_VALUE:
            raise PermissionError("No explicit append-only fixture backfill approval")
        sql=(apply_sql if args.apply else plan_sql)(day,args.after_id,args.limit)
        report=execute_psql(sql)
        print(json.dumps(report,ensure_ascii=False,sort_keys=True))
        if report.get("conflicts",0):
            return 2
        return 0
    except (ValueError,PermissionError,subprocess.SubprocessError,OSError) as exc:
        # Deliberately do not print raw SQL or psql.stderr (secrets/PII).
        print(json.dumps({"status":"BLOCKED","error_type":type(exc).__name__}),file=sys.stderr)
        return 3


if __name__=="__main__":
    sys.exit(main())
