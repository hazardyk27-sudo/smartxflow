from analysis_v2.cross_market import (
    apply_cross_market_to_trigger,
    build_cross_market_views,
    evaluate_cross_market,
    reconcile_market_selection,
)


def view(odds, cls="CONFIRMED_MOVE", risks=None):
    current = None
    if odds is not None:
        current = {
            "odds": odds,
            "pct": 60,
            "amount": 6000,
            "market_volume": 12000,
        }
    return {
        "features": {"current": current},
        "classification": {
            "primary_class": cls,
            "risk_flags": risks or [],
            "reason_codes": [],
        },
    }


def base_views():
    return {
        "1X2": view(3.40),
        "DNB": view(2.50),
        "DC": view(1.60),
        "OU25": {"O": view(1.90), "U": view(1.95, "NO_EDGE")},
        "BTTS": {"Y": view(1.75), "N": view(2.05, "NO_EDGE")},
    }


def test_three_same_direction_markets_cross_confirm():
    result = evaluate_cross_market("2", base_views())
    assert result["status"] == "CROSS_CONFIRMED"
    assert result["supportive_directional_markets"] == ["1X2", "DNB", "DC"]
    assert result["divergent_directional_markets"] == []


def test_same_direction_divergence_overrides_other_support():
    views = base_views()
    views["DC"] = view(1.60, "PRICE_MONEY_DIVERGENCE")
    result = evaluate_cross_market("2", views)
    assert result["status"] == "CONFLICT"
    assert result["divergent_directional_markets"] == ["DC"]
    assert "DIRECTIONAL_MARKET_DIVERGENCE" in result["risk_flags"]


def test_recent_divergence_risk_is_directional_conflict():
    views = base_views()
    views["DNB"] = view(
        2.50,
        "CONFIRMED_MOVE",
        ["RECENT_PRICE_MONEY_DIVERGENCE"],
    )
    result = evaluate_cross_market("2", views)
    assert result["status"] == "CONFLICT"
    assert "DNB" in result["divergent_directional_markets"]


def test_missing_optional_markets_do_not_create_false_conflict():
    views = base_views()
    views["DNB"] = view(None, "NO_EDGE")
    views["DC"] = view(None, "NO_EDGE")
    result = evaluate_cross_market("2", views)
    assert result["status"] == "SINGLE_MARKET_ONLY"
    assert set(result["unavailable_directional_markets"]) == {"DNB", "DC"}


def test_source_market_must_remain_supportive():
    views = base_views()
    views["1X2"] = view(3.40, "NO_EDGE")
    result = evaluate_cross_market("2", views)
    assert result["status"] == "NO_CONFIRMATION"
    assert "SOURCE_MARKET_NOT_SUPPORTIVE" in result["risk_flags"]


def test_over_plus_btts_yes_is_open_game_context():
    result = evaluate_cross_market("2", base_views())
    structural = result["structural_context"]
    assert structural["context"] == "OPEN_GAME"
    assert structural["ou25"]["dominant_selection"] == "O"
    assert structural["btts"]["dominant_selection"] == "Y"


def test_under_plus_btts_no_is_low_event_context():
    views = base_views()
    views["OU25"] = {"O": view(1.90, "NO_EDGE"), "U": view(1.95)}
    views["BTTS"] = {"Y": view(1.75, "NO_EDGE"), "N": view(2.05)}
    result = evaluate_cross_market("1", views)
    assert result["structural_context"]["context"] == "LOW_EVENT"


def test_structural_mixed_context_does_not_invert_team_direction():
    views = base_views()
    views["BTTS"] = {"Y": view(1.75, "NO_EDGE"), "N": view(2.05)}
    result = evaluate_cross_market("2", views)
    assert result["status"] == "CROSS_CONFIRMED"
    assert result["structural_context"]["context"] == "MIXED"


def test_structural_divergence_is_risk_not_directional_conflict():
    views = base_views()
    views["OU25"]["O"] = view(1.90, "PRICE_MONEY_DIVERGENCE")
    views["OU25"]["U"] = view(1.95, "NO_EDGE")
    result = evaluate_cross_market("2", views)
    assert result["status"] == "CROSS_CONFIRMED"
    assert "STRUCTURAL_MARKET_DIVERGENCE" in result["risk_flags"]


def test_draw_direction_never_uses_dc_12_as_confirmation():
    views = {
        "1X2": view(3.10),
        "DC": view(1.20),
        "DNB": view(1.80),
        "OU25": {"O": view(1.90, "NO_EDGE"), "U": view(1.95, "NO_EDGE")},
        "BTTS": {"Y": view(1.75, "NO_EDGE"), "N": view(2.05, "NO_EDGE")},
    }
    result = evaluate_cross_market("X", views)
    assert result["status"] == "SINGLE_MARKET_ONLY"
    assert list(result["directional_markets"]) == ["1X2"]


class FakeHistory:
    def __init__(self):
        self.calls = []

    def build_features(self, **kwargs):
        self.calls.append((kwargs["market_key"], kwargs["selection_code"]))
        return {
            "current": {
                "odds": 2.0,
                "pct": 60,
                "amount": 6000,
                "market_volume": 12000,
            },
            "_classification": {
                "primary_class": "CONFIRMED_MOVE",
                "risk_flags": [],
                "reason_codes": [],
            },
        }


def test_builder_reads_real_directional_and_both_structural_selections(monkeypatch):
    history = FakeHistory()

    def fake_classify(features, config=None):
        return features["_classification"]

    monkeypatch.setattr(
        "analysis_v2.market_selector.classify_market_movement",
        fake_classify,
    )
    monkeypatch.setattr(
        "analysis_v2.cross_market.classify_market_movement",
        fake_classify,
    )

    views = build_cross_market_views(
        history,
        match_id_hash="a1b2c3d4e5f6",
        direction="2",
        as_of="2026-10-02T12:00:00Z",
    )
    assert history.calls == [
        ("1X2", "2"),
        ("DNB", "2"),
        ("DC", "X2"),
        ("OU25", "O"),
        ("OU25", "U"),
        ("BTTS", "Y"),
        ("BTTS", "N"),
    ]
    assert set(views["OU25"]) == {"O", "U"}
    assert set(views["BTTS"]) == {"Y", "N"}


def test_reconcile_blocks_part5_recommendation_on_directional_conflict():
    selector = {
        "decision": "RECOMMEND",
        "recommended_market": "DC",
        "recommended_selection": "X2",
        "recommended_odds": 1.60,
        "protection_level": "DRAW_COVER",
        "reason_codes": ["REAL_PROVIDER_MARKET"],
    }
    views = base_views()
    views["DNB"] = view(2.50, "PRICE_MONEY_DIVERGENCE")
    cross = evaluate_cross_market("2", views)
    merged = reconcile_market_selection(selector, cross)
    assert merged["decision"] == "WATCH_ONLY"
    assert merged["recommended_market"] is None
    assert "CROSS_MARKET_DIRECTIONAL_CONFLICT" in merged["reason_codes"]


def test_reconcile_keeps_part5_recommendation_when_cross_confirmed():
    selector = {
        "decision": "RECOMMEND",
        "recommended_market": "DC",
        "recommended_selection": "X2",
        "recommended_odds": 1.60,
        "protection_level": "DRAW_COVER",
        "reason_codes": ["REAL_PROVIDER_MARKET"],
    }
    cross = evaluate_cross_market("2", base_views())
    merged = reconcile_market_selection(selector, cross)
    assert merged["decision"] == "RECOMMEND"
    assert merged["recommended_market"] == "DC"
    assert merged["cross_market"]["status"] == "CROSS_CONFIRMED"


def test_trigger_merge_preserves_existing_metadata():
    cross = evaluate_cross_market("2", base_views())
    original = {
        "engine_reason": {"primary_class": "CONFIRMED_MOVE"},
        "config_snapshot": {"classification": {"a": 1}},
        "features": {"market_selector": {"decision": "RECOMMEND"}},
    }
    merged = apply_cross_market_to_trigger(original, cross)
    assert merged["engine_reason"]["primary_class"] == "CONFIRMED_MOVE"
    assert merged["engine_reason"]["cross_market"]["status"] == "CROSS_CONFIRMED"
    assert "classification" in merged["config_snapshot"]
    assert "cross_market" in merged["config_snapshot"]
    assert "market_selector" in merged["features"]
    assert "cross_market" in merged["features"]
