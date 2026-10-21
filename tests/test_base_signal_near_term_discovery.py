"""Part 1: bounded near-term discovery must not rewrite cursor or signal truth."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace
import pytest
from base_signal_engine.discovery import near_term_discovery_once
from base_signal_engine import hetzner_worker as worker
from base_signal_engine.storage import DurableStoreError

NOW = datetime(2026, 10, 20, 14, 28, tzinfo=timezone.utc)
UID = "ef5c99bf-e002-451b-b401-af9174ad53f0"

class Catalog:
    def __init__(self, fixtures=None):
        self.rows = fixtures if fixtures is not None else [
            SimpleNamespace(fixture_uid=UID, kickoff_utc=NOW + timedelta(hours=8))]
        self.windows = []
    def list_between(self, start, end):
        self.windows.append((start,end))
        return self.rows

class Store:
    def __init__(self, *, pending=467, initialized=True, fail=False):
        self.pending, self.initialized, self.fail = pending, initialized, fail
        self.calls=[]
    def health_snapshot(self):
        self.calls.append("health")
        return {"checkpoint_queue":{"pending_due":self.pending},
                "discovery_cursor":{"initialized":self.initialized}}
    def enqueue(self, fixtures):
        self.calls.append(("enqueue",len(fixtures)))
        if self.fail:
            raise DurableStoreError("ACK uncertain after send")
        return len(fixtures)*11
    def claim_discovery(self, *a, **kw):
        raise AssertionError("urgent path must not claim historical cursor")
    def advance_discovery(self, *a, **kw):
        raise AssertionError("urgent path must not advance historical cursor")

def test_one_bounded_utc_hour_is_scanned_without_cursor_mutation():
    cat,store=Catalog(),Store()
    result=near_term_discovery_once(None,store,now=NOW,catalog=cat,hour_offset=8)
    assert cat.windows==[(datetime(2026,10,20,22,tzinfo=timezone.utc),
                           datetime(2026,10,20,23,tzinfo=timezone.utc))]
    assert result["status"]=="ENQUEUED" and result["enqueued"]==11
    assert result["source_capture_verified"] is False
    assert result["cursor_advanced"] is False
    assert store.calls==["health",("enqueue",1)]

def test_backlog_250_does_not_block_urgent_but_independent_cap_does():
    cat=Catalog()
    report=near_term_discovery_once(None,Store(pending=467),now=NOW,catalog=cat)
    assert report["status"]=="ENQUEUED"
    cat2=Catalog()
    store=Store(pending=1200)
    result=near_term_discovery_once(None,store,now=NOW,catalog=cat2)
    assert result["status"]=="PAUSED_BACKLOG" and result["paused"]
    assert cat2.windows==[] and store.calls==["health"]

def test_near_term_never_slices_or_silently_exceeds_queue_capacity():
    too_many=[SimpleNamespace(fixture_uid=str(i),kickoff_utc=NOW) for i in range(51)]
    store=Store()
    result=near_term_discovery_once(None,store,now=NOW,catalog=Catalog(too_many))
    assert result["status"]=="WINDOW_TOO_LARGE" and result["fixtures"]==51
    assert store.calls==["health"]
    cap_store=Store(pending=1190)
    result=near_term_discovery_once(None,cap_store,now=NOW,catalog=Catalog())
    assert result["status"]=="PAUSED_CAPACITY"
    assert cap_store.calls==["health"]

def test_uninitialized_missing_health_and_bad_settings_fail_closed():
    store=Store(initialized=False)
    result=near_term_discovery_once(None,store,now=NOW,catalog=Catalog())
    assert result["status"]=="UNINITIALIZED" and store.calls==["health"]
    class BadStore:
        def health_snapshot(self): return {"checkpoint_queue":{"pending_due":None},
                                            "discovery_cursor":{"initialized":True}}
    with pytest.raises(DurableStoreError):
        near_term_discovery_once(None,BadStore(),now=NOW,catalog=Catalog())
    for opts in ({"hour_offset":81},{"hour_offset":-2},{"max_fixtures":101},
                 {"max_pending_due":100},{"hour_offset":True}):
        with pytest.raises(ValueError):
            near_term_discovery_once(None,Store(),now=NOW,catalog=Catalog(),**opts)

def test_ack_uncertainty_not_hidden_as_success():
    with pytest.raises(DurableStoreError,match="ACK uncertain"):
        near_term_discovery_once(None,Store(fail=True),now=NOW,catalog=Catalog())

def test_empty_and_idempotent_windows_keep_honest_counts():
    empty=near_term_discovery_once(None,Store(),now=NOW,catalog=Catalog([]))
    assert empty["status"]=="EMPTY" and empty["enqueued"]==0
    class Idempotent(Store):
        def enqueue(self, fixtures):
            self.calls.append(("enqueue",len(fixtures)))
            return 0
    same=near_term_discovery_once(None,Idempotent(),now=NOW,catalog=Catalog())
    assert same["status"]=="IDEMPOTENT" and same["enqueued"]==0

def test_worker_switch_is_default_off_and_explicit_opt_in(monkeypatch):
    calls=[]
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**kw: {
        "status":"PAUSED_BACKLOG","enqueued":0,"fixtures":0,"paused":True,
        "pending_due":467,"uncertain":False})
    def urgent(*a,**kw):
        calls.append(kw)
        return {"status":"ENQUEUED","enqueued":11,"fixtures":1,"pending_due":467,
                "window_start":NOW.isoformat(),"window_end":NOW.isoformat()}
    monkeypatch.setattr(worker,"near_term_discovery_once",urgent)
    monkeypatch.setattr(worker,"execute_claims",lambda *a,**kw: {
        "claimed":0,"completed":0,"waiting_data":0,"retry":0,
        "lease_lost":0,"commit_uncertain":0})
    class WorkerStore:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":467,"expired_leases":0},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0}}
    s=WorkerStore()
    original=worker.run_cycle(None,s,worker_id="worker",max_jobs=1,max_reconcile=0)
    assert original["near_term_status"]=="DISABLED" and calls==[]
    enabled=worker.run_cycle(None,s,worker_id="worker",max_jobs=1,
                             max_reconcile=0,near_term=True,near_term_hour_offset=8)
    assert enabled["near_term_status"]=="ENQUEUED" and enabled["near_term_enqueued"]==11
    assert enabled["healthy_cycle"] is True and calls[0]["hour_offset"]==8

def test_worker_reports_both_paused_queues_unhealthy(monkeypatch):
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**kw: {
        "status":"PAUSED_BACKLOG","enqueued":0,"fixtures":0,"paused":True,
        "pending_due":1200,"uncertain":False})
    monkeypatch.setattr(worker,"near_term_discovery_once",lambda *a,**kw: {
        "status":"PAUSED_BACKLOG","enqueued":0,"fixtures":0,"pending_due":1200,
        "window_start":NOW.isoformat(),"window_end":NOW.isoformat()})
    monkeypatch.setattr(worker,"execute_claims",lambda *a,**kw: {
        "claimed":0,"completed":0,"waiting_data":0,"retry":0,
        "lease_lost":0,"commit_uncertain":0})
    class WorkerStore:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":1200,"expired_leases":0},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0}}
    report=worker.run_cycle(None,WorkerStore(),worker_id="worker",max_jobs=1,
                            max_reconcile=0,near_term=True)
    assert report["healthy_cycle"] is True
    assert report["near_term_capacity_limited"] is True
    assert report["coverage_state"] == "DEGRADED"
    assert report["production_release_verified"] is False

def test_near_term_never_runs_after_ambiguous_historical_discovery(monkeypatch):
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**kw: {
        "status":"UNCERTAIN","enqueued":0,"fixtures":0,"paused":False,
        "pending_due":0,"uncertain":True})
    monkeypatch.setattr(worker,"near_term_discovery_once",
                        lambda *a,**kw: (_ for _ in ()).throw(AssertionError("must not scan")))
    result=worker.run_cycle(None,object(),worker_id="w",max_jobs=1,
                            max_reconcile=0,near_term=True)
    assert result["lease_uncertain"]==1 and not result["healthy_cycle"]


def test_20_oct_production_pause_does_not_kill_priority_worker(monkeypatch):
    """Real outage: 47 fixtures *11 plus 772 due => controlled PAUSED_CAPACITY.

    No physical fixture is discarded or silently truncated. The next
    rotation minute can still run, while operators see DEGRADED coverage.
    """
    monkeypatch.setattr(worker, "bounded_cursor_discovery_once",
        lambda *a,**k: {"status":"PAUSED_BACKLOG","enqueued":0,
            "fixtures":0,"paused":True,"pending_due":772,"uncertain":False})
    calls=[]
    monkeypatch.setattr(worker,"near_term_discovery_once",lambda *a,**k:
        {"status":"PAUSED_CAPACITY","enqueued":0,"fixtures":47,
         "pending_due":772,"window_start":NOW.isoformat(),
         "window_end":(NOW+timedelta(hours=1)).isoformat()})
    monkeypatch.setattr(worker,"execute_claims",lambda *a,**k:
        (calls.append(k.get("lane","ANY")) or
         {"claimed":1,"completed":0,"waiting_data":1,"retry":0,
          "lease_lost":0,"commit_uncertain":0}))
    class S:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":772,
                    "oldest_due_seconds":253346.042219,
                    "expired_leases":0},
                    "discovery_cursor":{"initialized":True,
                    "last_scanned_at":NOW.isoformat()},
                    "reconciliation_queue":{"pending_due":54,
                    "expired_leases":0}}
    for minute in (0,1,2):
        result=worker.run_cycle(None,S(),worker_id="simulated",
            max_jobs=6,max_reconcile=0,priority_lanes=True,
            near_term=True,near_term_rotation=True,
            now=NOW+timedelta(minutes=minute))
        assert result["near_term_status"]=="PAUSED_CAPACITY"
        assert result["near_term_capacity_limited"] is True
        assert result["near_term_rotation_coverage_verified"] is False
        assert result["coverage_state"]=="DEGRADED"
        assert result["healthy_cycle"] is True
        assert result["production_release_verified"] is False
        assert result["live_claimed"]==6 and result["backlog_claimed"]==0
    assert len(calls)==18


def test_unknown_near_term_source_failure_still_stops_worker(monkeypatch):
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**k:
        {"status":"PAUSED_BACKLOG","enqueued":0,"fixtures":0,
         "paused":True,"pending_due":600,"uncertain":False})
    def broken(*a,**k):
        raise ValueError("bad catalog")
    monkeypatch.setattr(worker,"near_term_discovery_once",broken)
    monkeypatch.setattr(worker,"execute_claims",lambda *a,**k:
        {"claimed":0,"completed":0,"waiting_data":0,"retry":0,
         "lease_lost":0,"commit_uncertain":0})
    class S:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":600,
                "oldest_due_seconds":123,"expired_leases":0},
                "reconciliation_queue":{"pending_due":0,"expired_leases":0},
                "discovery_cursor":{"initialized":True,
                    "last_scanned_at":NOW.isoformat()}}
    report=worker.run_cycle(None,S(),worker_id="w",max_jobs=3,
                            max_reconcile=0,near_term=True,near_term_rotation=True,now=NOW)
    assert report["near_term_status"]=="ERROR_VALUEERROR"
    assert report["healthy_cycle"] is False
    assert report["near_term_capacity_limited"] is False


def test_production_priority_worker_can_use_bounded_2500_due_backlog(monkeypatch):
    """The previous 1200 cap blocked legitimate heavy-match fanout forever."""
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**kw: {
        "status":"PAUSED_BACKLOG","enqueued":0,"fixtures":0,
        "pending_due":1128,"paused":True,"uncertain":False})
    received=[]
    def urgent(*a,**kw):
        received.append(kw["max_pending_due"])
        return {"status":"ENQUEUED","enqueued":11,"fixtures":1,"pending_due":1128,
                "window_start":NOW.isoformat(),"window_end":NOW.isoformat()}
    monkeypatch.setattr(worker,"near_term_discovery_once",urgent)
    monkeypatch.setattr(worker,"execute_claims",lambda *a,**kw:{
        "claimed":0,"completed":0,"waiting_data":0,"retry":0,
        "lease_lost":0,"commit_uncertain":0})
    class Health:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":1128,
                "expired_leases":0,"oldest_due_seconds":50000},
                "reconciliation_queue":{"pending_due":0,"expired_leases":0},
                "discovery_cursor":{"initialized":True,
                    "last_scanned_at":NOW.isoformat()}}
    r=worker.run_cycle(None,Health(),worker_id="prod",now=NOW,
        near_term=True,near_term_rotation=True,priority_lanes=True,
        max_jobs=3,max_reconcile=0)
    assert r["near_term_status"]=="ENQUEUED"
    assert r["healthy_cycle"] is True
    assert received==[2500]
    received.clear()
    worker.run_cycle(None,Health(),worker_id="old",now=NOW,
        near_term=True,near_term_rotation=True,priority_lanes=False,
        max_jobs=1,max_reconcile=0)
    assert received==[1200]
