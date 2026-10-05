from __future__ import annotations

import unittest
from urllib.parse import urlparse

from learning_archive.supabase_source import (
    FALLBACK_HISTORY_TABLE,
    REQUIRED_HISTORY_TABLES,
    read_learning_archive_match_histories,
)


class _Response:
    def __init__(self, payload, status_code=200):
        self._payload = payload
        self.status_code = status_code

    def json(self):
        return self._payload


class _Http:
    def __init__(self):
        self.calls: list[str] = []

    @staticmethod
    def _requested(url: str) -> set[str]:
        marker = "match_id_hash=in.("
        if marker not in url:
            return set()
        tail = url.split(marker, 1)[1]
        values = tail.split(")", 1)[0]
        return {value for value in values.split(",") if value}

    def get(self, url, *, headers, timeout):
        self.calls.append(url)
        table = urlparse(url).path.rsplit("/", 1)[-1]
        requested = self._requested(url)
        if table == "fixtures":
            fixtures = [
                {
                    "match_id_hash": "aaaaaaaaaaaa",
                    "home_team": "A",
                    "away_team": "B",
                    "league": "L",
                    "kickoff_utc": "2026-10-05T18:00:00Z",
                    "fixture_date": "2026-10-05",
                },
                {
                    "match_id_hash": "bbbbbbbbbbbb",
                    "home_team": "C",
                    "away_team": "D",
                    "league": "L",
                    "kickoff_utc": "2026-10-05T19:00:00Z",
                    "fixture_date": "2026-10-05",
                },
            ]
            return _Response([row for row in fixtures if row["match_id_hash"] in requested])
        if table == REQUIRED_HISTORY_TABLES[0]:
            rows = [
                {
                    "match_id_hash": "aaaaaaaaaaaa",
                    "scraped_at": "2026-10-05T17:00:00Z",
                    "odds1": 2.0,
                }
            ]
            return _Response([row for row in rows if row["match_id_hash"] in requested])
        if table == FALLBACK_HISTORY_TABLE:
            rows = [
                {
                    "match_id_hash": "bbbbbbbbbbbb",
                    "scraped_at_utc": "2026-10-05T18:00:00Z",
                    "odds": 1.9,
                    "share": 55,
                }
            ]
            return _Response([row for row in rows if row["match_id_hash"] in requested])
        return _Response([])


class _Client:
    is_available = True

    def __init__(self):
        self.http = _Http()

    def _get_http_client(self):
        return self.http

    def _headers(self):
        return {"apikey": "test"}

    def _rest_url(self, table):
        return f"https://example.test/rest/v1/{table}"


class SupabaseHistoryBatchTests(unittest.TestCase):
    def test_many_hashes_are_grouped_into_table_batched_requests(self):
        client = _Client()
        result = read_learning_archive_match_histories(
            ["aaaaaaaaaaaa", "bbbbbbbbbbbb"],
            client=client,
        )

        self.assertEqual(set(result), {"aaaaaaaaaaaa", "bbbbbbbbbbbb"})
        self.assertEqual(
            len(client.http.calls),
            1 + len(REQUIRED_HISTORY_TABLES) + 1,
        )
        self.assertEqual(result["aaaaaaaaaaaa"].source_tables, (REQUIRED_HISTORY_TABLES[0],))
        self.assertEqual(result["bbbbbbbbbbbb"].source_tables, (FALLBACK_HISTORY_TABLE,))
        self.assertTrue(all("in.(aaaaaaaaaaaa,bbbbbbbbbbbb)" in url for url in client.http.calls[:7]))

    def test_missing_fixture_is_omitted_for_archive_fallback(self):
        client = _Client()
        result = read_learning_archive_match_histories(
            ["aaaaaaaaaaaa", "cccccccccccc"],
            client=client,
        )
        self.assertIn("aaaaaaaaaaaa", result)
        self.assertNotIn("cccccccccccc", result)


if __name__ == "__main__":
    unittest.main()
