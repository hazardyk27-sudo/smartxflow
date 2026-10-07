from __future__ import annotations

from types import SimpleNamespace

import sinyal_first_snapshot_fetch as indexed


class Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = [] if payload is None else payload
        self.text = text

    def json(self):
        return self._payload


def _valid_odds(row):
    for field in ("odds1", "oddsx", "odds2"):
        value = row.get(field)
        if value is None or not str(value).strip():
            return False
        try:
            if float(str(value).strip()) <= 0:
                return False
        except Exception:
            return False
    return True


def _engine(legacy_result=None):
    calls = {"legacy": 0, "logs": []}

    def legacy(active_keys=None):
        calls["legacy"] += 1
        return legacy_result if legacy_result is not None else {"legacy": []}

    engine = SimpleNamespace(
        SUPABASE_URL="https://example.supabase.co",
        _headers_read=lambda: {"apikey": "test"},
        _row_has_valid_odds=_valid_odds,
        log=lambda message: calls["logs"].append(message),
        fetch_first_snapshots=legacy,
    )
    return engine, calls


def _params_dict(params):
    result = {}
    for key, value in params:
        result.setdefault(key, []).append(value)
    return result


def setup_function():
    indexed._cache.clear()


def test_indexed_loader_returns_same_first_valid_identity_and_hash_alias(monkeypatch):
    engine, calls = _engine()
    indexed.install_first_snapshot_fetch(engine)

    active_key = "England|Croatia|2026-11-12T19:45:00+00:00"
    current_rows = [
        {
            "home": "England",
            "away": "Croatia",
            "date": "2026-11-12T19:45:00+00:00",
            "odds1": "1.20",
            "oddsx": "7.20",
            "odds2": "19",
        },
        {
            "home": "Inactive",
            "away": "Fixture",
            "date": "2026-11-13T19:45:00+00:00",
            "odds1": "2",
            "oddsx": "3",
            "odds2": "4",
        },
    ]
    first_row = {
        "home": "England",
        "away": "Croatia",
        "date": "2026-11-12T19:45:00+00:00",
        "odds1": "1.24",
        "oddsx": "7",
        "odds2": "18",
        "pct1": "50",
        "pctx": "20",
        "pct2": "30",
        "scraped_at": "2026-10-06T22:10:13+03:00",
        "match_id_hash": "abc123",
    }
    seen = []

    def fake_get(url, **kwargs):
        seen.append((url, kwargs))
        if url.endswith("/moneyway_1x2"):
            return Response(payload=current_rows)
        if url.endswith("/moneyway_1x2_history"):
            params = _params_dict(kwargs["params"])
            assert params["home"] == ["eq.England"]
            assert params["away"] == ["eq.Croatia"]
            assert params["date"] == ["eq.2026-11-12T19:45:00+00:00"]
            assert params["odds1"] == ["neq."]
            assert params["oddsx"] == ["neq."]
            assert params["odds2"] == ["neq."]
            assert params["order"] == ["scraped_at.asc"]
            assert params["limit"] == ["1"]
            assert "offset" not in params
            return Response(payload=[first_row])
        raise AssertionError(url)

    monkeypatch.setattr(indexed.requests, "get", fake_get)

    result = engine.fetch_first_snapshots({active_key})

    assert calls["legacy"] == 0
    assert result[active_key][0]["scraped_at"] == "2026-10-06T22:10:13+03:00"
    assert result["abc123"] is result[active_key]
    assert len(seen) == 2


def test_cache_skips_current_and_history_requests_on_repeat(monkeypatch):
    engine, calls = _engine()
    indexed.install_first_snapshot_fetch(engine)
    active_key = "A|B|2026-11-12T19:45:00+00:00"
    current = {
        "home": "A",
        "away": "B",
        "date": "2026-11-12T19:45:00+00:00",
        "odds1": "2",
        "oddsx": "3",
        "odds2": "4",
    }
    history = dict(current, scraped_at="2026-10-01T10:00:00+03:00", match_id_hash="h1")
    request_count = 0

    def fake_get(url, **kwargs):
        nonlocal request_count
        request_count += 1
        if url.endswith("/moneyway_1x2"):
            return Response(payload=[current])
        return Response(payload=[history])

    monkeypatch.setattr(indexed.requests, "get", fake_get)

    first = engine.fetch_first_snapshots({active_key})
    second = engine.fetch_first_snapshots({active_key})

    assert first[active_key][0] == history
    assert second[active_key][0] == history
    assert request_count == 2
    assert calls["legacy"] == 0


def test_missing_current_odds_do_not_trigger_history_scan(monkeypatch):
    engine, calls = _engine()
    indexed.install_first_snapshot_fetch(engine)
    active_key = "A|B|2026-11-12T19:45:00+00:00"
    current = {
        "home": "A",
        "away": "B",
        "date": "2026-11-12T19:45:00+00:00",
        "odds1": "",
        "oddsx": "",
        "odds2": "",
    }
    urls = []

    def fake_get(url, **kwargs):
        urls.append(url)
        if url.endswith("/moneyway_1x2"):
            return Response(payload=[current])
        raise AssertionError("history must not be queried for invalid current odds")

    monkeypatch.setattr(indexed.requests, "get", fake_get)

    assert engine.fetch_first_snapshots({active_key}) == {}
    assert calls["legacy"] == 0
    assert len(urls) == 1


def test_history_error_fails_closed_without_global_offset_fallback(monkeypatch):
    engine, calls = _engine()
    indexed.install_first_snapshot_fetch(engine)
    active_key = "A|B|2026-11-12T19:45:00+00:00"
    current = {
        "home": "A",
        "away": "B",
        "date": "2026-11-12T19:45:00+00:00",
        "odds1": "2",
        "oddsx": "3",
        "odds2": "4",
    }

    def fake_get(url, **kwargs):
        if url.endswith("/moneyway_1x2"):
            return Response(payload=[current])
        return Response(status_code=503, payload=[], text="temporary failure")

    monkeypatch.setattr(indexed.requests, "get", fake_get)

    assert engine.fetch_first_snapshots({active_key}) == {}
    assert calls["legacy"] == 0
    assert any("HTTP 503" in line for line in calls["logs"])


def test_unscoped_call_preserves_legacy_loader():
    legacy_result = {"legacy-key": [{"odds1": "1"}]}
    engine, calls = _engine(legacy_result=legacy_result)
    indexed.install_first_snapshot_fetch(engine)

    assert engine.fetch_first_snapshots(None) == legacy_result
    assert calls["legacy"] == 1


def test_current_table_error_fails_closed_without_global_offset_fallback(monkeypatch):
    engine, calls = _engine()
    indexed.install_first_snapshot_fetch(engine)
    active_key = "A|B|2026-11-12T19:45:00+00:00"

    monkeypatch.setattr(
        indexed.requests,
        "get",
        lambda *args, **kwargs: Response(status_code=503, payload=[], text="temporary failure"),
    )

    assert engine.fetch_first_snapshots({active_key}) == {}
    assert calls["legacy"] == 0
    assert any("fail-closed without legacy scan" in line for line in calls["logs"])
