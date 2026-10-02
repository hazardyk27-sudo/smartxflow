from analysis_v2.settlement import (
    build_settlements_from_hash_scores,
    evaluate_selection,
    flat_stake_units,
    parse_score,
)


def test_double_chance_settlement():
    assert evaluate_selection("DC", "X2", 1, 1) == "WIN"
    assert evaluate_selection("DC", "X2", 2, 1) == "LOSS"
    assert evaluate_selection("DC", "1X", 0, 0) == "WIN"
    assert evaluate_selection("DC", "12", 0, 0) == "LOSS"


def test_draw_no_bet_push():
    assert evaluate_selection("DNB", "1", 1, 1) == "PUSH"
    assert evaluate_selection("DNB", "2", 0, 1) == "WIN"


def test_core_market_settlement():
    assert evaluate_selection("1X2", "X", 2, 2) == "WIN"
    assert evaluate_selection("OU25", "U", 1, 1) == "WIN"
    assert evaluate_selection("OU25", "O", 2, 1) == "WIN"
    assert evaluate_selection("BTTS", "Y", 2, 1) == "WIN"
    assert evaluate_selection("BTTS", "N", 2, 0) == "WIN"


def test_flat_stake_units():
    assert flat_stake_units(1.80, "WIN") == 0.8
    assert flat_stake_units(3.40, "LOSS") == -1.0
    assert flat_stake_units(2.10, "PUSH") == 0.0
    assert flat_stake_units(None, "WIN") is None


def test_exact_hash_only_no_team_fuzzy_fallback():
    signals = [
        {
            "signal_id": "sig_test",
            "match_id_hash": "a1b2c3d4e5f6",
            "home_team": "Manchester United",
            "away_team": "Chelsea",
            "engine_version": "2.0.0",
            "market_key": "DC",
            "selection_code": "1X",
            "trigger_odds": 1.45,
        }
    ]
    settlements, skipped = build_settlements_from_hash_scores(
        signals,
        {
            "ffffffffffff": {
                "home": 1,
                "away": 0,
                "home_team": "Man Utd",
                "away_team": "Chelsea",
            }
        },
        settled_at="2026-10-02T20:00:00Z",
    )
    assert settlements == []
    assert skipped == ["sig_test"]


def test_exact_hash_builds_settlement_and_roi():
    signals = [
        {
            "signal_id": "sig_test",
            "match_id_hash": "a1b2c3d4e5f6",
            "engine_version": "2.0.0",
            "market_key": "DC",
            "selection_code": "X2",
            "trigger_odds": 1.60,
        }
    ]
    settlements, skipped = build_settlements_from_hash_scores(
        signals,
        {"a1b2c3d4e5f6": "1-1"},
        settled_at="2026-10-02T20:00:00Z",
    )

    assert skipped == []
    assert len(settlements) == 1
    assert settlements[0]["outcome"] == "WIN"
    assert abs(settlements[0]["pnl_units"] - 0.6) < 1e-9
    assert settlements[0]["entry_odds"] == 1.60
    assert settlements[0]["metadata"]["match_method"] == "exact_match_id_hash"


def test_recommended_market_uses_its_own_frozen_odds():
    signals = [
        {
            "signal_id": "sig_test",
            "match_id_hash": "a1b2c3d4e5f6",
            "engine_version": "2.0.0",
            "market_key": "1X2",
            "selection_code": "2",
            "recommended_market": "DC",
            "recommended_selection": "X2",
            "trigger_odds": 3.40,
            "recommended_odds": 1.60,
        }
    ]
    settlements, _ = build_settlements_from_hash_scores(
        signals,
        {"a1b2c3d4e5f6": "1-1"},
        settled_at="2026-10-02T20:00:00Z",
    )
    assert settlements[0]["outcome"] == "WIN"
    assert settlements[0]["entry_odds"] == 1.60
    assert abs(settlements[0]["pnl_units"] - 0.60) < 1e-9
    assert (
        settlements[0]["metadata"]["entry_odds_source"]
        == "recommended_odds"
    )


def test_changed_market_without_recommended_odds_never_uses_source_price():
    signals = [
        {
            "signal_id": "sig_test",
            "match_id_hash": "a1b2c3d4e5f6",
            "engine_version": "2.0.0",
            "market_key": "1X2",
            "selection_code": "2",
            "recommended_market": "DC",
            "recommended_selection": "X2",
            "trigger_odds": 3.40,
        }
    ]
    settlements, _ = build_settlements_from_hash_scores(
        signals,
        {"a1b2c3d4e5f6": "1-1"},
        settled_at="2026-10-02T20:00:00Z",
    )
    assert settlements[0]["outcome"] == "WIN"
    assert settlements[0]["entry_odds"] is None
    assert settlements[0]["pnl_units"] is None
    assert (
        settlements[0]["metadata"]["entry_odds_source"]
        == "missing_recommended_market_odds"
    )


def test_parse_score_shapes():
    assert parse_score("2-1") == (2, 1)
    assert parse_score({"home_score": 3, "away_score": 0}) == (3, 0)
    assert parse_score({"score": "0:0"}) == (0, 0)
