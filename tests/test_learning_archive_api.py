from __future__ import annotations

import os
import unittest
from unittest.mock import patch

from flask import Flask

from learning_archive.server_api import register_learning_archive_routes
from learning_archive.supabase_source import (
    LearningArchiveHistoryPayload,
    LearningArchiveMatchNotFound,
    read_learning_archive_match_history,
)


class FakeResponse:
    def __init__(self, status_code, payload):
        self.status_code = status_code
        self._payload = payload
    def json(self):
        return self._payload


class FakeHTTP:
    def __init__(self):
        self.calls = []
    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        if "/fixtures?" in url:
            return FakeResponse(200, [{
                "match_id_hash": "abc123def456",
                "home_team": "Home",
                "away_team": "Away",
                "league": "Test League",
                "kickoff_utc": "2026-10-03T18:00:00Z",
                "fixture_date": "2026-10-03",
            }])
        if "moneyway_1x2_history" in url:
            return FakeResponse(200, [{
                "match_id_hash": "abc123def456",
                "home": "Home",
                "away": "Away",
                "league": "Test League",
                "scraped_at": "2026-10-03T15:00:00Z",
                "odds1": 2.10,
                "api_key": "must-not-leak",
            }])
        return FakeResponse(200, [])


class FakeSnapshotOnlyHTTP:
    def __init__(self):
        self.calls = []
    def get(self, url, headers=None, timeout=None):
        self.calls.append((url, headers, timeout))
        if "/fixtures?" in url:
            return FakeResponse(200, [{
                "match_id_hash": "abc123def456",
                "home_team": "Home",
                "away_team": "Away",
                "league": "Test League",
                "kickoff_utc": "2026-10-03T18:00:00Z",
                "fixture_date": "2026-10-03",
            }])
        if "moneyway_snapshots" in url:
            return FakeResponse(200, [{
                "match_id_hash": "abc123def456",
                "market": "1X2",
                "selection": "2",
                "odds": 2.82,
                "volume": 123.45,
                "share": 67.8,
                "scraped_at_utc": "2026-10-03T15:10:00Z",
                "service_role": "must-not-leak",
            }])
        return FakeResponse(200, [])


class FakeSupabase:
    is_available = True
    def __init__(self, http=None):
        self.http = http or FakeHTTP()
    def _get_http_client(self):
        return self.http
    def _headers(self):
        return {"apikey": "internal", "Authorization": "Bearer internal"}
    def _rest_url(self, table):
        return f"https://db.test/rest/v1/{table}"


class LearningArchiveAPITests(unittest.TestCase):
    def setUp(self):
        self.app = Flask(__name__)
        register_learning_archive_routes(self.app)
        self.client = self.app.test_client()
        self.secret = "s" * 40

    def test_endpoint_unconfigured_fails_closed(self):
        with patch.dict(os.environ, {}, clear=True):
            response = self.client.get("/api/internal/learning-archive/match/abc123def456/history")
        self.assertEqual(response.status_code, 503)

    def test_endpoint_unauthorized_is_401(self):
        with patch.dict(os.environ, {"LEARNING_ARCHIVE_ACCESS_SECRET": self.secret}, clear=False):
            response = self.client.get("/api/internal/learning-archive/match/abc123def456/history")
        self.assertEqual(response.status_code, 401)

    def test_endpoint_invalid_hash_is_400_after_auth(self):
        with patch.dict(os.environ, {"LEARNING_ARCHIVE_ACCESS_SECRET": self.secret}, clear=False):
            response = self.client.get(
                "/api/internal/learning-archive/match/not-a-hash/history",
                headers={"Authorization": f"Bearer {self.secret}"},
            )
        self.assertEqual(response.status_code, 400)

    def test_endpoint_success_contract(self):
        payload = LearningArchiveHistoryPayload(
            match_id_hash="abc123def456",
            match={
                "match_id_hash": "abc123def456",
                "home": "Home",
                "away": "Away",
                "league": "Test League",
                "kickoff_utc": "2026-10-03T18:00:00Z",
                "fixture_date": "2026-10-03",
            },
            histories={"moneyway_1x2_history": [{"match_id_hash": "abc123def456", "odds1": 2.1}]},
            source_tables=("moneyway_1x2_history",),
            unavailable_optional_tables=(),
        )
        with patch.dict(os.environ, {"LEARNING_ARCHIVE_ACCESS_SECRET": self.secret}, clear=False), patch(
            "learning_archive.server_api.read_learning_archive_match_history", return_value=payload
        ):
            response = self.client.get(
                "/api/internal/learning-archive/match/abc123def456/history",
                headers={"Authorization": f"Bearer {self.secret}"},
            )
        self.assertEqual(response.status_code, 200)
        body = response.get_json()
        self.assertEqual(body["match_id_hash"], "abc123def456")
        self.assertEqual(body["source_tables"], ["moneyway_1x2_history"])
        self.assertEqual(body["unavailable_optional_tables"], [])
        self.assertEqual(response.headers.get("Cache-Control"), "no-store")

    def test_endpoint_unknown_match_is_404(self):
        with patch.dict(os.environ, {"LEARNING_ARCHIVE_ACCESS_SECRET": self.secret}, clear=False), patch(
            "learning_archive.server_api.read_learning_archive_match_history",
            side_effect=LearningArchiveMatchNotFound("abc123def456"),
        ):
            response = self.client.get(
                "/api/internal/learning-archive/match/abc123def456/history",
                headers={"Authorization": f"Bearer {self.secret}"},
            )
        self.assertEqual(response.status_code, 404)

    def test_source_reads_existing_history_and_filters_unknown_fields(self):
        http = FakeHTTP()
        result = read_learning_archive_match_history("abc123def456", client=FakeSupabase(http=http))
        self.assertEqual(result.match["home"], "Home")
        self.assertEqual(result.source_tables, ("moneyway_1x2_history",))
        self.assertEqual(result.unavailable_optional_tables, ())
        self.assertFalse(any("double_chance" in url or "draw_no_bet" in url for url, _, _ in http.calls))
        row = result.histories["moneyway_1x2_history"][0]
        self.assertEqual(row["odds1"], 2.10)
        self.assertNotIn("api_key", row)

    def test_source_falls_back_to_moneyway_snapshots_when_legacy_histories_are_empty(self):
        http = FakeSnapshotOnlyHTTP()
        result = read_learning_archive_match_history("abc123def456", client=FakeSupabase(http=http))
        self.assertEqual(result.source_tables, ("moneyway_snapshots",))
        self.assertEqual(result.unavailable_optional_tables, ())
        self.assertFalse(any("double_chance" in url or "draw_no_bet" in url for url, _, _ in http.calls))
        row = result.histories["moneyway_snapshots"][0]
        self.assertEqual(row["market"], "1X2")
        self.assertEqual(row["selection"], "2")
        self.assertEqual(row["odds"], 2.82)
        self.assertNotIn("service_role", row)
        snapshot_urls = [url for url, _, _ in http.calls if "moneyway_snapshots" in url]
        self.assertEqual(len(snapshot_urls), 1)
        self.assertIn("order=match_id_hash.asc,scraped_at_utc.asc", snapshot_urls[0])


if __name__ == "__main__":
    unittest.main()
