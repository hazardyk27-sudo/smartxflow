"""Single-fixture Hetzner read-only Base smoke. NEVER a production worker.

No fixture discovery, source writes, outbox ACK, notifications, trades,
timer, scheduler loop, or secret-bearing output. An operator must explicitly
invoke this bounded command for a single physical fixture.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
from uuid import UUID

from .reader import SupabaseMoneywayReader
from .rules import _utc
from .scheduler import (
    CheckpointJob, FixtureRef, INGESTION_GRACE, evaluate_job,
)
from .source_quality import CapturingReader, source_coverage


def probe_fixture(reader, fixture_uid: str, *,
                  checkpoint: int = 6,
                  now: datetime | None = None) -> dict:
    """Inspect exactly one UID and one immutable T-8 or T-6 checkpoint."""
    uid=str(UUID(fixture_uid))
    if uid != fixture_uid or checkpoint not in (6,8):
        raise ValueError("canonical fixture_uid and BASE checkpoint 6/8 required")
    at=_utc(now or datetime.now(timezone.utc))
    fixture, legacy_hash=reader.load_fixture(uid)
    if fixture.fixture_uid != uid:
        raise ValueError("physical fixture identity mismatch")
    job=CheckpointJob(FixtureRef(uid,fixture.kickoff_utc,legacy_hash),
                      checkpoint,"BASE")
    if at < job.timestamp + INGESTION_GRACE:
        raise ValueError("checkpoint not yet due; refusing future-data probe")

    capturing=CapturingReader(reader)
    payload=evaluate_job(job,capturing)
    coverage=source_coverage(job,capturing.source,payload)
    return {
        "operation":"SINGLE_FIXTURE_READ_ONLY_PROBE",
        "fixture_uid":uid,
        "kickoff_utc":fixture.kickoff_utc.isoformat(),
        "checkpoint_hours":checkpoint,
        "evaluated_as_of_utc":payload["evaluated_as_of_utc"],
        "source_rows":payload["fetched_rows"],
        "discarded_groups":payload["discarded_groups"],
        "status":coverage["disposition"],
        "coverage":coverage["state"],
        "missing_markets":coverage["missing_markets"],
        "missing_t6_markets":coverage["missing_t6_markets"],
        "requires_reconciliation":coverage["requires_reconciliation"],
        "markets":{name:record["state"]
                   for name,record in payload["markets"].items()},
        "signal_count":len(payload["signals"]),
        "signal_engines":sorted({item["engine"] for item in payload["signals"]}),
        "writes_performed":False,
        "shadow_24h_verified":False,
        "production_approved":False,
    }


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(
        description="Bounded Hetzner-only one-fixture read-only smoke")
    parser.add_argument("--fixture-uid",required=True)
    parser.add_argument("--checkpoint",type=int,choices=(6,8),default=6)
    args=parser.parse_args(argv)
    if os.environ.get("SXF_BASE_SINGLE_PROBE_APPROVED")!="yes":
        parser.error("explicit SXF_BASE_SINGLE_PROBE_APPROVED=yes required")
    base=os.environ.get("SUPABASE_URL","")
    key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
    if not base or not key:
        parser.error("missing server-only Supabase credentials")
    try:
        # Tight absolute bound: at most 2 pages of 50 source rows per merged
        # window, HTTPS-only GET, timeouts. Refuses silently truncated input.
        reader=SupabaseMoneywayReader(
            base,key,page_size=50,max_pages_per_window=2,
            request_timeout_seconds=12)
        result=probe_fixture(reader,args.fixture_uid,checkpoint=args.checkpoint)
    except Exception as exc:
        # Only class name: no URL, HTTP body, credentials, or raw source values.
        print(json.dumps({"operation":"SINGLE_FIXTURE_READ_ONLY_PROBE",
                          "status":"FAILED","error_type":type(exc).__name__,
                          "writes_performed":False}),file=sys.stderr)
        return 2
    print(json.dumps(result,sort_keys=True))
    return 0 if result["status"]=="EVALUATE" else 1


if __name__=="__main__":
    sys.exit(main())
