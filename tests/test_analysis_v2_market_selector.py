import pytest

from analysis_v2.market_selector import (
    MarketSelectorConfig,
    apply_market_selection_to_trigger,
    build_direction_market_views,
    direction_market_selection,
    select_direction_market,
)


def view(odds, cls="CONFIRMED_MOVE", risks=None):
    return {
        "features": {
            "current": {
                "odds": odds,
                "pct": 65,
                "amount": 7000,
                "market_volume": 12000,
            },
        },
        "classification": {
            "primary_class": cls,
            "risk_flags": risks or [],
            "reason_codes": [],
            "classifier_version": "test",
        },
    }


def test_high_odds_away_direction_prefers_real_x2():
    result = select_direction_market(
        "2",
        {"1X2": view(3.40), "DNB": view(2.55), "DC": view(1.62)},
    )
    assert result["recommended_market"] == "DC"
    assert result["recommended_selection"] == "X2"
    assert result["protection_level"] == "DRAW_COVER"


def test_high_odds_falls_back_to_dnb_when_dc_missing():
    result = select_direction_market(
        "AWAY",
        {"1X2": view(3.40), "DNB": view(2.55), "DC": view(None, "NO_EDGE")},
    )
    assert result["recommended_market"] == "DNB"
    assert result["recommended_selection"] == "2"


def test_divergent_dc_is_rejected_not_selected():
    result = select_direction_market(
        "2",
        {
            "1X2": view(3.40),
            "DNB": view(2.55),
            "DC": view(1.62, "PRICE_MONEY_DIVERGENCE"),
        },
    )
    assert result["recommended_market"] == "DNB"
    assert "MARKET_DIVERGENCE" in result["candidates"]["DC"]["reason_codes"]


def test_unconfirmed_protective_markets_fall_back_to_confirmed_ml():
    result = select_direction_market(
        "2",
        {
            "1X2": view(3.40),
            "DNB": view(2.55, "NO_EDGE"),
            "DC": view(1.62, "NO_EDGE"),
        },
    )
    assert result["recommended_market"] == "1X2"
    assert result["recommended_selection"] == "2"


def test_medium_ml_prefers_dnb_then_dc():
    result = select_direction_market(
        "1",
        {"1X2": view(2.30), "DNB": view(1.80), "DC": view(1.35)},
    )
    assert result["preference_order"] == ["DNB", "DC", "1X2"]
    assert result["recommended_market"] == "DNB"
    assert result["recommended_selection"] == "1"


def test_short_ml_prefers_match_odds():
    result = select_direction_market(
        "HOME",
        {"1X2": view(1.75), "DNB": view(1.40), "DC": view(1.12)},
    )
    assert result["recommended_market"] == "1X2"
    assert result["recommended_selection"] == "1"


def test_source_divergence_blocks_recommendation():
    result = select_direction_market(
        "2",
        {
            "1X2": view(3.40, "PRICE_MONEY_DIVERGENCE"),
            "DNB": view(2.50),
            "DC": view(1.60),
        },
    )
    assert result["decision"] == "WATCH_ONLY"
    assert result["recommended_market"] is None
    assert result["reason_codes"] == ["SOURCE_DIVERGENCE"]


def test_source_recent_divergence_risk_blocks_recommendation():
    result = select_direction_market(
        "2",
        {
            "1X2": view(
                3.40,
                "CONFIRMED_MOVE",
                ["RECENT_PRICE_MONEY_DIVERGENCE"],
            ),
            "DNB": view(2.50),
            "DC": view(1.60),
        },
    )
    assert result["decision"] == "WATCH_ONLY"
    assert result["reason_codes"] == ["SOURCE_RECENT_DIVERGENCE"]


def test_source_anomaly_is_watch_only_not_a_bet():
    result = select_direction_market(
        "2",
        {
            "1X2": view(3.40, "ANOMALOUS_MONEY"),
            "DNB": view(2.50),
            "DC": view(1.60),
        },
    )
    assert result["decision"] == "WATCH_ONLY"
    assert result["reason_codes"] == ["SOURCE_ANOMALY_WATCH_ONLY"]


def test_draw_direction_does_not_misuse_12_double_chance():
    assert direction_market_selection("X") == {"1X2": "X"}
    result = select_direction_market("DRAW", {"1X2": view(3.10)})
    assert result["recommended_market"] == "1X2"
    assert result["recommended_selection"] == "X"
    assert "DC" not in result["candidates"]


def test_no_confirmed_real_market_returns_watch_only():
    cfg = MarketSelectorConfig(require_source_confirmation=False)
    result = select_direction_market(
        "2",
        {
            "1X2": view(None, "NO_EDGE"),
            "DNB": view(None, "NO_EDGE"),
            "DC": view(None, "NO_EDGE"),
        },
        config=cfg,
    )
    assert result["decision"] == "WATCH_ONLY"
    assert result["reason_codes"] == ["NO_CONFIRMED_REAL_MARKET"]


class FakeHistoryClient:
    def __init__(self, missing_dc=False):
        self.calls = []
        self.missing_dc = missing_dc

    def build_features(self, **kwargs):
        self.calls.append(kwargs)
        market = kwargs["market_key"]
        odds = {"1X2": 3.40, "DNB": 2.50, "DC": 1.60}[market]
        cls = "CONFIRMED_MOVE"
        if market == "DC" and self.missing_dc:
            odds = None
            cls = "NO_EDGE"
        return {
            "current": {
                "odds": odds,
                "pct": 65,
                "amount": 7000,
                "market_volume": 12000,
            } if odds else None,
            "_classification": {
                "primary_class": cls,
                "risk_flags": [],
                "reason_codes": [],
            },
        }


def test_history_builder_requests_only_same_direction_real_legs(monkeypatch):
    client = FakeHistoryClient()

    def fake_classify(features, config=None):
        return features["_classification"]

    monkeypatch.setattr(
        "analysis_v2.market_selector.classify_market_movement",
        fake_classify,
    )
    views = build_direction_market_views(
        client,
        match_id_hash="a1b2c3d4e5f6",
        direction="2",
        as_of="2026-10-02T12:00:00Z",
    )
    requested = [
        (call["market_key"], call["selection_code"])
        for call in client.calls
    ]
    assert requested == [("1X2", "2"), ("DNB", "2"), ("DC", "X2")]
    assert "12" not in [selection for _, selection in requested]
    assert set(views) == {"1X2", "DNB", "DC"}


def test_missing_real_dc_stays_unavailable(monkeypatch):
    client = FakeHistoryClient(missing_dc=True)

    def fake_classify(features, config=None):
        return features["_classification"]

    monkeypatch.setattr(
        "analysis_v2.market_selector.classify_market_movement",
        fake_classify,
    )
    views = build_direction_market_views(
        client,
        match_id_hash="a1b2c3d4e5f6",
        direction="2",
        as_of="2026-10-02T12:00:00Z",
    )
    result = select_direction_market("2", views)
    assert result["candidates"]["DC"]["available"] is False
    assert result["recommended_market"] == "DNB"


def test_trigger_merge_preserves_part4_metadata():
    selector = select_direction_market(
        "2",
        {"1X2": view(3.40), "DNB": view(2.50), "DC": view(1.60)},
    )
    original = {
        "engine_reason": {"primary_class": "CONFIRMED_MOVE"},
        "config_snapshot": {"classification": {"x": 1}},
        "features": {"market_movement": {"x": 2}},
    }
    merged = apply_market_selection_to_trigger(original, selector)
    assert merged["recommended_market"] == "DC"
    assert merged["recommended_selection"] == "X2"
    assert merged["engine_reason"]["primary_class"] == "CONFIRMED_MOVE"
    assert "market_selector" in merged["engine_reason"]
    assert "classification" in merged["config_snapshot"]
    assert "market_selector" in merged["config_snapshot"]
    assert "market_movement" in merged["features"]
    assert "market_selector" in merged["features"]


def test_invalid_direction_rejected():
    with pytest.raises(ValueError):
        select_direction_market("12", {"1X2": view(2.0)})
