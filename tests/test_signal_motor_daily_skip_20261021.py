"""New Sinyal Motoru contracts: today-first, nearest real T-hour, skip gaps."""
from datetime import datetime, timedelta, timezone
from pathlib import Path
from uuid import uuid4
import json

import pytest

from base_signal_engine.rules import (
    Fixture, Quote, Snapshot, select_snapshot, choose_base_checkpoint,
)
from base_signal_engine import hetzner_worker as worker

ROOT=Path(__file__).resolve().parents[1]
KO=datetime(2026,10,24,18,0,tzinfo=timezone.utc)
FX=Fixture(str(uuid4()),KO)


def snapshot(hours, minutes=0, shares=("60","20","20")):
    at=KO-timedelta(hours=hours,minutes=minutes)
    return Snapshot("1X2",at,{
        "1":Quote("1.8","6000",shares[0]),
        "X":Quote("3.1","2000",shares[1]),
        "2":Quote("4.2","2000",shares[2]),
    })


def test_nearest_real_prior_snapshot_within_hour_not_after_checkpoint():
    future=snapshot(72,-3)       # 3 minutes AFTER checkpoint: forbidden
    older=snapshot(72,56)
    closest=snapshot(72,18)
    assert select_snapshot(FX,"1X2",72,[future,older,closest]) is closest
    assert select_snapshot(FX,"1X2",72,[older]) is older
    assert select_snapshot(FX,"1X2",72,[snapshot(72,60)]) is None
    assert select_snapshot(FX,"1X2",72,[future]) is None


def test_a_missing_t6_market_is_not_replaced_with_t8_snapshot():
    assert choose_base_checkpoint(
        FX,"1X2",[snapshot(8)],KO-timedelta(hours=5)
    )==(None,"INSUFFICIENT_DATA")


def test_day_first_priority_is_enforced_by_fenced_database_claim():
    sql=(ROOT/"migrations/2026_10_21_signal_motor_today_first.sql").read_text()
    for required in (
        "j.kickoff_utc>now()", "j.run_after<=now()",
        "AT TIME ZONE 'Europe/Istanbul'", "j.kickoff_utc ASC",
        "FOR UPDATE SKIP LOCKED", "lease_token=gen_random_uuid()",
        "p_lane='LIVE'",
    ):
        assert required in sql,required
    assert "TRUNCATE" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()


def test_terminal_source_skip_is_fenced_and_does_not_emit_fake_signals():
    sql=(ROOT/"migrations/2026_10_21_signal_motor_skip_missing.sql").read_text()
    for required in (
        "SKIPPED_DATA", "j.lease_token=p_lease_token",
        "j.state='LEASED'", "j.lease_expires_at>now()",
        "GRANT EXECUTE", "service_role",
    ):
        assert required in sql,required
    assert "INSERT INTO public.sxf_base_signal_events" not in sql
    assert "DELETE FROM" not in sql.upper()


def test_all_checkpoint_capacity_uses_live_today_then_tomorrow(monkeypatch):
    calls=[]
    def claim(_reader,_store,**kwargs):
        calls.append(kwargs.get("lane"))
        return {"claimed":1,"completed":0,"skipped_data":1,
                "waiting_data":0,"retry":0,"lease_lost":0,"commit_uncertain":0}
    monkeypatch.setattr(worker,"execute_claims",claim)
    class Store:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":33,"expired_leases":0,
                                        "oldest_due_seconds":11},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                                        "last_scanned_at":KO.isoformat()}}
    report=worker.run_cycle(None,Store(),worker_id="test",discover=False,
                            priority_lanes=True,max_jobs=24,max_reconcile=0,now=KO)
    assert calls==["LIVE"]*24
    assert report["backlog_claimed"]==0
    assert report["skipped_data"]==24
    assert report["completed"]==0


def test_legacy_five_removed_from_api_and_ui_and_old_writer_disabled():
    app=(ROOT/"app.py").read_text()
    fn=app.split("def base_signal_feed_api():",1)[1].split("_analyses_cache",1)[0]
    assert "LegacySignalsFeed" not in fn
    assert "source.read(first, days=int(days_text), archive=(mode == 'archive'))" in fn
    js=(ROOT/"static/js/base-signals.js").read_text()
    assert "LEGACY_UNDERDOG:" not in js
    assert "LEGACY_FAKE_SHARP:" not in js
    assert "LEGACY_EARLY_MONEY_LOCK:" not in js
    assert "LEGACY_CONFIRMED_MONEY_V1:" not in js
    assert "LEGACY_CONFIRMED_MONEY_V2:" not in js
    deploy=(ROOT/".github/workflows/deploy.yml").read_text()
    assert "systemctl stop smartxflow-sinyal.service" in deploy
    assert "systemctl disable smartxflow-sinyal.service" in deploy
    assert "systemctl restart smartxflow-alarm" in deploy


def test_title_is_signal_motor_in_seven_languages():
    expected={"tr":"Sinyal Motoru","en":"Signal Engine","de":"Signalmotor",
              "fr":"Moteur de signaux","it":"Motore dei segnali",
              "es":"Motor de señales","nl":"Signaalmotor"}
    for lang,title in expected.items():
        obj=json.loads((ROOT/"static/i18n"/(lang+".json")).read_text())
        assert obj["app"]["v4"]["title"]==title
        assert obj["app"]["flt"]["analysts"]==title
        assert obj["idx"]["analizler"]==title


def test_additive_skip_future_only_guard_requires_causal_due_time_and_live_lease():
    # The initial migration has already been deployed. Keep it immutable;
    # use a separate additive migration to narrow the terminal transition.
    sql=(ROOT/"migrations/2026_10_21_signal_motor_skip_future_only_guard.sql").read_text()
    for required in (
        "CREATE OR REPLACE FUNCTION public.sxf_base_skip_missing_source",
        "j.job_id=p_job_id",
        "j.lease_token=p_lease_token",
        "j.state='LEASED'",
        "j.lease_expires_at>now()",
        "j.checkpoint_at<=now()",
        "j.run_after<=now()",
        "j.kickoff_utc>now()",
        "p_reason IS DISTINCT FROM 'SOURCE_INCOMPLETE'",
        "SET search_path TO 'public','pg_temp'",
        "REVOKE ALL ON FUNCTION",
        "FROM PUBLIC,anon,authenticated",
        "GRANT EXECUTE ON FUNCTION",
        "TO service_role",
    ):
        assert required in sql, required
    assert "SECURITY DEFINER" not in sql.upper()
    for forbidden in ("TRUNCATE ", "DELETE FROM ", "INSERT INTO public.sxf_base_signal_events"):
        assert forbidden not in sql.upper() if forbidden != "INSERT INTO public.sxf_base_signal_events" else forbidden not in sql
    assert sql.strip().startswith("-- Part 3 additive")
    assert sql.rstrip().endswith("COMMIT;")


def test_part3_migration_order_documented_and_first_migration_unmodified():
    first=(ROOT/"migrations/2026_10_21_signal_motor_skip_missing.sql").read_text()
    hard=(ROOT/"migrations/2026_10_21_signal_motor_skip_future_only_guard.sql").read_text()
    claim=(ROOT/"migrations/2026_10_21_signal_motor_today_first.sql").read_text()
    assert "SKIPPED_DATA" in first
    assert "j.kickoff_utc>now()" in hard
    assert "AT TIME ZONE 'Europe/Istanbul'" in claim
    # This is an additive override of one existing RPC, not a destructive
    # replay of the applied state-constraint migration.
    assert "ALTER TABLE" not in hard.upper()
    assert "DROP " not in hard.upper()
    assert "CREATE OR REPLACE FUNCTION public.sxf_base_skip_missing_source" in hard


def test_fixture_level_missing_source_skip_is_atomic_and_does_not_rewrite_evidence():
    """One missing real checkpoint disqualifies sibling jobs, not completed events."""
    sql=(ROOT/"migrations/2026_10_21_signal_motor_skip_future_only_guard.sql").read_text()
    for required in (
        "SELECT j.fixture_uid,j.kickoff_utc INTO v_fixture_uid,v_kickoff_utc",
        "sibling.kickoff_utc=v_kickoff_utc",
        "j.kickoff_utc=v_kickoff_utc",
        "FOR UPDATE",
        "sibling.state='LEASED'",
        "sibling.lease_expires_at>now()",
        "RETURN FALSE",
        "j.fixture_uid=v_fixture_uid",
        "state='SKIPPED_DATA'",
        "THEN 'SOURCE_INCOMPLETE'",
        "ELSE 'FIXTURE_SKIPPED_UPSTREAM_GAP'",
        "j.state IN ('PENDING','RETRY','WAITING_DATA')",
        "j.lease_expires_at<=now()",
    ):
        assert required in sql, required
    # A future checkpoint skipped because the MATCH was disqualified must
    # not be mislabeled as a snapshot that was already due and missing.
    assert "FIXTURE_SKIPPED_UPSTREAM_GAP" in sql
    assert "j.state='COMPLETED'" not in sql
    assert "DELETE FROM" not in sql.upper()
    assert "TRUNCATE " not in sql.upper()


def test_claim_migration_excludes_terminally_skipped_fixtures():
    sql=(ROOT/"migrations/2026_10_21_signal_motor_today_first.sql").read_text()
    for required in (
        "AND NOT EXISTS (", "stopped.fixture_uid=j.fixture_uid",
        "stopped.kickoff_utc=j.kickoff_utc",
        "stopped.state='SKIPPED_DATA'",
        "stopped.last_error_code='SOURCE_INCOMPLETE'",
    ):
        assert required in sql, required
