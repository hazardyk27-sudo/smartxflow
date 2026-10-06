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


def test_runtime_overrides_false_flag_before_importing_scheduled_scraper(monkeypatch):
    module = _load_entrypoint()
    calls = []

    fake_scheduled = types.ModuleType("scheduled_scraper")
    fake_scheduled.run_loop = lambda: calls.append("run_loop")

    monkeypatch.setenv(FLAG, "false")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role-present")
    monkeypatch.setitem(sys.modules, "scheduled_scraper", fake_scheduled)

    module.run()

    assert module.os.environ[FLAG] == "true"
    assert calls == ["run_loop"]


def test_runtime_fails_closed_without_service_role(monkeypatch):
    module = _load_entrypoint()
    imported = []

    fake_scheduled = types.ModuleType("scheduled_scraper")
    fake_scheduled.run_loop = lambda: imported.append("run_loop")

    monkeypatch.setenv(FLAG, "false")
    monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
    monkeypatch.setitem(sys.modules, "scheduled_scraper", fake_scheduled)

    with pytest.raises(SystemExit, match="SUPABASE_SERVICE_ROLE_KEY"):
        module.run()

    assert module.os.environ[FLAG] == "true"
    assert imported == []


def test_supervisor_has_no_direct_legacy_prematch_entrypoint():
    text = SUPERVISOR.read_text()

    assert "python prematch_authoritative_runtime.py" in text
    assert "python scheduled_scraper.py" not in text


def test_entrypoint_sets_flag_before_scheduled_scraper_import():
    text = ENTRYPOINT.read_text()

    set_pos = text.index('os.environ[_CANONICAL_FLAG] = "true"')
    import_pos = text.index("from scheduled_scraper import run_loop")
    assert set_pos < import_pos
