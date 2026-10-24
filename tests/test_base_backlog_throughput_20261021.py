"""Regression: bounded LIVE-only queue drain; past jobs stay immutable."""
from pathlib import Path
from datetime import datetime,timezone
import pytest
from base_signal_engine import hetzner_worker

ROOT=Path(__file__).resolve().parents[1]
AT=datetime(2026,10,21,12,30,tzinfo=timezone.utc)


def test_unit_uses_bounded_24_jobs_and_30s_sleep_not_endless_load():
    unit=(ROOT/"deploy/systemd/smartxflow-base-worker.service").read_text()
    assert "--max-jobs 24 --max-reconcile 1 --interval-seconds 30" in unit
    assert "--queue-drain-first" in unit
    assert "RestartPreventExitStatus=3 4" in unit
    assert "WatchdogSec=420" in unit
    assert "SXF_BASE_DURABLE_WORKER_APPROVED=yes" not in unit


def test_backlog_migration_preserves_fenced_claims_and_lane_split():
    sql=(ROOT/"migrations/2026_10_21_sxf_base_backlog_recent_first.sql").read_text()
    assert "p_lane='BACKLOG' AND j.kickoff_utc >= now()-interval '24 hours'" in sql
    assert "CASE WHEN p_lane='LIVE' THEN" in sql
    assert "FOR UPDATE SKIP LOCKED" in sql
    assert "p_lease_seconds integer DEFAULT 900" in sql
    assert "lease_token=gen_random_uuid()" in sql
    assert "INSERT INTO" not in sql
    assert "DELETE FROM" not in sql
    assert "TRUNCATE " not in sql
    assert "DROP TABLE" not in sql


def test_24_job_live_backlog_quotas_and_tracking(monkeypatch):
    def claimed(reader,store,**kwargs):
        lane=kwargs["lane"]
        return {"claimed":1, "completed":1 if lane=="LIVE" else 0,
                "waiting_data":1 if lane=="BACKLOG" else 0,
                "retry":0,"lease_lost":0,"commit_uncertain":0}
    monkeypatch.setattr(hetzner_worker,"execute_claims",claimed)
    class Store:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":200,"expired_leases":0,
                                        "oldest_due_seconds":100},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                         "last_scanned_at":AT.isoformat()}}
    report=hetzner_worker.run_cycle(
        object(),Store(),worker_id="w",now=AT,discover=False,
        priority_lanes=True,max_jobs=24,max_reconcile=0)
    assert report["claimed"]==24
    assert report["live_claimed"]==24
    assert report["backlog_claimed"]==0
    assert report["completed"]==report["live_completed"]==24
    assert report["backlog_waiting_data"]==report["waiting_data"]==0
    assert report["healthy_cycle"] is True
    assert report["production_release_verified"] is False


def test_unexpected_uncertain_commit_stops_all_lanes_even_under_higher_quota(monkeypatch):
    count=[0]
    def claimed(*args,**kwargs):
        count[0]+=1
        return {"claimed":1,"completed":0,"waiting_data":0,"retry":0,
                "lease_lost":0,"commit_uncertain":1}
    monkeypatch.setattr(hetzner_worker,"execute_claims",claimed)
    report=hetzner_worker.run_cycle(object(),object(),worker_id="w",
        discover=False,priority_lanes=True,max_jobs=24,max_reconcile=0)
    assert count[0]==1
    assert report["commit_uncertain"]==1
    assert report["healthy_cycle"] is False


def _health(pending=66):
    return {"checkpoint_queue":{"pending_due":pending,"expired_leases":0,
                                "oldest_due_seconds":7200},
            "reconciliation_queue":{"pending_due":0,"expired_leases":0},
            "discovery_cursor":{"initialized":True,
                                "last_scanned_at":AT.isoformat()}}


def _claim_result(claimed=1, uncertain=0):
    return {"claimed":claimed,"completed":claimed,"waiting_data":0,
            "retry":0,"lease_lost":uncertain,"commit_uncertain":0}


def test_queue_first_drains_only_future_live_jobs_before_discovery(monkeypatch):
    calls = {"lanes": [], "discovery": []}
    monkeypatch.setattr(hetzner_worker,"bounded_cursor_discovery_once",
        lambda *a,**k: calls["discovery"].append(k))
    monkeypatch.setattr(hetzner_worker,"near_term_discovery_once",
        lambda *a,**k: (_ for _ in ()).throw(AssertionError("should not rescan")))
    def claim(*args,**kwargs):
        calls["lanes"].append(kwargs["lane"])
        return _claim_result()
    monkeypatch.setattr(hetzner_worker,"execute_claims",claim)
    class Store:
        def health_snapshot(self):
            return _health(748)
    result=hetzner_worker.run_cycle(object(),Store(),worker_id="w",now=AT,
        priority_lanes=True,queue_drain_first=True,near_term=True,
        near_term_rotation=True,max_jobs=24,max_reconcile=0)
    assert calls["lanes"] == ["LIVE"]*24
    assert calls["discovery"] == []
    assert result["discovery"] == "PAUSED_LIVE_QUEUE"
    assert result["near_term_status"] == "PAUSED_LIVE_QUEUE"
    assert result["backlog_claimed"] == 0
    assert result["claimed"] == result["live_claimed"] == 24
    assert result["healthy_cycle"] is True


def test_only_past_backlog_does_not_block_future_discovery(monkeypatch):
    claimed = []
    scanned = []
    def claim(*args,**kwargs):
        claimed.append(kwargs["lane"])
        return _claim_result(claimed=0)
    monkeypatch.setattr(hetzner_worker,"execute_claims",claim)
    def cursor(*args,**kwargs):
        scanned.append(("cursor",kwargs))
        return {"status":"IDLE","enqueued":0,"fixtures":0,
                "paused":False,"pending_due":66,"uncertain":False}
    def near(*args,**kwargs):
        scanned.append(("near",kwargs))
        return {"status":"EMPTY","enqueued":0,"fixtures":0,
                "pending_due":66,"window_start":AT.isoformat(),
                "window_end":AT.isoformat()}
    monkeypatch.setattr(hetzner_worker,"bounded_cursor_discovery_once",cursor)
    monkeypatch.setattr(hetzner_worker,"near_term_discovery_once",near)
    class Store:
        def health_snapshot(self):
            return _health(66)
    result=hetzner_worker.run_cycle(object(),Store(),worker_id="w",now=AT,
        priority_lanes=True,queue_drain_first=True,near_term=True,
        near_term_rotation=True,max_jobs=24,max_reconcile=0)
    assert claimed == ["LIVE","LIVE"]
    assert [x[0] for x in scanned] == ["cursor","near"]
    assert all(x[1]["future_only"] is True for x in scanned)
    assert all(x[1]["allow_high_backlog"] is True for x in scanned)
    assert result["backlog_claimed"] == 0
    assert result["near_term_status"] == "EMPTY"
    assert result["healthy_cycle"] is True


def test_newly_discovered_future_jobs_are_processed_without_past_lane(monkeypatch):
    lanes=[]
    def claim(*args,**kwargs):
        lanes.append(kwargs["lane"])
        return _claim_result(claimed=0 if len(lanes)==1 else 1)
    monkeypatch.setattr(hetzner_worker,"execute_claims",claim)
    monkeypatch.setattr(hetzner_worker,"bounded_cursor_discovery_once",
        lambda *a,**k: {"status":"OK","enqueued":11,"fixtures":1,
                        "paused":False,"pending_due":66,"uncertain":False})
    monkeypatch.setattr(hetzner_worker,"near_term_discovery_once",
        lambda *a,**k: (_ for _ in ()).throw(AssertionError("new jobs first")))
    class Store:
        def health_snapshot(self):
            return _health(66)
    result=hetzner_worker.run_cycle(object(),Store(),worker_id="w",now=AT,
        priority_lanes=True,queue_drain_first=True,near_term=True,
        near_term_rotation=True,max_jobs=3,max_reconcile=0)
    assert lanes == ["LIVE"]*4
    assert result["near_term_status"] == "PAUSED_LIVE_QUEUE"
    assert result["claimed"] == result["live_claimed"] == 3
    assert result["backlog_claimed"] == 0
    assert result["healthy_cycle"] is True


def test_future_lane_uncertainty_stops_before_discovery(monkeypatch):
    attempts=[]
    monkeypatch.setattr(hetzner_worker,"execute_claims",
        lambda *a,**k: (attempts.append(k["lane"]) or
                        _claim_result(claimed=1,uncertain=1)))
    monkeypatch.setattr(hetzner_worker,"bounded_cursor_discovery_once",
        lambda *a,**k: (_ for _ in ()).throw(AssertionError("fenced")))
    result=hetzner_worker.run_cycle(object(),object(),worker_id="w",
        discover=True,priority_lanes=True,queue_drain_first=True,
        max_jobs=24,max_reconcile=0)
    assert attempts == ["LIVE"]
    assert result["lease_uncertain"] == 1
    assert result["healthy_cycle"] is False


def test_near_term_future_only_does_not_enqueue_past_kickoffs():
    from datetime import timedelta
    from base_signal_engine import discovery
    from base_signal_engine.scheduler import FixtureRef
    past=FixtureRef("past",AT-timedelta(minutes=5))
    boundary=FixtureRef("boundary",AT)
    upcoming=FixtureRef("future",AT+timedelta(minutes=15))
    class Catalog:
        def list_between(self,begin,end):
            return [past,boundary,upcoming]
    class Store:
        enqueued = None
        def health_snapshot(self):
            return _health(0)
        def enqueue(self,fixtures):
            self.enqueued=list(fixtures)
            return len(fixtures)*11
    store=Store()
    result=discovery.near_term_discovery_once(
        object(),store,now=AT,catalog=Catalog(),future_only=True,
        allow_high_backlog=True)
    assert store.enqueued == [upcoming]
    assert result["fixtures"] == 1
    assert result["enqueued"] == 11


def test_cursor_future_only_preserves_source_window_audit_and_data():
    from datetime import timedelta
    from base_signal_engine import discovery
    from base_signal_engine.scheduler import FixtureRef
    past=FixtureRef("past",AT-timedelta(minutes=5))
    upcoming=FixtureRef("future",AT+timedelta(minutes=10))
    class Catalog:
        def list_between(self,begin,end):
            return [past,upcoming]
    class Store:
        enqueued = None
        advanced_count = None
        def claim_discovery(self,worker_id):
            return {"completed_through":AT-timedelta(minutes=15)}
        def enqueue(self,fixtures):
            self.enqueued=list(fixtures)
            return len(fixtures)*11
        def advance_discovery(self,item,*,end,fixture_count):
            self.advanced_count=fixture_count
    store=Store()
    result=discovery.discover_window_once(
        object(),store,worker_id="worker",now=AT,catalog=Catalog(),
        window_hours=1,future_only=True)
    assert store.enqueued == [upcoming]
    assert store.advanced_count == 2
    assert result["fixtures"] == 1
    assert result["advanced"] is True


def test_queue_first_requires_versioned_priority_claim_lanes():
    with pytest.raises(ValueError,match="priority lanes"):
        hetzner_worker.run_cycle(None,None,worker_id="w",
                                 queue_drain_first=True,discover=False)
