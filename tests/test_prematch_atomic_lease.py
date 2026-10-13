from types import SimpleNamespace

from core import prematch_atomic_lease as lease


class FakeResponse:
    def __init__(self, status_code=200, body=None, text=""):
        self.status_code = status_code
        self._body = body if body is not None else {}
        self.text = text

    def json(self):
        return self._body


def test_acquire_runtime_lease_uses_service_role_rpc():
    seen = {}

    def fake_post(url, headers=None, json=None, timeout=None):
        seen.update(url=url, headers=headers, json=json, timeout=timeout)
        return FakeResponse(
            200,
            {
                "acquired": True,
                "holder": "hetzner-prod",
                "lease_until": "2026-10-13T16:30:00+00:00",
                "error": None,
            },
        )

    result = lease.acquire_runtime_lease(
        "https://example.supabase.co",
        "service-role",
        "hetzner-prod",
        ttl_seconds=420,
        request_post=fake_post,
    )

    assert result["acquired"] is True
    assert result["holder"] == "hetzner-prod"
    assert seen["url"].endswith("/rest/v1/rpc/acquire_scraper_runtime_lease")
    assert seen["headers"]["Authorization"] == "Bearer service-role"
    assert seen["json"] == {
        "p_lease_name": "prematch-production",
        "p_holder": "hetzner-prod",
        "p_ttl_seconds": 420,
    }


def test_atomic_guard_fails_closed_when_other_runtime_holds_lease(monkeypatch, tmp_path):
    calls = []
    runtime = SimpleNamespace()
    runtime.SCRAPER_SOURCE = "replit-preview"
    runtime.check_master_status = lambda *_: (True, "legacy_would_allow")
    runtime.main = lambda: calls.append("main") or True

    monkeypatch.setenv("SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    monkeypatch.setenv("SMARTXFLOW_RUNTIME_ID", "replit-preview")
    monkeypatch.setenv("SMARTXFLOW_PREMATCH_LOCAL_LOCK_PATH", str(tmp_path / "lock"))
    monkeypatch.setattr(
        lease,
        "acquire_runtime_lease",
        lambda *args, **kwargs: {
            "acquired": False,
            "holder": "hetzner-prod",
            "lease_until": "2026-10-13T16:30:00+00:00",
            "error": None,
        },
    )

    lease.install_authoritative_atomic_lease_guard(runtime)

    assert runtime.main() is False
    assert calls == []


def test_atomic_guard_bypasses_racy_legacy_election_after_lease(monkeypatch, tmp_path):
    legacy_checks = []
    observed = []
    runtime = SimpleNamespace()
    runtime.SCRAPER_SOURCE = "replit-preview"

    def legacy_check(*_):
        legacy_checks.append(True)
        return False, "other heartbeat"

    runtime.check_master_status = legacy_check

    def original_main():
        observed.append(runtime.check_master_status("url", "key"))
        return True

    runtime.main = original_main

    monkeypatch.setenv("SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE", "true")
    monkeypatch.setenv("SUPABASE_URL", "https://example.supabase.co")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "service-role")
    monkeypatch.setenv("SMARTXFLOW_RUNTIME_ID", "replit-preview")
    monkeypatch.setenv("SMARTXFLOW_PREMATCH_LOCAL_LOCK_PATH", str(tmp_path / "lock"))
    monkeypatch.setattr(
        lease,
        "acquire_runtime_lease",
        lambda *args, **kwargs: {
            "acquired": True,
            "holder": "replit-preview",
            "lease_until": "2026-10-13T16:30:00+00:00",
            "error": None,
        },
    )

    lease.install_authoritative_atomic_lease_guard(runtime)

    assert runtime.main() is True
    assert observed == [(True, "atomic_db_lease")]
    assert legacy_checks == []
