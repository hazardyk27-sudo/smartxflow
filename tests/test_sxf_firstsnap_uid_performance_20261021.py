"""Regression tests for low-IO indexed first historical odds lookup."""
from types import SimpleNamespace
from unittest.mock import Mock

import sinyal_first_snapshot_fetch as sxf

UID = "f9d7a59a-8fbf-4f1f-8e48-6be11d7498e7"
CURRENT = {
    "home": "Fleetwood Town", "away": "Arsenal",
    "date": "2026-10-27T20:00:00+00:00", "fixture_uid": UID,
}
KEY = "Fleetwood Town|Arsenal|2026-10-27T20:00:00+00:00"


def make_engine():
    logs = []
    return SimpleNamespace(
        SUPABASE_URL="https://example.invalid",
        _headers_read=lambda: {"apikey": "TEST"},
        _row_has_valid_odds=lambda row: all(row.get(k) not in (None, "") for k in ("odds1", "oddsx", "odds2")),
        log=logs.append,
        logs=logs,
    )


def valid_row(**overrides):
    row = {**CURRENT, "odds1": "1.7", "oddsx": "3.2", "odds2": "4.4", "scraped_at": "2026-10-21T20:40:00+03:00"}
    row.update(overrides)
    return row


def test_uid_hit_requires_one_small_indexed_request(monkeypatch):
    get = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: [valid_row()]))
    monkeypatch.setattr(sxf.requests, "get", get)
    key, row, err = sxf._fetch_one_history_row(make_engine(), KEY, CURRENT)
    assert (key, err) == (KEY, None)
    assert row["odds1"] == "1.7"
    params = dict(get.call_args.kwargs["params"])
    assert params["fixture_uid"] == f"eq.{UID}"
    assert "home" not in params and "date" not in params and "away" not in params
    assert params["order"] == "scraped_at.asc"
    assert get.call_count == 1


def test_identity_mismatch_fails_closed(monkeypatch):
    get = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: [valid_row(away="Another Team")]))
    monkeypatch.setattr(sxf.requests, "get", get)
    _key, row, err = sxf._fetch_one_history_row(make_engine(), KEY, CURRENT)
    assert row is None and err == "physical fixture identity mismatch"
    assert get.call_count == 1


def test_uid_miss_falls_back_for_legacy_history(monkeypatch):
    get = Mock(side_effect=[
        SimpleNamespace(status_code=200, json=lambda: []),
        SimpleNamespace(status_code=200, json=lambda: [valid_row(fixture_uid=None)]),
    ])
    monkeypatch.setattr(sxf.requests, "get", get)
    _key, row, err = sxf._fetch_one_history_row(make_engine(), KEY, CURRENT)
    assert err is None and row["odds2"] == "4.4"
    assert get.call_count == 2
    fallback = dict(get.call_args.kwargs["params"])
    assert fallback["home"] == f"eq.{CURRENT['home']}"
    assert fallback["away"] == f"eq.{CURRENT['away']}"
    assert fallback["date"] == f"eq.{CURRENT['date']}"


def test_invalid_uid_uses_safe_composite_fallback(monkeypatch):
    get = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: [valid_row(fixture_uid=None)]))
    monkeypatch.setattr(sxf.requests, "get", get)
    _key, row, err = sxf._fetch_one_history_row(make_engine(), KEY, {**CURRENT,"fixture_uid": "not-a-uuid"})
    assert err is None and row
    assert "fixture_uid" not in dict(get.call_args.kwargs["params"])


def test_legacy_fallback_does_not_cross_physical_fixture(monkeypatch):
    get = Mock(side_effect=[
        SimpleNamespace(status_code=200, json=lambda: []),
        SimpleNamespace(status_code=200, json=lambda: [valid_row(fixture_uid="d96b90a5-32b4-4f85-a9ae-a23352d43c05")]),
    ])
    monkeypatch.setattr(sxf.requests, "get", get)
    _, row, err = sxf._fetch_one_history_row(make_engine(), KEY, CURRENT)
    assert row is None and err == "legacy fallback fixture_uid mismatch"


def test_no_active_key_list_never_triggers_unbounded_legacy_scan():
    calls = []
    engine = make_engine()
    result = sxf._indexed_fetch(engine, lambda keys: calls.append(keys), active_keys=None)
    assert result == {}
    assert calls == []
    assert any("refusing full-table legacy scan" in log for log in engine.logs)


def test_uid_current_source_selected(monkeypatch):
    get = Mock(return_value=SimpleNamespace(status_code=200, json=lambda: [{**CURRENT, "odds1":"1.5","oddsx":"3.0","odds2":"4.0"}]))
    monkeypatch.setattr(sxf.requests, "get", get)
    got = sxf._fetch_current_candidates(make_engine(), {KEY})
    assert KEY in got and got[KEY]["fixture_uid"] == UID
    assert "fixture_uid" in dict(get.call_args.kwargs["params"])["select"]


def test_error_fails_closed_without_unbounded_fallback(monkeypatch):
    get = Mock(return_value=SimpleNamespace(status_code=500, text="unavailable"))
    monkeypatch.setattr(sxf.requests, "get", get)
    _, row, err = sxf._fetch_one_history_row(make_engine(), KEY, CURRENT)
    assert row is None and err.startswith("HTTP 500")
    assert get.call_count == 1
