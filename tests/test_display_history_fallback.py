from datetime import datetime, timedelta, timezone

from services.display_history_fallback import (
    _fetch_latest_history_row,
    enrich_started_matches_from_history,
)


MARKET = "moneyway_1x2"
NOW = datetime(2026, 10, 5, 15, 0, tzinfo=timezone.utc)


class FakeClient:
    is_available = True

    def _normalize_history_row(self, row, market):
        assert market == MARKET
        return {
            "ScrapedAt": row.get("scraped_at", ""),
            "Volume": row.get("volume", ""),
            "Odds1": row.get("odds1", "-"),
            "OddsX": row.get("oddsx", "-"),
            "Odds2": row.get("odds2", "-"),
            "Pct1": row.get("pct1", ""),
            "PctX": row.get("pctx", ""),
            "Pct2": row.get("pct2", ""),
            "Amt1": row.get("amt1", ""),
            "AmtX": row.get("amtx", ""),
            "Amt2": row.get("amt2", ""),
        }


EMPTY = {
    "ScrapedAt": "",
    "Volume": "",
    "Odds1": "-",
    "OddsX": "-",
    "Odds2": "-",
    "Pct1": "",
    "PctX": "",
    "Pct2": "",
    "Amt1": "",
    "AmtX": "",
    "Amt2": "",
}


def fixture(kickoff):
    return {
        "home_team": "Odd II",
        "away_team": "Viking FK II",
        "league": "Norwegian 3rd Division",
        "kickoff_utc": kickoff.isoformat(),
        "match_id_hash": "8d56ee172066",
        "latest": dict(EMPTY),
    }


def history_row():
    return {
        "scraped_at": "2026-10-05T13:59:15+03:00",
        "volume": "£9,876",
        "odds1": "1.80",
        "oddsx": "3.60",
        "odds2": "4.10",
        "pct1": "61%",
        "pctx": "20%",
        "pct2": "19%",
        "amt1": "£6,024",
        "amtx": "£1,975",
        "amt2": "£1,877",
    }


def test_started_fixture_uses_latest_history_for_display():
    match = fixture(NOW - timedelta(hours=2))
    calls = []

    def fetcher(client, candidate, market):
        calls.append((candidate["match_id_hash"], market))
        return history_row()

    result = enrich_started_matches_from_history(
        FakeClient(), [match], MARKET, now_utc=NOW, fetcher=fetcher
    )

    assert calls == [("8d56ee172066", MARKET)]
    assert result[0]["latest"]["Odds1"] == "1.80"
    assert result[0]["latest"]["Pct1"] == "61%"
    assert result[0]["latest"]["DataSource"] == "history_fallback"
    assert result[0]["latest"]["IsHistorical"] is True


def test_future_fixture_never_uses_history_fallback():
    match = fixture(NOW + timedelta(hours=2))

    def fetcher(*args, **kwargs):
        raise AssertionError("future fixture must not query history")

    result = enrich_started_matches_from_history(
        FakeClient(), [match], MARKET, now_utc=NOW, fetcher=fetcher
    )

    assert result[0]["latest"] == EMPTY


def test_existing_current_values_win_over_history():
    match = fixture(NOW - timedelta(hours=2))
    match["latest"] = dict(EMPTY, Odds1="1.91", Pct1="57%")

    def fetcher(*args, **kwargs):
        raise AssertionError("current data must not query history")

    result = enrich_started_matches_from_history(
        FakeClient(), [match], MARKET, now_utc=NOW, fetcher=fetcher
    )

    assert result[0]["latest"]["Odds1"] == "1.91"
    assert "DataSource" not in result[0]["latest"]


def test_history_failure_fails_closed_to_empty_display():
    match = fixture(NOW - timedelta(hours=2))

    def fetcher(*args, **kwargs):
        raise RuntimeError("temporary history error")

    result = enrich_started_matches_from_history(
        FakeClient(), [match], MARKET, now_utc=NOW, fetcher=fetcher
    )

    assert result[0]["latest"] == EMPTY


class FakeResponse:
    status_code = 200

    def json(self):
        return [history_row()]


class FakeHttp:
    def __init__(self):
        self.calls = []

    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        return FakeResponse()


class FetchClient(FakeClient):
    def __init__(self):
        self.http = FakeHttp()

    def _rest_url(self, table):
        return f"https://example.test/rest/v1/{table}"

    def _get_http_client(self):
        return self.http

    def _headers(self):
        return {"Authorization": "Bearer test"}


def test_history_fetch_is_exact_hash_latest_limit_one():
    client = FetchClient()
    match = fixture(NOW - timedelta(hours=2))

    row = _fetch_latest_history_row(client, match, MARKET)

    assert row["scraped_at"] == "2026-10-05T13:59:15+03:00"
    assert len(client.http.calls) == 1
    url, _, timeout = client.http.calls[0]
    assert "moneyway_1x2_history" in url
    assert "match_id_hash=eq.8d56ee172066" in url
    assert "order=scraped_at.desc" in url
    assert "limit=1" in url
    assert timeout == 8
