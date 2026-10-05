from __future__ import annotations

import importlib.util
from dataclasses import dataclass
from pathlib import Path

import core.fixture_identity_shadow as shadow


@dataclass
class _Response:
    status_code: int
    payload: object

    def raise_for_status(self):
        if self.status_code >= 400:
            raise RuntimeError(f"HTTP {self.status_code}")

    def json(self):
        return self.payload


class _Writer:
    def _rest_url(self, table):
        return f"https://example.supabase.co/rest/v1/{table}"

    def _headers(self):
        return {"Authorization": "Bearer test"}


def _match(match_id, home="A", away="B", league="League", kickoff="2026-10-06T18:00:00Z"):
    return {
        "match_id": match_id,
        "teams": {"v1": home, "v2": away},
        "league": league,
        "kickoff": kickoff,
    }


def setup_function():
    shadow.clear_betwatch_identity_stage()


def test_stage_fails_closed_when_provider_id_missing():
    batch = shadow.build_betwatch_identity_stage([
        _match(None),
        _match(1002, home="C", away="D"),
    ])
    assert batch.total_rows == 2
    assert batch.eligible_rows == 1
    assert batch.missing_provider_ids == 1
    assert len(batch.hash_to_event_ids) == 1


def test_same_hash_with_two_provider_ids_is_excluded(monkeypatch):
    batch = shadow.stage_betwatch_identity_payload([
        _match(1001),
        _match(2002),
    ])
    assert len(batch.hash_to_event_ids) == 1

    def unexpected_get(*args, **kwargs):
        raise AssertionError("DB lookup must not run for ambiguous hash")

    monkeypatch.setattr(shadow.requests, "get", unexpected_get)
    stats = shadow.flush_staged_betwatch_identity_shadow(_Writer())
    assert stats["hash_collision_groups"] == 1
    assert stats["submitted_bindings"] == 0
    assert stats["error"] is None


def test_shadow_binding_uses_fixture_uid_and_rpc(monkeypatch):
    shadow.stage_betwatch_identity_payload([
        _match(1001),
        _match(2002, home="C", away="D"),
    ])

    captured = {}

    def fake_get(url, **kwargs):
        hashes_filter = kwargs["params"]["match_id_hash"]
        assert hashes_filter.startswith("in.(")
        values = hashes_filter[4:-1].split(",")
        return _Response(
            200,
            [
                {"match_id_hash": values[0], "fixture_uid": "11111111-1111-1111-1111-111111111111"},
                {"match_id_hash": values[1], "fixture_uid": "22222222-2222-2222-2222-222222222222"},
            ],
        )

    def fake_post(url, **kwargs):
        assert url.endswith("/rpc/record_fixture_identity_shadow_batch")
        captured.update(kwargs["json"])
        return _Response(
            200,
            [{
                "inserted_count": 2,
                "matched_count": 0,
                "conflict_count": 0,
                "received_count": 2,
            }],
        )

    monkeypatch.setattr(shadow.requests, "get", fake_get)
    monkeypatch.setattr(shadow.requests, "post", fake_post)

    stats = shadow.flush_staged_betwatch_identity_shadow(
        _Writer(), observed_at="2026-10-06T18:00:00+00:00"
    )
    assert captured["p_source"] == "betwatch"
    assert len(captured["p_bindings"]) == 2
    assert stats["submitted_bindings"] == 2
    assert stats["inserted_count"] == 2
    assert stats["conflict_count"] == 0


def test_shadow_db_failure_never_raises_into_legacy_flow(monkeypatch):
    shadow.stage_betwatch_identity_payload([_match(1001)])

    def broken_get(*args, **kwargs):
        raise RuntimeError("db unavailable")

    monkeypatch.setattr(shadow.requests, "get", broken_get)
    stats = shadow.flush_staged_betwatch_identity_shadow(_Writer())
    assert stats["attempted"] is True
    assert stats["error"] == "db unavailable"


def test_desktop_betwatch_client_stages_prematch_payload(monkeypatch):
    """The deployed runtime resolves the desktop client copy first on sys.path."""
    client_path = (
        Path(__file__).resolve().parents[1]
        / "desktop"
        / "scraper_standalone"
        / "betwatch_client.py"
    )
    spec = importlib.util.spec_from_file_location("desktop_betwatch_client_test", client_path)
    module = importlib.util.module_from_spec(spec)
    assert spec and spec.loader
    spec.loader.exec_module(module)

    payload = [_match(9001), _match(9002, home="C", away="D")]
    monkeypatch.setattr(module.requests, "get", lambda *args, **kwargs: _Response(200, payload))

    shadow.clear_betwatch_identity_stage()
    returned = module.fetch_prematch(timeout=1)
    staged = shadow.consume_betwatch_identity_stage()

    assert returned == payload
    assert staged is not None
    assert staged.total_rows == 2
    assert staged.eligible_rows == 2
    assert staged.missing_provider_ids == 0
