"""Fresh-start V2 contracts: no old backlog, no tampering with append-only records.

These tests do not execute cutover SQL; production writes are gated behind
verified stopped services, authorized release, and drained leases.
"""
from pathlib import Path

from base_signal_engine.scheduler import RULESET_VERSION, CHECKPOINT_TASKS, CheckpointJob, FixtureRef
from base_signal_engine.feed import BaseSignalsFeed
from datetime import datetime, timezone

ROOT = Path(__file__).resolve().parents[1]
V2 = "SXF_SIGNAL_MOTOR_V2_2026_10_22"
V3 = "SXF_SIGNAL_MOTOR_V3_2026_10_24"


def test_new_ruleset_is_explicit_and_all_jobs_get_new_identity():
    assert RULESET_VERSION == V3
    ref = FixtureRef("fake-fixture-uid",datetime(2026,10,22,20,tzinfo=timezone.utc))
    job = CheckpointJob(ref,8,"BASE")
    assert job.key.startswith(V3 + ":")
    assert len(CHECKPOINT_TASKS)==11


def test_live_claims_cannot_reclaim_v1_backlog():
    sql = (ROOT/"migrations/2026_10_21_signal_motor_today_first.sql").read_text()
    assert "j.ruleset_version='"+V2+"'" in sql
    assert "AT TIME ZONE 'Europe/Istanbul'" in sql
    assert "j.kickoff_utc>now()" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql


def test_skip_rpc_is_fenced_to_fresh_v2_jobs():
    sql = (ROOT/"migrations/2026_10_21_signal_motor_skip_future_only_guard.sql").read_text()
    assert "j.ruleset_version='"+V2+"'" in sql
    assert "j.lease_token=p_lease_token" in sql
    assert "j.kickoff_utc>now()" in sql
    assert "j.lease_expires_at>now()" in sql
    assert "sibling.lease_expires_at>now()" in sql


def test_feed_reads_only_fresh_release_events():
    source = (ROOT/"base_signal_engine/feed.py").read_text()
    assert '("ruleset_version", "eq." + RULESET_VERSION)' in source
    assert 'archive: bool = False' not in source
    assert '"sxf_base_signal_events"' in source
    assert '"sxf_base_checkpoint_jobs"' in source


def test_operator_gate_and_lease_drain_required_for_fresh_start():
    sql = (ROOT/"deploy/signal_motor_fresh_start_cutover_20261022.sql").read_text()
    for phrase in (
        "FRESH_START_REJECTED: worker and timer human verification required",
        "VERIFIED_WORKER_AND_TIMER_STOPPED",
        "FRESH_START_REJECTED: outstanding leases",
        "FRESH_START_REJECTED: V2 already started",
        "IN ACCESS EXCLUSIVE MODE",
        "public.sxf_base_discovery_cursors",
        "cursor_name='BASE_FIXTURES'",
        "AT TIME ZONE 'Europe/Istanbul'",
    ):
        assert phrase in sql, phrase
    assert "BEGIN;" in sql and sql.rstrip().endswith("COMMIT;")


def test_old_never_attempted_pending_delete_only_and_other_jobs_retired():
    sql = (ROOT/"deploy/signal_motor_fresh_start_cutover_20261022.sql").read_text()
    assert "DELETE FROM public.sxf_base_checkpoint_jobs j" in sql
    assert "j.state='PENDING' AND j.attempt_count=0" in sql
    assert "NOT EXISTS(SELECT 1 FROM public.sxf_base_checkpoint_attempts" in sql
    assert "state='SUPERSEDED'" in sql
    assert "FRESH_START_V2_RETIRED" in sql
    assert "UPDATE public.sxf_base_discovery_cursors" in sql
    assert "DELETE FROM public.sxf_base_reconcile_jobs" in sql
    assert "DELETE FROM public.sxf_base_checkpoint_attempts" not in sql
    assert "DELETE FROM public.sxf_base_signal_events" not in sql
    assert "DELETE FROM public.moneyway_snapshots" not in sql
    assert "DISABLE TRIGGER" not in sql.upper()
    assert "TRUNCATE " not in sql.upper()


def test_enqueue_accepts_new_identity_without_rewriting_original_audit():
    sql = (ROOT/"deploy/signal_motor_fresh_start_cutover_20261022.sql").read_text()
    assert "CREATE OR REPLACE FUNCTION public.sxf_base_enqueue_jobs" in sql
    assert "v_ruleset NOT IN ('SXF_BASE_V1_2026_10_18', '"+V2+"')" in sql
    assert "p_jobs jsonb" in sql
    assert "ON CONFLICT DO NOTHING" in sql
    assert "DROP TABLE" not in sql.upper()
