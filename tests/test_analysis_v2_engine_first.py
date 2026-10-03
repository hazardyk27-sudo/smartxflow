from analysis_v2.engine_first import (
    candidate_from_v1_signal,
    canonical_engine_key,
    persistence_gate,
    reject_generic_discovery,
    source_engine_summary,
)


def _base_row(**overrides):
    row = {
        "id": 42,
        "match_id_hash": "abcdef123456",
        "match_key": "Home|Away|2026-10-04",
        "home_team": "Home",
        "away_team": "Away",
        "league": "League",
        "kickoff_utc": "2026-10-04T18:00:00Z",
        "selection_code": "2",
        "created_at": "2026-10-03T12:00:00Z",
        "odds": "3.40",
        "pct": "67.5%",
        "amt_now": "£ 8,250",
        "volume_now": "£ 14,000",
    }
    row.update(overrides)
    return row


def test_aliases_map_to_existing_v1_engines_only():
    assert canonical_engine_key("underdog") == "underdog_pressure_v1"
    assert canonical_engine_key("confirmed_money") == "confirmed_money_v1"
    assert canonical_engine_key("early_money_lock") == "early_money_lock_v1"
    assert canonical_engine_key("fake_sharp") == "price_money_divergence_v1"


def test_underdog_is_direction_candidate_not_direct_bet():
    candidate = candidate_from_v1_signal("underdog", _base_row())
    summary = source_engine_summary(candidate)
    assert summary["source_role"] == "DIRECTION_CANDIDATE"
    assert summary["direct_bet_allowed"] is False
    assert summary["source_selection"] == "2"
    assert summary["trigger_odds"] == 3.40
    assert summary["trigger_pct"] == 67.5


def test_confirmed_money_keeps_real_source_identity():
    row = _base_row(selection_code="X", odds_now="1.88", pct_now="86.4")
    row.pop("odds")
    row.pop("pct")
    candidate = candidate_from_v1_signal("confirmed_money", row)
    assert candidate.source_engine == "confirmed_money_v1"
    assert candidate.source_signal_id == "42"
    assert candidate.source_selection == "X"
    assert candidate.exact_identity_ready is True


def test_unsupported_generic_engine_is_rejected():
    try:
        canonical_engine_key("anomalous_money_v2")
    except ValueError as exc:
        assert "UNSUPPORTED_SOURCE_ENGINE" in str(exc)
    else:
        raise AssertionError("generic V2 discovery engine must not be accepted")


def test_generic_discovery_without_v1_provenance_fails_closed():
    try:
        reject_generic_discovery({"match_id_hash": "abcdef123456"})
    except ValueError as exc:
        assert str(exc) == "ENGINE_FIRST_SOURCE_REQUIRED"
    else:
        raise AssertionError("V2 candidate without V1 provenance must fail")


def test_generic_discovery_with_real_v1_provenance_passes():
    reject_generic_discovery(
        {
            "source_engine": "confirmed_money",
            "source_signal_id": "123",
        }
    )


def test_exact_match_hash_is_required_before_v2_persistence():
    row = _base_row(match_id_hash="")
    candidate = candidate_from_v1_signal("underdog", row)
    ready, reasons = persistence_gate(candidate)
    assert ready is False
    assert "EXACT_MATCH_ID_REQUIRED" in reasons


def test_early_money_lock_requires_trigger_odds_for_v2_persistence():
    row = _base_row(selection_code="1")
    row.pop("odds")
    candidate = candidate_from_v1_signal("early_money_lock", row)
    ready, reasons = persistence_gate(candidate)
    assert ready is False
    assert "EML_TRIGGER_ODDS_MISSING" in reasons


def test_fake_sharp_becomes_warning_role_not_opposite_bet():
    row = _base_row(selection_code="1", odds_now="1.74", pct_now="79.0")
    row.pop("odds")
    row.pop("pct")
    candidate = candidate_from_v1_signal("fake_sharp", row)
    summary = source_engine_summary(candidate)
    assert summary["source_engine"] == "price_money_divergence_v1"
    assert summary["source_role"] == "WARNING"
    assert summary["direct_bet_allowed"] is False


def test_invalid_selection_for_source_engine_is_rejected():
    try:
        candidate_from_v1_signal("underdog", _base_row(selection_code="X"))
    except ValueError as exc:
        assert "INVALID_SOURCE_SELECTION" in str(exc)
    else:
        raise AssertionError("Underdog V1 never scans draw selection")
