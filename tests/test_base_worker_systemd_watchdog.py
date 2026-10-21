"""Tests for native systemd watchdog and bounded checkpoint read recovery."""
from datetime import datetime, timezone
from types import SimpleNamespace
from uuid import uuid4
import socket

import pytest

from base_signal_engine.durable_runtime import (
    CheckpointReadBudgetExceeded, execute_claims,
)
from base_signal_engine.rules import Fixture
from base_signal_engine.scheduler import FixtureRef, CheckpointJob
from base_signal_engine.storage import ClaimedCheckpoint, DurableStoreError
from base_signal_engine.reader import SupabaseMoneywayReader
from base_signal_engine.systemd_watchdog import SystemdNotifier
from base_signal_engine import hetzner_worker

KO = datetime(2026, 10, 24, 12, tzinfo=timezone.utc)
UID = "ef5c99bf-e002-451b-b401-af9174ad53f0"
JOB = CheckpointJob(FixtureRef(UID, KO), 72, "EARLY_CORE")


def _claim():
    return ClaimedCheckpoint(str(uuid4()), str(uuid4()), JOB, 1)


def test_bounded_early_read_fails_to_retry_without_committing():
    clock = [0.0]
    class Reader:
        def load_fixture(self, fixture_uid):
            return Fixture(UID, KO), "native-hash"
        def load_checkpoints(self, *args, **kwargs):
            clock[0] += 181
            return SimpleNamespace(snapshots=(), fetched_rows=0,
                                   discarded_groups=0, hash_drift_rows=0)
    class Store:
        def __init__(self):
            self.events = []
        def claim(self, *args, **kwargs):
            return [_claim()]
        def fail(self, item, reason, **kwargs):
            self.events.append(("fail", reason))
        def complete(self, *args, **kwargs):
            raise AssertionError("never commit an incomplete oversized read")
        def renew(self, *args, **kwargs):
            raise AssertionError("no renewal needed in fake test")
    store = Store()
    stats = execute_claims(Reader(), store, worker_id="w", max_read_seconds=150,
                           clock=lambda: clock[0])
    assert stats["retry"] == 1
    assert stats["completed"] == 0
    assert stats["lease_lost"] == 0
    assert store.events == [("fail", "CHECKPOINTREADBUDGETEXCEEDED")]


def test_lease_renewal_uncertainty_is_never_followed_by_fail_or_commit():
    class Store:
        def claim(self, *args, **kwargs):
            return [_claim()]
        def renew(self, *args, **kwargs):
            raise DurableStoreError("renewal ack ambiguous")
        def fail(self, *args, **kwargs):
            raise AssertionError("cannot mutate uncertain lease")
        def complete(self, *args, **kwargs):
            raise AssertionError("cannot commit uncertain lease")
    reader = SupabaseMoneywayReader("https://example.invalid", "test-token")
    stats = execute_claims(reader, Store(), worker_id="w")
    assert stats["lease_lost"] == 1
    assert stats["retry"] == stats["completed"] == 0


def test_native_watchdog_sends_abstract_socket_datagrams():
    with socket.socket(socket.AF_UNIX, socket.SOCK_DGRAM) as server:
        addr = "\0sxf-test-watchdog-" + str(uuid4())
        server.bind(addr)
        server.settimeout(2)
        notifier = SystemdNotifier(address="@" + addr[1:])
        assert notifier.enabled
        assert notifier.ready()
        assert server.recv(100) == b"READY=1"
        assert notifier.progressed()
        assert server.recv(100) == b"WATCHDOG=1"


def test_missing_systemd_socket_does_not_fake_healthy():
    notifier = SystemdNotifier(address="")
    assert notifier.enabled is False
    assert notifier.ready() is False
    assert notifier.progressed() is False


def test_worker_reports_real_progress_to_service_notifier(monkeypatch):
    signals = []
    class FakeNotifier:
        enabled = True
        def ready(self):
            signals.append("READY")
        def progressed(self):
            signals.append("WATCHDOG")
    monkeypatch.setenv("SXF_BASE_DURABLE_WORKER_APPROVED","yes")
    monkeypatch.setenv("SXF_BASE_COMPOSITE_INDEX_VERIFIED","yes")
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","test-only")
    monkeypatch.setattr(hetzner_worker,"SupabaseMoneywayReader",lambda *a,**kw: object())
    monkeypatch.setattr(hetzner_worker,"SupabaseCheckpointStore",lambda *a,**kw: object())
    monkeypatch.setattr(hetzner_worker,"SystemdNotifier",FakeNotifier)

    def fake_run_cycle(reader,store,**kwargs):
        assert callable(kwargs["progress_hook"])
        kwargs["progress_hook"]()
        return {"discovery":"SKIPPED","healthy_cycle":True,
                "lease_uncertain":0,"commit_uncertain":0,"reconcile_uncertain":0}
    monkeypatch.setattr(hetzner_worker,"run_cycle",fake_run_cycle)
    assert hetzner_worker.main(["--once","--no-discovery"]) == 0
    assert signals == ["READY","WATCHDOG","WATCHDOG"]


def test_fenced_exit_does_not_claim_healthy_watchdog_heartbeat(monkeypatch):
    signals = []
    class FakeNotifier:
        enabled = True
        def ready(self):
            signals.append("READY")
        def progressed(self):
            signals.append("WATCHDOG")
    monkeypatch.setenv("SXF_BASE_DURABLE_WORKER_APPROVED","yes")
    monkeypatch.setenv("SXF_BASE_COMPOSITE_INDEX_VERIFIED","yes")
    monkeypatch.setenv("SUPABASE_URL","https://example.invalid")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY","test-only")
    monkeypatch.setattr(hetzner_worker,"SupabaseMoneywayReader",lambda *a,**kw: object())
    monkeypatch.setattr(hetzner_worker,"SupabaseCheckpointStore",lambda *a,**kw: object())
    monkeypatch.setattr(hetzner_worker,"SystemdNotifier",FakeNotifier)
    monkeypatch.setattr(hetzner_worker,"run_cycle",lambda *a,**kw:{
        "discovery":"SKIPPED","healthy_cycle":False,
        "lease_uncertain":1,"commit_uncertain":0,"reconcile_uncertain":0})
    assert hetzner_worker.main(["--once","--no-discovery"]) == 3
    assert signals == ["READY"]


def test_permanent_service_uses_native_watchdog_without_resurrecting_unsafe_exits():
    from pathlib import Path
    root=Path(__file__).resolve().parents[1]
    config=(root/"deploy/systemd/smartxflow-base-worker.service").read_text()
    assert "Type=notify" in config
    assert "NotifyAccess=main" in config
    assert "WatchdogSec=420" in config
    assert "Restart=on-failure" in config
    assert "RestartPreventExitStatus=3 4" in config
    assert "RuntimeMaxSec=" not in config


def test_stale_expired_lease_is_reclaimable_not_a_worker_crash(monkeypatch):
    calls=[]
    def claim(reader,store,**kwargs):
        calls.append("claim")
        return {"claimed":0,"completed":0,"waiting_data":0,"retry":0,
                "lease_lost":0,"commit_uncertain":0}
    monkeypatch.setattr(hetzner_worker,"execute_claims",claim)
    class Store:
        def health_snapshot(self):
            return {"checkpoint_queue":{"pending_due":1,"expired_leases":1},
                    "reconciliation_queue":{"pending_due":0,"expired_leases":0}}
    report=hetzner_worker.run_cycle(
        object(),Store(),worker_id="autonomous",discover=False,
        max_jobs=1,max_reconcile=0)
    assert calls==["claim"]
    assert report["healthy_cycle"] is True
    assert report["expired_leases_awaiting_reclaim"]==1
    assert report["coverage_state"]=="DEGRADED"
    assert report["production_release_verified"] is False
