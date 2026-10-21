"""Legacy cleanup must remain disabled unless deliberately approved."""
import sys
import types
from core import retention_guard

def test_default_blocks_even_when_learning_holds_disabled(monkeypatch):
    monkeypatch.delenv("SMARTXFLOW_RETENTION_CLEANUP_APPROVED", raising=False)
    monkeypatch.delenv("SMARTXFLOW_DISABLE_RETENTION_CLEANUP", raising=False)
    monkeypatch.setattr(retention_guard, "_learning_archive_guard_enabled", lambda: False)
    assert retention_guard.retention_cleanup_disabled() is True

def test_explicit_approval_still_respects_emergency_disable(monkeypatch):
    monkeypatch.setattr(retention_guard, "_learning_archive_guard_enabled", lambda: False)
    assert retention_guard.retention_cleanup_disabled({
        "SMARTXFLOW_RETENTION_CLEANUP_APPROVED": "true",
        "SMARTXFLOW_DISABLE_RETENTION_CLEANUP": "1",
    }) is True
    assert retention_guard.retention_cleanup_disabled({
        "SMARTXFLOW_RETENTION_CLEANUP_APPROVED": "true",
    }) is False

def test_default_denies_web_supabase_cleanup_without_calling_legacy(monkeypatch):
    monkeypatch.delenv("SMARTXFLOW_RETENTION_CLEANUP_APPROVED", raising=False)
    monkeypatch.delenv("SMARTXFLOW_DISABLE_RETENTION_CLEANUP", raising=False)
    monkeypatch.setattr(retention_guard, "_learning_archive_guard_enabled", lambda: False)
    calls = []
    class FakeClient:
        def cleanup_old_matches(self, cutoff):
            calls.append(cutoff)
            return {"moneyway_snapshots": 1000}
    package = types.ModuleType("services")
    package.__path__ = []
    fake = types.ModuleType("services.supabase_client")
    fake.SupabaseClient = FakeClient
    monkeypatch.setitem(sys.modules, "services", package)
    monkeypatch.setitem(sys.modules, "services.supabase_client", fake)
    assert retention_guard.install_supabase_cleanup_guard() is True
    assert FakeClient().cleanup_old_matches("2026-10-15") == {}
    assert calls == []
