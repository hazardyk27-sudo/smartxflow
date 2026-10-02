from analysis_v2.classification import (
    ClassificationConfig,
    classification_to_signal_metadata,
    classify_market_movement,
)


def features(
    *,
    current_odds=1.80,
    current_pct=70,
    current_amount=9000,
    market_volume=13000,
    h2_drop=6.0,
    h2_money=3000,
    h2_pct=10,
    h6_drop=7.0,
    h6_money=4000,
    h30_drop=2.0,
    h30_money=500,
    hours=6,
):
    current = {
        "odds": current_odds,
        "pct": current_pct,
        "amount": current_amount,
        "market_volume": market_volume,
    }
    return {
        "current": current,
        "opening": {
            "odds": 2.0,
            "pct": 50,
            "amount": 4000,
            "market_volume": 10000,
        },
        "anchors": {
            "6h": {"odds": 1.94, "pct": 58, "amount": 5000, "market_volume": 10500},
            "2h": {"odds": 1.915, "pct": 60, "amount": 6000, "market_volume": 11000},
            "30m": {"odds": 1.837, "pct": 65, "amount": 8500, "market_volume": 12500},
        },
        "movement": {
            "open": {
                "odds_drop_pct": 10.0,
                "amount_delta": current_amount - 4000,
                "pct_delta": current_pct - 50,
            },
            "6h": {"odds_drop_pct": h6_drop, "amount_delta": h6_money, "pct_delta": h2_pct},
            "2h": {"odds_drop_pct": h2_drop, "amount_delta": h2_money, "pct_delta": h2_pct},
            "30m": {"odds_drop_pct": h30_drop, "amount_delta": h30_money, "pct_delta": 5},
        },
        "hours_before_kickoff": hours,
    }


def test_money_up_and_odds_down_is_confirmed_move():
    result = classify_market_movement(features())
    assert result["primary_class"] == "CONFIRMED_MOVE"
    assert result["decision_window"] == "2h"
    assert result["reason_codes"] == ["MONEY_UP", "PRICE_SHORTENED"]


def test_money_up_and_odds_up_is_divergence_warning():
    result = classify_market_movement(
        features(h30_drop=-6.0, h30_money=1800, h2_drop=6.0, h2_money=3000)
    )
    assert result["primary_class"] == "PRICE_MONEY_DIVERGENCE"
    assert "RECENT_PRICE_MONEY_DIVERGENCE" in result["risk_flags"]


def test_high_money_percentage_alone_is_not_confirmation():
    result = classify_market_movement(
        features(
            current_pct=95,
            h2_drop=0.2,
            h2_money=100,
            h6_drop=0.4,
            h6_money=100,
            h30_drop=0.1,
            h30_money=100,
        )
    )
    assert result["primary_class"] == "NO_EDGE"
    assert "VERY_HIGH_MONEY_SHARE_CONTEXT_ONLY" in result["risk_flags"]


def test_extreme_money_without_price_reaction_is_anomaly_watch():
    result = classify_market_movement(
        features(
            current_amount=15000,
            market_volume=20000,
            h2_drop=0.5,
            h2_money=6000,
            h6_drop=0.5,
            h6_money=6000,
            h30_drop=0.2,
            h30_money=1000,
        )
    )
    assert result["primary_class"] == "ANOMALOUS_MONEY"
    assert "PRICE_NOT_REACTING" in result["reason_codes"]


def test_late_steam_requires_late_timing_price_and_money():
    result = classify_market_movement(
        features(hours=1.25, h30_drop=4.0, h30_money=1500, h2_drop=6.0, h2_money=3000)
    )
    assert result["primary_class"] == "LATE_STEAM"
    assert result["decision_window"] == "30m"


def test_same_30m_move_is_not_late_steam_when_kickoff_far_away():
    result = classify_market_movement(
        features(hours=8, h30_drop=4.0, h30_money=1500, h2_drop=6.0, h2_money=3000)
    )
    assert result["primary_class"] == "CONFIRMED_MOVE"


def test_early_position_requires_early_timing_plus_price_confirmation():
    result = classify_market_movement(
        features(
            hours=30,
            h6_drop=4.0,
            h6_money=2500,
            h2_drop=1.0,
            h2_money=300,
            h30_drop=0.2,
            h30_money=100,
        )
    )
    assert result["primary_class"] == "EARLY_POSITION"


def test_early_large_money_with_drifting_price_is_divergence_not_early_position():
    result = classify_market_movement(
        features(
            hours=30,
            h6_drop=-6.0,
            h6_money=3000,
            h2_drop=-5.5,
            h2_money=2500,
            h30_drop=-5.1,
            h30_money=1200,
        )
    )
    assert result["primary_class"] == "PRICE_MONEY_DIVERGENCE"


def test_low_market_volume_blocks_directional_signal():
    result = classify_market_movement(
        features(
            market_volume=3000,
            h2_drop=8.0,
            h2_money=2000,
            h6_drop=8.0,
            h6_money=2000,
            h30_drop=4.0,
            h30_money=1200,
        )
    )
    assert result["primary_class"] == "NO_EDGE"


def test_missing_current_data_returns_no_edge():
    result = classify_market_movement({"current": None})
    assert result["primary_class"] == "NO_EDGE"
    assert result["risk_flags"] == ["CURRENT_SNAPSHOT_MISSING"]


def test_missing_money_delta_does_not_infer_from_pct():
    f = features(current_pct=92)
    f["movement"]["2h"]["amount_delta"] = None
    f["movement"]["6h"]["amount_delta"] = None
    f["movement"]["30m"]["amount_delta"] = None
    f["movement"]["open"]["amount_delta"] = None
    result = classify_market_movement(f)
    assert result["primary_class"] == "NO_EDGE"


def test_config_is_explicit_and_snapshotted():
    cfg = ClassificationConfig(confirmed_price_drop_pct=4.0, min_money_added=750.0)
    result = classify_market_movement(features(), cfg)
    assert result["config_snapshot"]["confirmed_price_drop_pct"] == 4.0
    assert result["config_snapshot"]["min_money_added"] == 750.0


def test_signal_metadata_keeps_reason_and_config():
    result = classify_market_movement(features())
    metadata = classification_to_signal_metadata(result)
    assert metadata["engine_reason"]["primary_class"] == "CONFIRMED_MOVE"
    assert metadata["config_snapshot"]["confirmed_price_drop_pct"] == 5.0
    assert metadata["features"]["classification"]["classifier_version"]
