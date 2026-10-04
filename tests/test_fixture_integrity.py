from core.hash_utils import make_match_id_hash
from services.supabase_client import SupabaseClient


def _fixture(match_hash, home="Home FC", away="Away FC", league="League A", kickoff="2026-10-15T19:00:00+00:00"):
    return {
        "match_id_hash": match_hash,
        "home_team": home,
        "away_team": away,
        "league": league,
        "kickoff_utc": kickoff,
        "fixture_date": kickoff[:10],
    }


def test_fixture_dedupe_prefers_repository_canonical_hash():
    canonical = make_match_id_hash("Home FC", "Away FC", "League A")
    result = SupabaseClient._dedupe_fixtures([_fixture("aaaaaaaaaaaa"), _fixture(canonical)])
    assert len(result) == 1
    assert result[0]["match_id_hash"] == canonical


def test_fixture_dedupe_is_order_independent_when_canonical_exists():
    canonical = make_match_id_hash("Home FC", "Away FC", "League A")
    old = _fixture("ffffffffffff")
    current = _fixture(canonical)
    assert SupabaseClient._dedupe_fixtures([old, current])[0]["match_id_hash"] == canonical
    assert SupabaseClient._dedupe_fixtures([current, old])[0]["match_id_hash"] == canonical


def test_fixture_dedupe_turkiye_ascii_prefers_canonical():
    stale = _fixture("5d5911c1dafd", "Italy", "Türkiye", "UEFA Nations League A", "2026-10-05T18:45:00+00:00")
    canonical = _fixture("f26381742135", "Italy", "Turkiye", "UEFA Nations League A", "2026-10-05T21:45:00+03:00")
    result = SupabaseClient._dedupe_fixtures([stale, canonical])
    assert len(result) == 1
    assert result[0]["match_id_hash"] == "f26381742135"


def test_fixture_dedupe_ad_ceuta_suffix_prefers_canonical():
    stale = _fixture("8d8af9e8c1ef", "CD Castellon", "AD Ceuta FC", "Spanish Segunda Division", "2026-10-04T16:30:00Z")
    canonical = _fixture("d0666bbeb294", "CD Castellon", "AD Ceuta", "Spanish Segunda Division", "2026-10-04T16:30:00+00:00")
    result = SupabaseClient._dedupe_fixtures([stale, canonical])
    assert len(result) == 1
    assert result[0]["match_id_hash"] == "d0666bbeb294"


def test_fixture_dedupe_keeps_different_kickoff_minutes():
    a = _fixture("aaaaaaaaaaaa", kickoff="2026-10-15T19:00:00+00:00")
    b = _fixture("bbbbbbbbbbbb", kickoff="2026-10-15T19:01:00+00:00")
    assert len(SupabaseClient._dedupe_fixtures([a, b])) == 2


def test_fixture_dedupe_normalizes_timezone_offsets():
    stale = _fixture("aaaaaaaaaaaa", kickoff="2026-10-15T19:00:00Z")
    canonical_hash = make_match_id_hash("Home FC", "Away FC", "League A")
    canonical = _fixture(canonical_hash, kickoff="2026-10-15T22:00:00+03:00")
    result = SupabaseClient._dedupe_fixtures([stale, canonical])
    assert len(result) == 1
    assert result[0]["match_id_hash"] == canonical_hash


def test_fixture_dedupe_keeps_same_teams_kickoff_in_different_leagues():
    a = _fixture("aaaaaaaaaaaa", league="League A")
    b = _fixture("bbbbbbbbbbbb", league="League B")
    assert len(SupabaseClient._dedupe_fixtures([a, b])) == 2


def test_fixture_dedupe_preserves_rows_without_identity_fields():
    malformed = {
        "match_id_hash": "aaaaaaaaaaaa",
        "home_team": "",
        "away_team": "Away FC",
        "league": "League A",
        "kickoff_utc": "",
    }
    valid = _fixture("bbbbbbbbbbbb")
    result = SupabaseClient._dedupe_fixtures([malformed, valid])
    assert malformed in result
    assert valid in result
