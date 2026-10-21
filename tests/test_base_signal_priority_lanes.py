"""Part 2: deterministic rotation, strict lane contracts, no network."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
from uuid import uuid4
import pytest
from base_signal_engine.rotation import rotation_slot, queue_diagnostics, HOUR_OFFSETS
from base_signal_engine import hetzner_worker as worker
from base_signal_engine.durable_runtime import execute_claims
from base_signal_engine.storage import SupabaseCheckpointStore

AT=datetime(2026,10,20,14,33,tzinfo=timezone.utc)

def test_rotation_restarts_do_not_reset_its_wall_clock_slot():
    first=rotation_slot(AT)
    assert first==rotation_slot(AT+timedelta(seconds=12))
    assert first["hour_offset"] in range(-1,81)
    assert first["coverage_verified"] is False
    assert rotation_slot(AT+timedelta(minutes=len(HOUR_OFFSETS)))["hour_offset"]==first["hour_offset"]
    assert len({rotation_slot(AT+timedelta(minutes=i))["hour_offset"]
                for i in range(len(HOUR_OFFSETS))})==len(HOUR_OFFSETS)
    with pytest.raises(ValueError): rotation_slot(datetime(2026,10,20))

def test_queue_alerts_distinguish_stale_cursor_from_zero_lag_report():
    health={"checkpoint_queue":{"pending_due":467,"oldest_due_seconds":4000},
            "discovery_cursor":{"initialized":True,
              "lag_seconds":0,"last_scanned_at":(AT-timedelta(hours=10)).isoformat()},
            "reconciliation_queue":{"pending_due":51}}
    diag=queue_diagnostics(health,now=AT)
    assert set(diag["alerts"])=={"DISCOVERY_STALE","CHECKPOINT_BACKPRESSURE",
                                  "CHECKPOINT_OVERDUE","RECONCILE_BACKLOG"}
    assert diag["discovery_scan_age_seconds"]==36000
    assert diag["discovery_coverage_verified"] is False
    assert diag["source_capture_verified"] is False
    with pytest.raises(ValueError):
        queue_diagnostics({"checkpoint_queue":{"pending_due":None}},now=AT)

def test_lane_claims_use_separate_rpc_but_keep_fencing_and_identity():
    class Session:
        def __init__(self): self.calls=[]
        def post(self,url,*,json,headers,timeout):
            self.calls.append((url.rsplit("/",1)[-1],json))
            return SimpleNamespace(status_code=200,json=lambda:[])
    fake=Session()
    store=SupabaseCheckpointStore("https://example.supabase.co","test-token",session=fake)
    assert store.claim("worker",limit=1,lane="LIVE")==[]
    assert fake.calls[-1][0]=="sxf_base_claim_due_jobs_lane"
    assert fake.calls[-1][1]["p_lane"]=="LIVE"
    assert store.claim("worker",limit=1,lane="BACKLOG")==[]
    assert fake.calls[-1][1]["p_lane"]=="BACKLOG"
    assert store.claim("worker",limit=1)==[]
    assert fake.calls[-1][0]=="sxf_base_claim_due_jobs"
    with pytest.raises(ValueError): store.claim("worker",lane="EARLY")

def test_execute_claims_uses_explicit_lane_only_on_opt_in(monkeypatch):
    class S:
        def __init__(self): self.calls=[]
        def claim(self,worker_id,**kw):
            self.calls.append(kw)
            return []
    s=S()
    execute_claims(object(),s,worker_id="w",lane="LIVE")
    execute_claims(object(),s,worker_id="w")
    assert s.calls==[{"limit":1,"lease_seconds":900,"lane":"LIVE"},
                     {"limit":1,"lease_seconds":900}]
    with pytest.raises(ValueError): execute_claims(None,s,worker_id="w",lane="invalid")

def test_live_and_backlog_quotas_without_cross_lane_starvation(monkeypatch):
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**k:{
        "status":"IDLE","enqueued":0,"fixtures":0,
        "paused":False,"pending_due":0,"uncertain":False})
    seen=[]
    def fake_claim(*a,**kw):
        lane=kw.get("lane")
        seen.append(lane)
        if lane=="LIVE":
            return dict(claimed=0,completed=0,waiting_data=0,retry=0,lease_lost=0,commit_uncertain=0)
        return dict(claimed=1,completed=1,waiting_data=0,retry=0,lease_lost=0,commit_uncertain=0)
    monkeypatch.setattr(worker,"execute_claims",fake_claim)
    class S:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":0,"oldest_due_seconds":0,
                      "expired_leases":0},
                    "discovery_cursor":{"initialized":True,"last_scanned_at":AT.isoformat()},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0}}
    report=worker.run_cycle(None,S(),worker_id="w",now=AT,
                            max_jobs=12,max_reconcile=0,priority_lanes=True)
    assert report["backlog_claimed"]==0 and report["live_claimed"]==0
    assert report["completed"]==0 and seen.count("LIVE")==1
    assert seen.count("BACKLOG")==0
    assert report["priority_lanes_enabled"] is True
    assert report["healthy_cycle"] is True

def test_rotation_worker_propagates_selected_hour_and_missing_coverage(monkeypatch):
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**kw:{
        "status":"PAUSED_BACKLOG","enqueued":0,"fixtures":0,
        "paused":True,"pending_due":500,"uncertain":False})
    selections=[]
    def urgent(*a,**kw):
        selections.append(kw["hour_offset"])
        return {"status":"IDEMPOTENT","enqueued":0,"fixtures":1,"pending_due":500,
                "window_start":AT.isoformat(),"window_end":AT.isoformat()}
    monkeypatch.setattr(worker,"near_term_discovery_once",urgent)
    monkeypatch.setattr(worker,"execute_claims",lambda *a,**k:{
        "claimed":0,"completed":0,"waiting_data":0,"retry":0,
        "lease_lost":0,"commit_uncertain":0})
    class S:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":500,"oldest_due_seconds":5000,
                     "expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                     "last_scanned_at":(AT-timedelta(hours=10)).isoformat()},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0}}
    report=worker.run_cycle(None,S(),worker_id="w",now=AT,max_jobs=3,
                            max_reconcile=0,near_term=True,near_term_rotation=True)
    assert selections==[rotation_slot(AT)["hour_offset"]]
    assert report["near_term_rotation_coverage_verified"] is False
    assert "DISCOVERY_STALE" in report["queue_diagnostics"]["alerts"]
    assert report["healthy_cycle"] is True
    with pytest.raises(ValueError):
        worker.run_cycle(None,S(),worker_id="w",near_term_rotation=True)

def test_priority_is_not_silently_active_without_operator_gate(monkeypatch):
    monkeypatch.setenv("SXF_BASE_DURABLE_WORKER_APPROVED","yes")
    monkeypatch.setenv("SXF_BASE_COMPOSITE_INDEX_VERIFIED","yes")
    monkeypatch.delenv("SXF_BASE_PRIORITY_LANES_APPROVED",raising=False)
    with pytest.raises(SystemExit,match="2"):
        worker.main(["--once","--priority-lanes"])


def test_real_health_rpc_fractional_oldest_due_seconds_is_supported():
    h={"checkpoint_queue":{"pending_due":467,"oldest_due_seconds":156621.473528},
       "discovery_cursor":{"initialized":True,"last_scanned_at":AT.isoformat()},
       "reconciliation_queue":{"pending_due":51}}
    result=queue_diagnostics(h,now=AT)
    assert result["checkpoint_oldest_due_seconds"]==156621.473528
    assert "CHECKPOINT_OVERDUE" in result["alerts"]
    h["checkpoint_queue"]={"pending_due":0,"oldest_due_seconds":None}
    result=queue_diagnostics(h,now=AT)
    assert result["checkpoint_oldest_due_seconds"]==0
    h["checkpoint_queue"]={"pending_due":1,"oldest_due_seconds":None}
    with pytest.raises(ValueError):
        queue_diagnostics(h,now=AT)


def test_coverage_state_is_degraded_not_green_even_if_checkpoint_cycle_is_healthy(monkeypatch):
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**k: {
        "status":"PAUSED_BACKLOG","enqueued":0,"fixtures":0,
        "paused":True,"pending_due":467,"uncertain":False})
    monkeypatch.setattr(worker,"execute_claims",lambda *a,**k: {
        "claimed":0,"completed":0,"waiting_data":0,"retry":0,
        "lease_lost":0,"commit_uncertain":0})
    class S:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":467,
                     "oldest_due_seconds":5600.3,"expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                     "last_scanned_at":(AT-timedelta(hours=10)).isoformat()},
                    "reconciliation_queue":{"pending_due":51,"expired_leases":0}}
    report=worker.run_cycle(None,S(),worker_id="worker",max_jobs=3,
                            max_reconcile=0,priority_lanes=True,now=AT)
    assert report["coverage_state"]=="DEGRADED"
    assert report["discovery_fresh"] is False
    assert report["healthy_cycle"] is True  # no lease errors, NOT full coverage
    assert report["production_release_verified"] is False
