import importlib.util
import sys
import types
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]
ENTRYPOINT = ROOT / "prematch_authoritative_runtime.py"
SUPERVISOR = ROOT / "run_services.sh"
FLAG = "SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE"


def _load_entrypoint():
    spec = importlib.util.spec_from_file_location(
        "prematch_authoritative_runtime_under_test",
        ENTRYPOINT,
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_runtime_overrides_false_flag_and_anon_slot_before_import(monkeypatch):
    module = _load_entrypoint()
    calls = []

    fake_scheduled = types.ModuleType("scheduled_scraper")
    fake_scheduled.run_loop = lambda: calls.append("run_loop")

    monkeypatch.setenv(FLAG, "false")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "server-service-key")
    monkeypatch.setitem(sys.modules, "scheduled_scraper", fake_scheduled)
    monkeypatch.setattr(
        module,
        "_install_authoritative_history_guard",
        lambda: calls.append("history_guard"),
    )

    module.run()

    assert module.os.environ[FLAG] == "true"
    assert module.os.environ["SUPABASE_ANON_KEY"] == "server-service-key"
    assert module.os.environ["SMARTXFLOW_PREMATCH_CREDENTIAL_MODE"] == "service_role"
    assert calls == ["history_guard", "run_loop"]


def test_runtime_fails_closed_without_service_role(monkeypatch):
    module = _load_entrypoint()
    imported = []

    fake_scheduled = types.ModuleType("scheduled_scraper")
    fake_scheduled.run_loop = lambda: imported.append("run_loop")

    monkeypatch.setenv(FLAG, "false")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "public-anon-key")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "scheduled_scraper", fake_scheduled)

    with pytest.raises(SystemExit, match="SUPABASE_SERVICE_ROLE_KEY"):
        module.run()

    assert module.os.environ[FLAG] == "true"
    assert module.os.environ["SUPABASE_ANON_KEY"] == "public-anon-key"
    assert imported == []


def test_history_guard_skips_history_after_failed_current_and_recovers(monkeypatch):
    module = _load_entrypoint()

    class FakeWriter:
        def __init__(self):
            self.last_write_errors = []
            self.history_calls = []

        def append_history(self, table, rows, scraped_at):
            self.history_calls.append((table, list(rows), scraped_at))
            return True

    outcomes = {
        "moneyway_1x2": False,
    }

    fake_prematch = types.ModuleType("betwatch_prematch")
    fake_prematch.SupabaseWriter = FakeWriter

    def fake_sync(writer, table, rows, logger=None):
        return outcomes[table]

    fake_prematch.sync_current_table = fake_sync
    monkeypatch.setitem(sys.modules, "betwatch_prematch", fake_prematch)

    module._install_authoritative_history_guard()
    writer = FakeWriter()

    assert fake_prematch.sync_current_table(
        writer,
        "moneyway_1x2",
        [{"fixture_uid": "uid-1"}],
    ) is False
    assert fake_prematch.SupabaseWriter.append_history(
        writer,
        "moneyway_1x2_history",
        [{"fixture_uid": "uid-1"}],
        "2026-10-13 18:00:00",
    ) is False
    assert writer.history_calls == []
    assert writer.last_write_errors == [
        "fixture_uid_current_write:moneyway_1x2"
    ]

    outcomes["moneyway_1x2"] = True
    assert fake_prematch.sync_current_table(
        writer,
        "moneyway_1x2",
        [{"fixture_uid": "uid-1"}],
    ) is True
    assert fake_prematch.SupabaseWriter.append_history(
        writer,
        "moneyway_1x2_history",
        [{"fixture_uid": "uid-1"}],
        "2026-10-13 18:05:00",
    ) is True
    assert len(writer.history_calls) == 1

    # Installing twice must not stack wrappers.
    module._install_authoritative_history_guard()
    assert fake_prematch._SXF_AUTHORITATIVE_HISTORY_GUARD is True


def test_supervisor_has_no_direct_legacy_prematch_entrypoint():
    text = SUPERVISOR.read_text()

    assert "python prematch_authoritative_runtime.py" in text
    assert "python scheduled_scraper.py" not in text


def test_entrypoint_sets_identity_and_service_role_before_scraper_imports():
    text = ENTRYPOINT.read_text()

    set_pos = text.index('os.environ[_CANONICAL_FLAG] = "true"')
    credential_pos = text.index("    _install_service_role_credentials()", set_pos)
    guard_pos = text.index("    _install_authoritative_history_guard()", credential_pos)
    import_pos = text.index("from scheduled_scraper import run_loop", guard_pos)
    assert set_pos < credential_pos < guard_pos < import_pos
