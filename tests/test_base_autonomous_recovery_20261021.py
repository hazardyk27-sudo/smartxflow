"""Regression tests for the 21 Oct permanent Base discovery/worker repair."""
from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

import pytest

from base_signal_engine import discovery, hetzner_worker
from base_signal_engine.rotation import HOUR_OFFSETS
from base_signal_engine.storage import (
    DurableStoreError, ReadOnlyStoreError, SupabaseCheckpointStore,
)

AT = datetime(2026, 10, 21, 1, 0, tzinfo=timezone.utc)


class FakeResponse:
    status_code = 503

    def json(self):
        raise AssertionError("HTTP 503 should fail before JSON")


class HttpFailure:
    def post(self, *args, **kwargs):
        return FakeResponse()


def test_readonly_failure_is_safe_to_retry_but_unknown_writes_remain_fenced():
    store = SupabaseCheckpointStore(
        "https://source.invalid", "private-test-only", session=HttpFailure())
    with pytest.raises(ReadOnlyStoreError):
        store.health_snapshot()
    with pytest.raises(DurableStoreError) as error:
        store._rpc("sxf_base_enqueue_jobs", {"p_jobs": []})
    assert not isinstance(error.value, ReadOnlyStoreError)
    assert "private-test-only" not in str(error.value)


def test_main_restarts_only_safe_read_outage_not_ambiguous_write(monkeypatch):
    monkeypatch.setenv("SXF_BASE_DURABLE_WORKER_APPROVED", "yes")
    monkeypatch.setenv("SXF_BASE_COMPOSITE_INDEX_VERIFIED", "yes")
    monkeypatch.setenv("SUPABASE_URL", "https://source.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-only")
    monkeypatch.setattr(hetzner_worker, "SupabaseMoneywayReader", lambda *a, **kw: object())
    monkeypatch.setattr(hetzner_worker, "SupabaseCheckpointStore", lambda *a, **kw: object())

    def safe_error(*args, **kwargs):
        raise ReadOnlyStoreError("health RPC failed")
    monkeypatch.setattr(hetzner_worker, "run_cycle", safe_error)
    assert hetzner_worker.main(["--once"]) == 2

    def uncertain(*args, **kwargs):
        raise DurableStoreError("enqueue ACK uncertain")
    monkeypatch.setattr(hetzner_worker, "run_cycle", uncertain)
    assert hetzner_worker.main(["--once"]) == 3


def test_durable_cursor_discovery_is_not_stopped_by_old_missing_source_debt(monkeypatch):
    class Store:
        def health_snapshot(self):
            return {
                "checkpoint_queue": {"pending_due": 1500},
                "discovery_cursor": {"initialized": True}
            }
    observations = []
    def fake_discovery(*args, **kwargs):
        observations.append(kwargs)
        return dict(uncertain=False, retry=False, idle=False,
                    advanced=True, enqueued=33, fixtures=3)
    monkeypatch.setattr(discovery, "discover_window_once", fake_discovery)
    report = discovery.bounded_cursor_discovery_once(
        object(), Store(), worker_id="prod", now=AT, max_fixtures=100,
        allow_high_backlog=True)
    assert report["status"] == "OK"
    assert report["backpressure"] is True
    assert not report["paused"]
    assert report["enqueued"] == 33
    assert observations[0]["max_fixtures"] == 100


def test_t72_and_later_fixture_windows_are_seen_under_backpressure():
    assert set(range(13, 81)).issubset(set(HOUR_OFFSETS))
    assert set((72, 60, 40, 24, 12, 8, 6, 0, -1)).issubset(set(HOUR_OFFSETS))

    class Store:
        def health_snapshot(self):
            return {
                "checkpoint_queue": {"pending_due": 2000},
                "discovery_cursor": {"initialized": True}
            }
        def enqueue(self, fixtures):
            return 11 * len(fixtures)
    class Catalog:
        def __init__(self):
            self.windows = []
        def list_between(self, start, end):
            self.windows.append((start, end))
            return [SimpleNamespace(fixture_uid="fake", kickoff_utc=AT+timedelta(hours=76))]
    catalog = Catalog()
    result = discovery.near_term_discovery_once(
        None, Store(), now=AT, hour_offset=76,
        max_fixtures=100, allow_high_backlog=True, catalog=catalog)
    assert result["status"] == "ENQUEUED"
    assert result["backpressure"] is True
    assert result["enqueued"] == 11
    assert catalog.windows[0][0] == datetime(2026,10,24,5,tzinfo=timezone.utc)


def test_autonomous_worker_enables_recovery_only_with_both_production_modes(monkeypatch):
    discovery_calls = []
    urgent_calls = []
    def cursor(*args, **kwargs):
        discovery_calls.append(kwargs)
        return {"status":"OK","enqueued":0,"fixtures":0,
                "paused":False,"pending_due":1800,"uncertain":False,
                "backpressure":True}
    def urgent(*args, **kwargs):
        urgent_calls.append(kwargs)
        return {"status":"EMPTY","enqueued":0,"fixtures":0,
                "pending_due":1800,"backpressure":True,
                "window_start":AT.isoformat(),"window_end":AT.isoformat()}
    monkeypatch.setattr(hetzner_worker,"bounded_cursor_discovery_once", cursor)
    monkeypatch.setattr(hetzner_worker,"near_term_discovery_once", urgent)
    monkeypatch.setattr(hetzner_worker,"execute_claims",lambda *args, **kwargs:
        {"claimed":0,"completed":0,"waiting_data":0,"retry":0,
         "lease_lost":0,"commit_uncertain":0})

    class Store:
        def health_snapshot(self):
            return {
                "checkpoint_queue": {"pending_due":1800,
                                     "oldest_due_seconds":4000.0,
                                     "expired_leases":0},
                "discovery_cursor": {"initialized":True,
                                     "last_scanned_at":AT.isoformat()},
                "reconciliation_queue": {"pending_due":0,
                                         "expired_leases":0}
            }
    status = hetzner_worker.run_cycle(
        object(), Store(), worker_id="prod", now=AT,
        max_jobs=3, max_reconcile=0, near_term=True,
        near_term_rotation=True, priority_lanes=True)
    assert discovery_calls[0]["allow_high_backlog"] is True
    assert urgent_calls[0]["allow_high_backlog"] is True
    assert status["discovery_backpressure"] is True
    assert status["near_term_backpressure"] is True
    assert status["healthy_cycle"] is True
    assert status["coverage_state"] == "DEGRADED"
