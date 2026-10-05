from core.fixture_identity_v2 import (
    BETWATCH_SOURCE,
    extract_betwatch_identity,
    make_provider_identity,
    normalize_provider_event_id,
)
from core.hash_utils import make_match_id_hash


def test_numeric_provider_id_is_treated_as_opaque_text():
    identity = make_provider_identity(" BetWatch ", 123456789)
    assert identity is not None
    assert identity.source == BETWATCH_SOURCE
    assert identity.event_id == "123456789"
    assert identity.key == (BETWATCH_SOURCE, "123456789")


def test_missing_or_bogus_provider_id_fails_closed():
    assert normalize_provider_event_id(None) is None
    assert normalize_provider_event_id("") is None
    assert normalize_provider_event_id("   ") is None
    assert normalize_provider_event_id(True) is None
    assert extract_betwatch_identity({}) is None
    assert extract_betwatch_identity({"match_id": None}) is None


def test_betwatch_extractor_uses_only_audited_match_id_field():
    assert extract_betwatch_identity({"event_id": 111, "fixture_id": 222}) is None
    identity = extract_betwatch_identity({"match_id": 333, "event_id": 111})
    assert identity is not None
    assert identity.event_id == "333"


def test_mutable_display_fields_do_not_change_provider_identity():
    before = {
        "match_id": 987654,
        "league": "Example League",
        "teams": {"v1": "Team A", "v2": "Team B"},
        "kickoff": "2026-10-05T18:00:00Z",
    }
    after = {
        "match_id": 987654,
        "league": "Example League renamed",
        "teams": {"v1": "Team A FC", "v2": "Team B"},
        "kickoff": "2026-10-05T19:30:00Z",
    }
    assert extract_betwatch_identity(before) == extract_betwatch_identity(after)


def test_rematches_can_share_legacy_hash_but_must_have_distinct_provider_identity():
    first_hash = make_match_id_hash(
        "Team A", "Team B", "Example League", "2026-10-05T18:00:00Z"
    )
    second_hash = make_match_id_hash(
        "Team A", "Team B", "Example League", "2027-02-15T18:00:00Z"
    )
    assert first_hash == second_hash

    first = extract_betwatch_identity({"match_id": 1001})
    second = extract_betwatch_identity({"match_id": 2002})
    assert first is not None and second is not None
    assert first != second
    assert first.key != second.key


def test_same_provider_event_is_same_identity_even_if_legacy_hash_changes():
    original_hash = make_match_id_hash("Türkiye", "Italy", "Friendly", None)
    renamed_hash = make_match_id_hash("Turkiye A", "Italy", "Friendly", None)
    assert original_hash != renamed_hash

    original = extract_betwatch_identity({"match_id": 4444})
    renamed = extract_betwatch_identity({"match_id": 4444})
    assert original == renamed
