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


def test_fixture_dedupe_prefers_current_betwatch_hash():
    canonical = SupabaseClient._fixture_canonical_hash(_fixture("placeholder"))
    old = _fixture("aaaaaaaaaaaa")
    current = _fixture(canonical)

    result = SupabaseClient._dedupe_fixtures([old, current])

    assert len(result) == 1
    assert result[0]["match_id_hash"] == canonical


def test_fixture_dedupe_is_order_independent_when_canonical_exists():
    canonical = SupabaseClient._fixture_canonical_hash(_fixture("placeholder"))
    old = _fixture("ffffffffffff")
    current = _fixture(canonical)

    first = SupabaseClient._dedupe_fixtures([old, current])
    second = SupabaseClient._dedupe_fixtures([current, old])

    assert first[0]["match_id_hash"] == canonical
    assert second[0]["match_id_hash"] == canonical


def test_fixture_dedupe_keeps_different_kickoff_minutes():
    a = _fixture("aaaaaaaaaaaa", kickoff="2026-10-15T19:00:00+00:00")
    b = _fixture("bbbbbbbbbbbb", kickoff="2026-10-15T19:01:00+00:00")

    result = SupabaseClient._dedupe_fixtures([a, b])

    assert len(result) == 2


def test_fixture_dedupe_normalizes_z_and_utc_offset():
    base = _fixture("aaaaaaaaaaaa", kickoff="2026-10-15T19:00:00Z")
    canonical_row = _fixture("placeholder", kickoff="2026-10-15T19:00:00+00:00")
    canonical = SupabaseClient._fixture_canonical_hash(canonical_row)
    current = _fixture(canonical, kickoff="2026-10-15T19:00:00+00:00")

    result = SupabaseClient._dedupe_fixtures([base, current])

    assert len(result) == 1
    assert result[0]["match_id_hash"] == canonical


def test_fixture_dedupe_preserves_rows_without_identity_fields():
    malformed = {"match_id_hash": "aaaaaaaaaaaa", "home_team": "", "away_team": "Away FC", "kickoff_utc": ""}
    valid = _fixture("bbbbbbbbbbbb")

    result = SupabaseClient._dedupe_fixtures([malformed, valid])

    assert malformed in result
    assert valid in result
