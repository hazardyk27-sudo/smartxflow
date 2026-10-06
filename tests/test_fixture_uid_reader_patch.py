from __future__ import annotations

from services.fixture_uid_reader_patch import (
    enrich_matches_with_fixture_uids,
    get_matches_paginated_uid_safe,
)


class FakeResponse:
    def __init__(self, rows, status_code=200):
        self._rows = rows
        self.status_code = status_code

    def json(self):
        return self._rows


class FakeHttp:
    def __init__(self, fixture_rows):
        self.fixture_rows = fixture_rows
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if "/fixtures?" in url:
            return FakeResponse(self.fixture_rows)
        raise AssertionError(f"unexpected URL {url}")


class FakeClient:
    is_available = True

    def __init__(self, fixture_rows, odds=None):
        self.http = FakeHttp(fixture_rows)
        self.odds = odds or {}

    def _rest_url(self, table):
        return f"https://example.invalid/rest/v1/{table}"

    def _headers(self):
        return {}

    def _get_http_client(self):
        return self.http

    def _dedupe_fixtures(self, rows):
        return list(rows)

    def _fetch_main_table_odds(self, market, date_gte=None):
        return dict(self.odds)

    def _normalize_history_row(self, row, market):
        return {"Odds1": row.get("odds1", "-")}

    def _get_empty_odds(self, market):
        return {"Odds1": "-"}


def _fixture(uid, kickoff, match_hash="same-legacy-hash"):
    return {
        "fixture_uid": uid,
        "match_id_hash": match_hash,
        "home_team": "Home FC",
        "away_team": "Away FC",
        "league": "League",
        "kickoff_utc": kickoff,
        "fixture_date": kickoff[:10],
    }


def test_paginated_reader_keeps_two_physical_rematches_with_same_legacy_hash():
    fixtures = [
        _fixture("uid-1", "2026-10-06T18:00:00+00:00"),
        _fixture("uid-2", "2026-10-07T18:00:00+00:00"),
    ]
    client = FakeClient(fixtures)

    result = get_matches_paginated_uid_safe(client, "moneyway_1x2")

    assert result["total"] == 2
    assert {row["fixture_uid"] for row in result["matches"]} == {"uid-1", "uid-2"}
    assert {row["match_id_hash"] for row in result["matches"]} == {"same-legacy-hash"}


def test_uid_enrichment_uses_exact_physical_identity_not_hash():
    fixtures = [
        _fixture("uid-1", "2026-10-06T18:00:00+00:00"),
        _fixture("uid-2", "2026-10-07T18:00:00+00:00"),
    ]
    client = FakeClient(fixtures)
    matches = [
        {
            "match_id_hash": "same-legacy-hash",
            "home_team": "Home FC",
            "away_team": "Away FC",
            "league": "League",
            "kickoff_utc": "2026-10-07T18:00:00+00:00",
        }
    ]

    enriched = enrich_matches_with_fixture_uids(client, matches)

    assert enriched[0]["fixture_uid"] == "uid-2"


def test_uid_enrichment_does_not_guess_ambiguous_physical_identity():
    fixtures = [
        _fixture("uid-1", "2026-10-06T18:00:00+00:00", "hash-a"),
        _fixture("uid-2", "2026-10-06T18:00:00+00:00", "hash-b"),
    ]
    client = FakeClient(fixtures)
    matches = [
        {
            "match_id_hash": "hash-a",
            "home_team": "Home FC",
            "away_team": "Away FC",
            "league": "League",
            "kickoff_utc": "2026-10-06T18:00:00+00:00",
        }
    ]

    enriched = enrich_matches_with_fixture_uids(client, matches)

    assert "fixture_uid" not in enriched[0]
