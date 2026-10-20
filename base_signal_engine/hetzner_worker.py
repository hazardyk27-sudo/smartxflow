"""Hetzner-owned Base durable worker orchestration (source-only, opt-in).

NO automatic startup. Reads native SXF Moneyway data, stores ONLY sxf_base_*
durable jobs/events via token-fenced RPC, never alters legacy signals or source.
The Phase 5A per-row source triggers are deliberately NOT required for the
first supervised run: bounded cursor discovery plus scheduled reconciliation
retries provide a bounded, conservative baseline.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
import json
import os
import sys
import time

from .discovery import bounded_cursor_discovery_once, near_term_discovery_once
from .durable_runtime import execute_claims
from .reader import SupabaseMoneywayReader
from .rotation import rotation_slot, queue_diagnostics
from .reconcile_runtime import reconcile_once
from .storage import DurableStoreError, SupabaseCheckpointStore

def run_cycle(reader, store, *, worker_id: str, discover: bool = True,
              max_jobs: int = 12, max_reconcile: int = 2,
              lookback_days: int = 1, near_term: bool = False,
              near_term_hour_offset: int = 0,
              near_term_rotation: bool = False,
              priority_lanes: bool = False,
              now: datetime | None = None) -> dict:
    """Work is bounded, independently retryable, and never invents successful ACKs."""
    if not worker_id or len(worker_id)>100 or not (1<=max_jobs<=30) or not (
            0<=max_reconcile<=5) or not (1<=lookback_days<=7):
        raise ValueError("unsafe worker bounds")
    if type(near_term) is not bool or (near_term and not discover):
        raise ValueError("near-term discovery requires explicit normal discovery")
    if type(near_term_rotation) is not bool or (near_term_rotation and not near_term):
        raise ValueError("rotation requires near-term discovery")
    if near_term_rotation and near_term_hour_offset != 0:
        raise ValueError("rotating hour conflicts with explicit hour")
    if type(priority_lanes) is not bool or (priority_lanes and max_jobs < 3):
        raise ValueError("priority lanes require 3 or more jobs per cycle")
    if type(near_term_hour_offset) is not int or not -1 <= near_term_hour_offset <= 12:
        raise ValueError("unsafe near-term hour offset")
    report={"mode":"HETZNER_BASE_DURABLE","discovery":"SKIPPED",
            "enqueued":0,"discovered_fixtures":0,"superseded":0,
            "claimed":0,"completed":0,"waiting_data":0,"retried":0,
            "lease_uncertain":0,"commit_uncertain":0,
            "reconcile_claimed":0,"reconcile_completed":0,
            "reconcile_waiting_data":0,"reconcile_uncertain":0,
            "source_capture_enabled":False,
            "near_term_status":"DISABLED","near_term_enqueued":0,
            "near_term_fixtures":0,"near_term_cursor_advanced":False,
            "near_term_rotation_coverage_verified":False,
            "priority_lanes_enabled":priority_lanes,
            "live_claimed":0,"backlog_claimed":0}
    if discover:
        try:
            status=bounded_cursor_discovery_once(
                reader,store,worker_id=worker_id,window_hours=1,
                max_fixtures=50,max_pending_due=250)
            report["discovery"]=status["status"]
            report["enqueued"]=status["enqueued"]
            report["discovered_fixtures"]=status["fixtures"]
            report["discovery_paused"]=status["paused"]
            report["discovery_pending_before"]=status["pending_due"]
            if status["uncertain"]:
                # Unknown advance/lease result: do not claim ANY additional work.
                report["lease_uncertain"]=1
                report["healthy_cycle"]=False
                report["production_release_verified"]=False
                return report
        except DurableStoreError:
            # RPC failure may follow a committed cursor lease or advance.
            # Preserve uncertain exit status instead of blind re-run.
            raise
        except Exception as exc:
            # Catalog errors do not discard previously enqueued checkpoints.
            report["discovery"]="ERROR_"+type(exc).__name__.upper()[:50]

    # Optional Part 1 safety path. It does not change the historical cursor.
    # Default OFF; activating the guarded worker and this mode are separate
    # operator decisions. Never run after discovery uncertainty or failure.
    if near_term and report["discovery"] in ("OK", "IDLE", "PAUSED_BACKLOG"):
        try:
            selected_offset = near_term_hour_offset
            if near_term_rotation:
                slot = rotation_slot(now or datetime.now(timezone.utc))
                selected_offset = slot["hour_offset"]
                report["near_term_rotation_slot"] = slot["slot"]
                report["near_term_rotation_cycle_minute_utc"] = slot["cycle_minute_utc"]
            urgent = near_term_discovery_once(
                reader, store, now=now, hour_offset=selected_offset,
                max_fixtures=50, max_pending_due=1200)
            report["near_term_hour_offset"] = selected_offset
            report["near_term_status"] = urgent["status"]
            report["near_term_enqueued"] = urgent["enqueued"]
            report["near_term_fixtures"] = urgent["fixtures"]
            report["near_term_pending_before"] = urgent["pending_due"]
            report["near_term_window_start"] = urgent["window_start"]
            report["near_term_window_end"] = urgent["window_end"]
        except DurableStoreError:
            # A lost enqueue ACK is ambiguous; do not continue claiming jobs.
            raise
        except Exception as exc:
            report["near_term_status"] = "ERROR_" + type(exc).__name__.upper()[:50]
    elif near_term:
        report["near_term_status"] = "SKIPPED_DISCOVERY_UNHEALTHY"

    # Independent quotas prevent stale WAITING_DATA debt from swallowing
    # all capacity, while still guaranteeing a bounded backlog share.
    # A lane's empty claim does not suppress the OTHER lane's remaining work.
    slots = (["LIVE" if i % 3 != 2 else "BACKLOG" for i in range(max_jobs)]
             if priority_lanes else ["ANY"] * max_jobs)
    exhausted = set()
    for lane in slots:
        if lane in exhausted:
            continue
        if priority_lanes:
            result = execute_claims(reader, store, worker_id=worker_id,
                                    limit=1, lane=lane)
        else:
            result = execute_claims(reader, store, worker_id=worker_id,
                                    limit=1)
        report["claimed"] += result["claimed"]
        report["completed"] += result["completed"]
        report["waiting_data"] += result["waiting_data"]
        report["retried"] += result["retry"]
        report["lease_uncertain"] += result["lease_lost"]
        report["commit_uncertain"] += result["commit_uncertain"]
        if priority_lanes:
            report["live_claimed" if lane=="LIVE" else "backlog_claimed"] += result["claimed"]
        if result["lease_lost"] or result["commit_uncertain"]:
            # Unknown outcome must stop both lanes before any further claim.
            break
        if result["claimed"] == 0:
            exhausted.add(lane)
    if not (report["lease_uncertain"] or report["commit_uncertain"]):
        for _ in range(max_reconcile):
            result=reconcile_once(reader,store,worker_id=worker_id)
            report["reconcile_claimed"]+=result["claimed"]
            report["reconcile_completed"]+=result["completed"]
            report["reconcile_waiting_data"]+=result["waiting_data"]
            report["reconcile_uncertain"]+=(
                result["lease_uncertain"]+result["commit_uncertain"])
            if (result["claimed"]==0 or result["lease_uncertain"]
                    or result["commit_uncertain"]):
                # Reconcile ACK uncertainty must not be followed by another
                # claim before an independent durable-state read.
                break
    # A lost lease or ambiguous commit is an operator-review stop, even if
    # the subsequent health RPC is unavailable. Never turn it into exit 2
    # (which systemd may automatically restart).
    if (report["lease_uncertain"] or report["commit_uncertain"]
            or report["reconcile_uncertain"]):
        report["healthy_cycle"]=False
        report["production_release_verified"]=False
        return report
    # Never declare source health normal: outbox triggers are still deferred.
    health=store.health_snapshot()
    checkpoint=health.get("checkpoint_queue") if isinstance(health,dict) else None
    reconcile=health.get("reconciliation_queue") if isinstance(health,dict) else None
    if not isinstance(checkpoint,dict) or not isinstance(reconcile,dict):
        raise ValueError("missing durable health RPC result")
    if priority_lanes or near_term_rotation:
        report["queue_diagnostics"] = queue_diagnostics(
            health, now=now or datetime.now(timezone.utc))
        # A worker may successfully process leases while its discovery source
        # remains stale. Keep those two facts separate for operations:
        # never treat a successful cycle as evidence of complete coverage.
        report["coverage_state"] = ("DEGRADED" if
            report["queue_diagnostics"]["alerts"] else "UNVERIFIED")
        report["discovery_fresh"] = (
            "DISCOVERY_STALE" not in report["queue_diagnostics"]["alerts"] and
            "DISCOVERY_UNINITIALIZED" not in report["queue_diagnostics"]["alerts"])
    for name,metric in (("checkpoint_pending_due",checkpoint.get("pending_due")),
                        ("checkpoint_expired_leases",checkpoint.get("expired_leases")),
                        ("reconcile_pending_due",reconcile.get("pending_due")),
                        ("reconcile_expired_leases",reconcile.get("expired_leases"))):
        if type(metric) is not int or metric<0:
            raise ValueError("missing durable health metric")
        report[name]=metric
    report["healthy_cycle"]=(report["discovery"] in ("OK","SKIPPED","IDLE","PAUSED_BACKLOG")
       and not report["lease_uncertain"] and not report["commit_uncertain"]
       and not report["reconcile_uncertain"]
       and (not near_term or
            report["near_term_status"] in ("ENQUEUED", "IDEMPOTENT", "EMPTY"))
       and report["checkpoint_expired_leases"]==0
       and report["reconcile_expired_leases"]==0)
    report["production_release_verified"]=False
    return report


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="SXF Base Hetzner-only opt-in durable worker")
    parser.add_argument("--once",action="store_true",help="execute exactly one bounded cycle")
    parser.add_argument("--no-discovery",action="store_true",
                        help="one-shot supervised queue verification only; no bulk enqueue")
    parser.add_argument("--max-jobs",type=int,default=12)
    parser.add_argument("--max-reconcile",type=int,default=2)
    parser.add_argument("--lookback-days",type=int,default=1,
                        help="legacy CLI compatibility; durable cursor controls discovery")
    parser.add_argument("--interval-seconds",type=int,default=60)
    parser.add_argument("--near-term-discovery",action="store_true",
                        help="opt-in bounded single-hour scan; default disabled")
    parser.add_argument("--near-term-hour-offset",type=int,default=0,
                        help="UTC hour bucket relative to current hour, -1..12")
    parser.add_argument("--near-term-rotation",action="store_true",
                        help="rotate one UTC hour bucket per wall-clock minute, no coverage claim")
    parser.add_argument("--priority-lanes",action="store_true",
                        help="separately gated LIVE/BACKLOG fenced claim RPC")
    args=parser.parse_args(argv)
    if os.environ.get("SXF_BASE_DURABLE_WORKER_APPROVED")!="yes":
        parser.error("durable worker disabled until separately approved production release")
    if os.environ.get("SXF_BASE_COMPOSITE_INDEX_VERIFIED")!="yes":
        parser.error("verified composite snapshot index required")
    if not (1<=args.max_jobs<=30 and 0<=args.max_reconcile<=5
            and 1<=args.lookback_days<=7 and 30<=args.interval_seconds<=600):
        parser.error("unsafe work/sleep bounds")
    if (args.near_term_discovery and args.no_discovery) or (
            args.near_term_hour_offset != 0 and not args.near_term_discovery):
        parser.error("near-term discovery requires explicit --near-term-discovery and normal discovery")
    if not -1 <= args.near_term_hour_offset <= 12:
        parser.error("unsafe near-term hour offset")
    if (args.near_term_rotation and
        (not args.near_term_discovery or args.near_term_hour_offset != 0)):
        parser.error("rotation requires near-term discovery without manual offset")
    if args.priority_lanes and (
            args.max_jobs < 3 or os.environ.get("SXF_BASE_PRIORITY_LANES_APPROVED") != "yes"):
        parser.error("priority lanes require approval, migration and >=3 jobs")
    if args.no_discovery and not args.once:
        parser.error("--no-discovery requires --once")
    url=os.environ.get("SUPABASE_URL","")
    key=os.environ.get("SUPABASE_SERVICE_ROLE_KEY","")
    if not url or not key:
        parser.error("server-only credentials missing")
    worker_id="hetzner-base-"+os.environ.get("SXF_BASE_WORKER_ID","one")
    if len(worker_id)>100 or any(x not in "abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_-" for x in worker_id):
        parser.error("invalid safe worker ID")
    reader=SupabaseMoneywayReader(url,key,page_size=300,
        max_pages_per_window=15,request_timeout_seconds=15)
    store=SupabaseCheckpointStore(url,key,request_timeout_seconds=15)
    iteration=0
    while True:
        try:
            optional = ({"near_term": True, "near_term_hour_offset": args.near_term_hour_offset,
                         "near_term_rotation": args.near_term_rotation}
                        if args.near_term_discovery else {})
            if args.priority_lanes:
                optional["priority_lanes"] = True
            report=run_cycle(reader,store,worker_id=worker_id,
                max_jobs=args.max_jobs,max_reconcile=args.max_reconcile,
                lookback_days=args.lookback_days,
                discover=(not args.no_discovery), **optional)
            print(json.dumps(report,sort_keys=True),flush=True)
            if report["lease_uncertain"] or report["commit_uncertain"] or report["reconcile_uncertain"]:
                return 3  # External operator review rather than blind retry.
            if report["discovery"]=="UNINITIALIZED":
                # Operator must explicitly set the historical bootstrap cursor.
                # This is not a transient fault: do not restart forever.
                return 4
            if not report["healthy_cycle"]:
                return 2  # Discovery/health failure cannot be silent success.
        except DurableStoreError:
            # RPC timeouts can follow a committed lease or completion. Preserve
            # ambiguous outcome semantics: systemd must NOT auto-restart.
            print(json.dumps({"mode":"HETZNER_BASE_DURABLE","status":"UNCERTAIN",
                              "error_type":"DURABLESTOREERROR"}),file=sys.stderr,flush=True)
            return 3
        except Exception as exc:
            print(json.dumps({"mode":"HETZNER_BASE_DURABLE","status":"FAILED",
                              "error_type":type(exc).__name__}),file=sys.stderr,flush=True)
            return 2
        if args.once:
            return 0
        iteration+=1
        time.sleep(args.interval_seconds)


if __name__=="__main__":
    sys.exit(main())
