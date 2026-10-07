from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import poly_trade_checkpoints as batch


class Response:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = [] if payload is None else payload
        self.text = text

    def json(self):
        return self._payload


def _writer():
    calls = {"legacy": [], "logs": []}

    def legacy(condition_id):
        calls["legacy"].append(condition_id)
        return {"a": 101, "b": None, "c": 303}.get(condition_id)

    writer = SimpleNamespace(
        _rest_url=lambda table: f"https://example.supabase.co/rest/v1/{table}",
        _headers=lambda: {"apikey": "test"},
        get_last_traded_at=legacy,
    )
    return writer, calls


def test_batch_rpc_deduplicates_and_returns_same_checkpoint_semantics(monkeypatch):
    writer, calls = _writer()
    post_calls = []

    def fake_post(url, **kwargs):
        post_calls.append((url, kwargs))
        return Response(
            payload=[
                {"condition_id": "a", "traded_at": "1970-01-01T00:01:41+00:00"},
                {"condition_id": "c", "traded_at": "1970-01-01T00:05:03Z"},
            ]
        )

    monkeypatch.setattr(batch.requests, "post", fake_post)
    result = batch.fetch_latest_trade_checkpoints(
        writer,
        ["a", "b", "a", "c"],
        log=calls["logs"].append,
        ssl_verify=False,
    )

    assert result == {"a": 101, "b": None, "c": 303}
    assert calls["legacy"] == []
    assert len(post_calls) == 1
    assert post_calls[0][0].endswith("/rest/v1/rpc/polymarket_latest_trade_checkpoints")
    assert post_calls[0][1]["json"] == {"condition_ids": ["a", "b", "c"]}
    assert writer._checkpoint_batch_rpc_available is True


def test_rpc_failure_falls_back_once_then_disables_probe(monkeypatch):
    writer, calls = _writer()
    post_count = 0

    def fake_post(*args, **kwargs):
        nonlocal post_count
        post_count += 1
        return Response(status_code=404, payload=[], text="missing rpc")

    monkeypatch.setattr(batch.requests, "post", fake_post)

    first = batch.fetch_latest_trade_checkpoints(
        writer, ["a", "b"], log=calls["logs"].append
    )
    second = batch.fetch_latest_trade_checkpoints(
        writer, ["c"], log=calls["logs"].append
    )

    assert first == {"a": 101, "b": None}
    assert second == {"c": 303}
    assert post_count == 1
    assert calls["legacy"] == ["a", "b", "c"]
    assert writer._checkpoint_batch_rpc_available is False


def test_scraper_wires_one_checkpoint_batch_per_match():
    source = Path("polymarket_scraper.py").read_text(encoding="utf-8")
    assert "from poly_trade_checkpoints import fetch_latest_trade_checkpoints" in source
    assert "def get_last_traded_at_many(" in source
    assert "checkpoint_by_condition = writer.get_last_traded_at_many(" in source
    assert "since_ts = checkpoint_by_condition.get(condition_id)" in source
    assert "since_ts = writer.get_last_traded_at(condition_id)" not in source


def test_migration_is_read_only_grouped_checkpoint_rpc():
    sql = Path("migrations/2026_10_07_polymarket_latest_trade_checkpoints.sql").read_text(
        encoding="utf-8"
    ).lower()
    assert "returns table(condition_id text, traded_at timestamptz)" in sql
    assert "max(t.traded_at)" in sql
    assert "group by t.condition_id" in sql
    assert "security invoker" in sql
    assert "grant execute" in sql
    for forbidden in ("insert ", "update ", "delete ", "truncate ", "drop table"):
        assert forbidden not in sql
