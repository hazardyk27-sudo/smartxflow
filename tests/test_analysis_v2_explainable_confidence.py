from analysis_v2.explainable_confidence import (
    apply_explainable_confidence_to_trigger,
    build_explainable_confidence,
)


def classification(
    primary="CONFIRMED_MOVE",
    window="2h",
    drop=6.0,
    money=6000,
    pct_delta=16,
    money_state="UP",
    risks=None,
):
    return {
        "primary_class": primary,
        "decision_window": window,
        "risk_flags": risks or [],
        "window_states": {
            window: {
                "available": True,
                "price_state": "DRIFTED" if drop < -5 else "SHORTENED",
                "money_state": money_state,
                "odds_drop_pct": drop,
                "money_added": money,
                "pct_delta": pct_delta,
                "current_amount": 12000,
                "current_pct": 70,
            }
        },
    }


def selector(decision="RECOMMEND", reasons=None):
    return {
        "decision": decision,
        "recommended_market": "DC" if decision == "RECOMMEND" else None,
        "recommended_selection": "X2" if decision == "RECOMMEND" else None,
        "recommended_odds": 1.62 if decision == "RECOMMEND" else None,
        "reason_codes": reasons or ["REAL_PROVIDER_MARKET"],
    }


def cross(status="CROSS_CONFIRMED", risks=None):
    return {
        "status": status,
        "risk_flags": risks or [],
        "supportive_directional_markets": ["1X2", "DNB", "DC"],
        "divergent_directional_markets": [],
        "structural_context": {"context": "OPEN_GAME"},
    }


def movement(hours=6):
    return {"hours_before_kickoff": hours}


def poly(status="POLY_CONFIRMED"):
    return {
        "status": status,
        "supporting_components": ["general_direction", "big_trades"],
        "conflicting_components": [],
    }


def build(**overrides):
    args = {
        "movement_features": movement(),
        "classification": classification(),
        "selector_result": selector(),
        "cross_market_result": cross(),
        "poly_result": poly(),
    }
    args.update(overrides)
    return build_explainable_confidence(**args)


def test_full_confirmation_is_firsat_without_numeric_score():
    result = build()
    assert result["user_state"] == "FIRSAT"
    assert result["recommended_market"] == "DC"
    assert "score" not in result
    assert "confidence_score" not in result


def test_components_are_separate_and_explainable():
    result = build()
    assert set(result["components"]) == {
        "price_confirmation",
        "money_flow",
        "timing",
        "cross_market",
        "poly",
        "risk",
    }
    assert result["components"]["price_confirmation"]["level"] == "STRONG"
    assert result["components"]["money_flow"]["level"] == "STRONG"
    assert result["components"]["cross_market"]["level"] == "STRONG"
    assert result["components"]["poly"]["level"] == "STRONG"


def test_poly_neutral_does_not_block_firsat():
    result = build(poly_result=poly("POLY_NEUTRAL"))
    assert result["user_state"] == "FIRSAT"
    assert result["components"]["poly"]["level"] == "NEUTRAL"


def test_poly_unavailable_does_not_block_core_opportunity():
    result = build(poly_result=None)
    assert result["user_state"] == "FIRSAT"
    assert result["components"]["poly"]["level"] == "UNAVAILABLE"


def test_poly_conflict_downgrades_to_watch_not_stay_away():
    result = build(poly_result=poly("POLY_CONFLICT"))
    assert result["user_state"] == "IZLE"
    assert result["components"]["poly"]["level"] == "CONFLICT"
    assert result["components"]["risk"]["evidence"]["hard_count"] == 0


def test_poly_mixed_is_watch():
    result = build(poly_result=poly("POLY_MIXED"))
    assert result["user_state"] == "IZLE"


def test_core_divergence_is_uzak_dur():
    c = classification(
        primary="PRICE_MONEY_DIVERGENCE",
        drop=-7,
        money=4000,
        money_state="UP",
    )
    result = build(classification=c)
    assert result["user_state"] == "UZAK_DUR"
    assert result["components"]["price_confirmation"]["level"] == "CONFLICT"


def test_cross_market_conflict_is_uzak_dur():
    result = build(cross_market_result=cross("CONFLICT"))
    assert result["user_state"] == "UZAK_DUR"


def test_cross_no_confirmation_is_watch_not_hard_rejection():
    result = build(cross_market_result=cross("NO_CONFIRMATION"))
    assert result["user_state"] == "IZLE"
    assert result["components"]["risk"]["evidence"]["hard_count"] == 0


def test_single_market_only_is_watch():
    result = build(cross_market_result=cross("SINGLE_MARKET_ONLY"))
    assert result["user_state"] == "IZLE"


def test_anomalous_money_is_watch():
    c = classification(primary="ANOMALOUS_MONEY", drop=0.5, money=7000)
    result = build(classification=c)
    assert result["user_state"] == "IZLE"


def test_high_money_share_context_only_is_not_material_risk():
    c = classification(risks=["VERY_HIGH_MONEY_SHARE_CONTEXT_ONLY"])
    result = build(classification=c)
    risk = result["components"]["risk"]["evidence"]
    assert result["user_state"] == "FIRSAT"
    assert risk["risk_count"] == 0
    assert "VERY_HIGH_MONEY_SHARE_CONTEXT_ONLY" in risk["context_flags"]


def test_early_position_timing_is_medium():
    c = classification(
        primary="EARLY_POSITION",
        window="6h",
        drop=4,
        money=2500,
    )
    result = build(
        classification=c,
        movement_features=movement(30),
    )
    assert result["components"]["timing"]["level"] == "MEDIUM"


def test_money_strength_keeps_actual_evidence():
    c = classification(money=1800, pct_delta=7)
    result = build(classification=c)
    money = result["components"]["money_flow"]
    assert money["level"] == "MEDIUM"
    assert money["evidence"]["money_added"] == 1800
    assert money["evidence"]["pct_delta"] == 7


def test_selector_watch_only_produces_watch_when_no_hard_contradiction():
    result = build(
        selector_result=selector("WATCH_ONLY", ["SOURCE_NO_EDGE"])
    )
    assert result["user_state"] == "IZLE"


def test_selector_source_divergence_is_hard_risk():
    result = build(
        selector_result=selector(
            "WATCH_ONLY",
            ["SOURCE_DIVERGENCE"],
        )
    )
    assert result["user_state"] == "UZAK_DUR"


def test_trigger_merge_preserves_previous_metadata():
    confidence = build()
    original = {
        "engine_reason": {"primary_class": "CONFIRMED_MOVE"},
        "config_snapshot": {"classification": {"a": 1}},
        "features": {
            "poly_confirmation": {"status": "POLY_CONFIRMED"}
        },
    }
    merged = apply_explainable_confidence_to_trigger(
        original,
        confidence,
    )
    assert (
        merged["engine_reason"]["primary_class"]
        == "CONFIRMED_MOVE"
    )
    assert (
        merged["engine_reason"]["explainable_confidence"]["user_state"]
        == "FIRSAT"
    )
    assert "classification" in merged["config_snapshot"]
    assert "explainable_confidence" in merged["config_snapshot"]
    assert "poly_confirmation" in merged["features"]
    assert "explainable_confidence" in merged["features"]
