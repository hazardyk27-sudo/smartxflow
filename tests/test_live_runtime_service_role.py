from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _load_runtime():
    path = ROOT / "live_runtime.py"
    spec = importlib.util.spec_from_file_location("live_runtime_test", path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)
    return module


def test_live_runtime_replaces_legacy_anon_slot_with_service_role():
    runtime = _load_runtime()
    env = {
        "SUPABASE_ANON_KEY": "public-anon-key",
        "SUPABASE_SERVICE_ROLE_KEY": "server-service-key",
    }

    selected = runtime.install_live_service_role_guard(env)

    assert selected == "server-service-key"
    assert env["SUPABASE_ANON_KEY"] == "server-service-key"
    assert env["SMARTXFLOW_LIVE_CREDENTIAL_MODE"] == "service_role"


def test_live_runtime_fails_closed_without_service_role():
    runtime = _load_runtime()
    env = {"SUPABASE_ANON_KEY": "public-anon-key"}

    with pytest.raises(RuntimeError, match="requires SUPABASE_SERVICE_ROLE_KEY"):
        runtime.install_live_service_role_guard(env)

    assert env["SUPABASE_ANON_KEY"] == "public-anon-key"
    assert "SMARTXFLOW_LIVE_CREDENTIAL_MODE" not in env


def test_live_runtime_accepts_only_canonical_live_scraper_target(tmp_path):
    runtime = _load_runtime()
    canonical = tmp_path / "live_scraper.py"
    canonical.write_text("# test target\n", encoding="utf-8")

    assert runtime._resolve_live_target(["live_runtime.py", str(canonical)]) == canonical.resolve()

    unexpected = tmp_path / "other_worker.py"
    unexpected.write_text("# no\n", encoding="utf-8")
    with pytest.raises(RuntimeError, match="unexpected live runtime target"):
        runtime._resolve_live_target(["live_runtime.py", str(unexpected)])
