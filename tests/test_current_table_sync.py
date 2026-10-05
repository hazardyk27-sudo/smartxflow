from __future__ import annotations

from unittest.mock import Mock

from core import current_table_sync as sync


class FakeWriter:
    def __init__(self, upsert_ok: bool = True):
        self.upsert_ok = upsert_ok
        self.last_write_errors = []
        self.events = []

    def _rest_url(self, table: str) -> str:
        return f"https://example.supabase.co/rest/v1/{table}"

    def _headers(self):
        return {"apikey": "key"}

    def upsert_rows(self, table, rows, on_conflict="home,away,date"):
        self.events.append(("upsert", table, list(rows), on_conflict))
        return self.upsert_ok


def _response(status_code: int, rows=None):
    response = Mock()
    response.status_code = status_code
    response.json.return_value = [] if rows is None else rows
    return response


def test_sync_upserts_then_prunes_only_missing_current_ids(monkeypatch):
    writer = FakeWriter()
    network_events = []
    current_rows = [
        {
            "id": 1,
            "league": "League",
            "home": "Home",
            "away": "Away",
            "date": "2026-10-05T18:00:00+00:00",
        },
        {
            "id": 2,
            "league": "League",
            "home": "Old Home",
            "away": "Old Away",
            "date": "2026-10-05T19:00:00+00:00",
        },
    ]

    def fake_get(*args, **kwargs):
        network_events.append(("get", args[0]))
        return _response(200, current_rows)

    def fake_delete(*args, **kwargs):
        network_events.append(("delete", args[0]))
        return _response(204)

    monkeypatch.setattr(sync.requests, "get", fake_get)
    monkeypatch.setattr(sync.requests, "delete", fake_delete)

    incoming = [
        {
            "league": "League",
            "home": "Home",
            "away": "Away",
            "date": "2026-10-05T18:00:00Z",
            "odds1": "2.1",
        }
    ]

    assert sync.sync_current_table(writer, "moneyway_1x2", incoming) is True
    assert writer.events[0][0] == "upsert"
    assert writer.events[0][3] == "league,home,away,date"
    delete_urls = [url for event, url in network_events if event == "delete"]
    assert delete_urls == [
        "https://example.supabase.co/rest/v1/moneyway_1x2?id=in.(2)"
    ]
    assert writer.last_write_errors == []


def test_empty_feed_clears_current_table_without_touching_history(monkeypatch):
    writer = FakeWriter()
    current_rows = [
        {"id": 11, "league": "L", "home": "A", "away": "B", "date": "2026-10-05T10:00:00Z"},
        {"id": 12, "league": "L", "home": "C", "away": "D", "date": "2026-10-05T11:00:00Z"},
    ]
    monkeypatch.setattr(sync.requests, "get", Mock(return_value=_response(200, current_rows)))
    delete = Mock(return_value=_response(204))
    monkeypatch.setattr(sync.requests, "delete", delete)

    assert sync.sync_current_table(writer, "dropping_btts", []) is True
    assert writer.events == [
        ("upsert", "dropping_btts", [], "league,home,away,date")
    ]
    assert delete.call_count == 1
    assert "id=in.(11,12)" in delete.call_args.args[0]


def test_read_failure_allows_safe_upsert_but_never_prunes(monkeypatch):
    writer = FakeWriter()
    monkeypatch.setattr(sync.requests, "get", Mock(return_value=_response(500)))
    delete = Mock(side_effect=AssertionError("prune must be fail-closed"))
    monkeypatch.setattr(sync.requests, "delete", delete)

    incoming = [
        {"league": "L", "home": "A", "away": "B", "date": "2026-10-05T10:00:00Z"}
    ]
    assert sync.sync_current_table(writer, "moneyway_btts", incoming) is False
    assert writer.events[0][0] == "upsert"
    delete.assert_not_called()
    assert any("current index HTTP 500" in error for error in writer.last_write_errors)


def test_upsert_failure_never_prunes_existing_rows(monkeypatch):
    writer = FakeWriter(upsert_ok=False)
    current_rows = [
        {"id": 21, "league": "L", "home": "Old", "away": "Row", "date": "2026-10-05T10:00:00Z"}
    ]
    monkeypatch.setattr(sync.requests, "get", Mock(return_value=_response(200, current_rows)))
    delete = Mock(side_effect=AssertionError("failed upsert must not prune"))
    monkeypatch.setattr(sync.requests, "delete", delete)

    incoming = [
        {"league": "L", "home": "New", "away": "Row", "date": "2026-10-05T11:00:00Z"}
    ]
    assert sync.sync_current_table(writer, "dropping_1x2", incoming) is False
    delete.assert_not_called()
    assert any("UPSERT başarısız" in error for error in writer.last_write_errors)
