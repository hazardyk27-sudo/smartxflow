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
    for opts in ({"hour_offset":13},{"hour_offset":-2},{"max_fixtures":51},
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
    assert report["healthy_cycle"] is False

def test_near_term_never_runs_after_ambiguous_historical_discovery(monkeypatch):
    monkeypatch.setattr(worker,"bounded_cursor_discovery_once",lambda *a,**kw: {
        "status":"UNCERTAIN","enqueued":0,"fixtures":0,"paused":False,
        "pending_due":0,"uncertain":True})
    monkeypatch.setattr(worker,"near_term_discovery_once",
                        lambda *a,**kw: (_ for _ in ()).throw(AssertionError("must not scan")))
    result=worker.run_cycle(None,object(),worker_id="w",max_jobs=1,
                            max_reconcile=0,near_term=True)
    assert result["lease_uncertain"]==1 and not result["healthy_cycle"]
