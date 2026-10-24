"""Regression: 24-job bounded production throughput, fresh BACKLOG priority."""
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


def test_queue_first_pauses_future_discovery_and_claims_both_due_lanes(monkeypatch):
    calls = {"discovery": [], "near_term": [], "lanes": []}
    def discovery(*args, **kwargs):
        calls["discovery"].append(kwargs)
        return {"status":"PAUSED_BACKLOG","enqueued":0,"fixtures":0,
                "paused":True,"pending_due":748,"uncertain":False}
    def urgent(*args, **kwargs):
        calls["near_term"].append(kwargs)
        raise AssertionError("future rescan must wait for due queue")
    def claim(*args, **kwargs):
        calls["lanes"].append(kwargs["lane"])
        return {"claimed":1,"completed":1,"waiting_data":0,"retry":0,
                "lease_lost":0,"commit_uncertain":0}
    monkeypatch.setattr(hetzner_worker,"bounded_cursor_discovery_once",discovery)
    monkeypatch.setattr(hetzner_worker,"near_term_discovery_once",urgent)
    monkeypatch.setattr(hetzner_worker,"execute_claims",claim)
    class Store:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":748,"expired_leases":0,
                                        "oldest_due_seconds":7200},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                                        "last_scanned_at":AT.isoformat()}}
    result = hetzner_worker.run_cycle(object(),Store(),worker_id="w",now=AT,
            priority_lanes=True,queue_drain_first=True,near_term=True,
            near_term_rotation=True,max_jobs=24,max_reconcile=0)
    assert result["discovery"] == "PAUSED_BACKLOG"
    assert calls["discovery"][0]["max_pending_due"] == 1
    assert calls["discovery"][0].get("allow_high_backlog") is None
    assert calls["near_term"] == []
    assert result["near_term_status"] == "PAUSED_BACKLOG"
    assert result["live_claimed"] == 16
    assert result["backlog_claimed"] == 8
    assert result["claimed"] == result["completed"] == 24
    assert result["healthy_cycle"] is True


def test_queue_first_refills_from_backlog_when_live_lane_is_empty(monkeypatch):
    claimed = []
    def claim(*args, **kwargs):
        lane = kwargs["lane"]
        claimed.append(lane)
        return {"claimed":int(lane=="BACKLOG"),"completed":int(lane=="BACKLOG"),
                "waiting_data":0,"retry":0,"lease_lost":0,"commit_uncertain":0}
    monkeypatch.setattr(hetzner_worker,"execute_claims",claim)
    class Store:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":66,"expired_leases":0,
                                        "oldest_due_seconds":7200},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                                        "last_scanned_at":AT.isoformat()}}
    result=hetzner_worker.run_cycle(object(),Store(),worker_id="w",now=AT,
        discover=False,priority_lanes=True,queue_drain_first=True,
        max_jobs=24,max_reconcile=0)
    assert claimed.count("LIVE") == 1
    assert claimed.count("BACKLOG") == 23
    assert result["backlog_claimed"] == 23
    assert result["healthy_cycle"] is True


def test_future_scan_resumes_when_due_queue_is_empty(monkeypatch):
    calls = []
    monkeypatch.setattr(hetzner_worker,"bounded_cursor_discovery_once",
        lambda *args,**kwargs: (calls.append(("cursor",kwargs)) or
        {"status":"IDLE","enqueued":0,"fixtures":0,"paused":False,
         "pending_due":0,"uncertain":False}))
    monkeypatch.setattr(hetzner_worker,"near_term_discovery_once",
        lambda *args,**kwargs: (calls.append(("near",kwargs)) or
        {"status":"EMPTY","enqueued":0,"fixtures":0,"pending_due":0,
         "window_start":AT.isoformat(),"window_end":AT.isoformat()}))
    monkeypatch.setattr(hetzner_worker,"execute_claims",lambda *args,**kwargs: {
        "claimed":0,"completed":0,"waiting_data":0,"retry":0,
        "lease_lost":0,"commit_uncertain":0})
    class Store:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":0,"expired_leases":0,
                                        "oldest_due_seconds":None},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                                        "last_scanned_at":AT.isoformat()}}
    result=hetzner_worker.run_cycle(object(),Store(),worker_id="w",now=AT,
        priority_lanes=True,queue_drain_first=True,near_term=True,
        near_term_rotation=True,max_jobs=6,max_reconcile=0)
    assert [call[0] for call in calls] == ["cursor","near"]
    assert result["near_term_status"] == "EMPTY"
    assert result["healthy_cycle"] is True


def test_cursor_newly_enqueued_jobs_precede_near_term_scan(monkeypatch):
    monkeypatch.setattr(hetzner_worker,"bounded_cursor_discovery_once",
        lambda *args,**kwargs:{
            "status":"OK","enqueued":11,"fixtures":1,"paused":False,
            "pending_due":0,"uncertain":False})
    def unexpected(*args,**kwargs):
        raise AssertionError("must process newly enqueued jobs before rescan")
    monkeypatch.setattr(hetzner_worker,"near_term_discovery_once",unexpected)
    monkeypatch.setattr(hetzner_worker,"execute_claims",lambda *args,**kwargs: {
        "claimed":0,"completed":0,"waiting_data":0,"retry":0,
        "lease_lost":0,"commit_uncertain":0})
    class Store:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":0,"expired_leases":0,
                                        "oldest_due_seconds":None},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                                        "last_scanned_at":AT.isoformat()}}
    result=hetzner_worker.run_cycle(object(),Store(),worker_id="w",now=AT,
        priority_lanes=True,queue_drain_first=True,near_term=True,
        near_term_rotation=True,max_jobs=3,max_reconcile=0)
    assert result["near_term_status"] == "PAUSED_BACKLOG"
    assert result["healthy_cycle"] is True


def test_queue_first_requires_versioned_priority_claim_lanes():
    with pytest.raises(ValueError,match="priority lanes"):
        hetzner_worker.run_cycle(None,None,worker_id="w",
                                 queue_drain_first=True,discover=False)
