from analysis_v2.presenter import (
    present_signal,
    present_signal_rows,
)


def base_row(state="FIRSAT"):
    return {
        "signal_id": "sig_1",
        "engine_key": "confirmed_money_v2",
        "engine_version": "2.0.0",
        "match_id_hash": "a1b2c3d4e5f6",
        "home_team": "Home FC",
        "away_team": "Away FC",
        "league": "League",
        "kickoff_utc": "2026-10-03T18:00:00Z",
        "trigger_at": "2026-10-03T12:00:00Z",
        "market_key": "1X2",
        "selection_code": "2",
        "trigger_odds": 3.40,
        "recommended_market": "DC",
        "recommended_selection": "X2",
        "recommended_odds": 1.62,
        "current_state": "CONFIRMED",
        "engine_reason": {
            "primary_class": "CONFIRMED_MOVE",
            "decision_window": "2h",
            "explainable_confidence": {
                "user_state": state,
                "state_reason_codes": (
                    ["CORE_AND_CROSS_MARKET_CONFIRMED"]
                    if state == "FIRSAT"
                    else ["CONFIRMATION_INCOMPLETE_OR_RISK_PRESENT"]
                ),
                "risk_count": 0,
            },
        },
        "features": {
            "market_movement": {
                "opening": {
                    "odds": 3.70,
                    "pct": 45,
                    "amount": 4000,
                },
                "anchors": {
                    "2h": {
                        "odds": 3.40,
                        "pct": 56,
                        "amount": 7000,
                    },
                },
                "current": {
                    "odds": 3.05,
                    "pct": 70,
                    "amount": 15400,
                    "market_volume": 22000,
                },
                "movement": {
                    "2h": {
                        "odds_drop_pct": 10.29,
                        "amount_delta": 8400,
                        "pct_delta": 14,
                    }
                },
            },
            "classification": {
                "primary_class": "CONFIRMED_MOVE",
                "window_states": {},
            },
            "market_selector": {
                "recommended_odds": 1.62,
            },
            "explainable_confidence": {
                "user_state": state,
                "risk_count": 0,
                "state_reason_codes": (
                    ["CORE_AND_CROSS_MARKET_CONFIRMED"]
                    if state == "FIRSAT"
                    else ["CONFIRMATION_INCOMPLETE_OR_RISK_PRESENT"]
                ),
                "components": {
                    "price_confirmation": {
                        "level": "STRONG",
                        "reason_codes": ["MEANINGFUL_PRICE_SHORTENING"],
                        "evidence": {
                            "odds_drop_pct": 10.29,
                        },
                    },
                    "money_flow": {
                        "level": "STRONG",
                        "reason_codes": ["LARGE_CONFIRMED_MONEY_INFLOW"],
                        "evidence": {
                            "money_added": 8400,
                            "pct_delta": 14,
                        },
                    },
                    "timing": {
                        "level": "STRONG",
                        "reason_codes": ["RECENT_DECISION_WINDOW"],
                        "evidence": {
                            "decision_window": "2h",
                        },
                    },
                    "cross_market": {
                        "level": "STRONG",
                        "reason_codes": ["MULTI_MARKET_DIRECTION_CONFIRMED"],
                        "evidence": {
                            "status": "CROSS_CONFIRMED",
                        },
                    },
                    "poly": {
                        "level": "NEUTRAL",
                        "reason_codes": ["POLY_NOT_DECISIVE"],
                        "evidence": {
                            "status": "POLY_NEUTRAL",
                        },
                    },
                    "risk": {
                        "level": "NEUTRAL",
                        "reason_codes": ["NO_MATERIAL_RISK"],
                        "evidence": {
                            "risk_count": 0,
                            "items": [],
                        },
                    },
                },
            },
        },
    }


def test_presenter_builds_beginner_friendly_opportunity_card():
    card = present_signal(base_row())
    assert card["state"] == "FIRSAT"
    assert card["state_label"] == "FIRSAT"
    assert card["recommendation"]["market"] == "DC"
    assert card["recommendation"]["selection"] == "X2"
    assert card["recommendation"]["odds"] == 1.62
    assert card["recommendation"]["direction_copy"] == (
        "Deplasman kaybetmeme tarafı güçleniyor."
    )


def test_presenter_exposes_money_and_price_sequence():
    card = present_signal(base_row())
    assert [item["label"] for item in card["flow"]] == [
        "PARA GELDİ",
        "ORAN DÜŞTÜ",
        "PİYASA TEYİT ETTİ",
    ]
    assert card["movement"]["window"] == "2h"
    assert card["movement"]["money_added"] == 8400
    assert card["movement"]["base_odds"] == 3.40
    assert card["movement"]["current_odds"] == 3.05


def test_presenter_keeps_all_six_explainable_components():
    card = present_signal(base_row())
    assert [item["key"] for item in card["components"]] == [
        "price_confirmation",
        "money_flow",
        "timing",
        "cross_market",
        "poly",
        "risk",
    ]
    assert card["components"][0]["level_label"] == "Güçlü"


def test_watch_state_is_not_relabelled_as_opportunity():
    card = present_signal(base_row("IZLE"))
    assert card["state"] == "IZLE"
    assert card["state_tone"] == "watch"


def test_divergence_flow_is_visible_not_hidden():
    row = base_row("UZAK_DUR")
    row["features"]["explainable_confidence"]["components"][
        "price_confirmation"
    ] = {
        "level": "CONFLICT",
        "reason_codes": ["PRICE_MOVES_AGAINST_MONEY"],
        "evidence": {},
    }
    row["features"]["explainable_confidence"]["components"][
        "cross_market"
    ] = {
        "level": "CONFLICT",
        "reason_codes": ["DIRECTIONAL_MARKETS_CONFLICT"],
        "evidence": {},
    }
    row["features"]["explainable_confidence"]["components"][
        "risk"
    ] = {
        "level": "CONFLICT",
        "reason_codes": ["CORE_PRICE_MONEY_DIVERGENCE"],
        "evidence": {
            "risk_count": 1,
            "items": [
                {
                    "code": "CORE_PRICE_MONEY_DIVERGENCE",
                    "severity": "HARD",
                    "source": "classification",
                }
            ],
        },
    }
    card = present_signal(row)
    assert card["state"] == "UZAK_DUR"
    assert card["flow"][1]["label"] == "ORAN TERSİNE GİTTİ"
    assert card["flow"][2]["label"] == "PİYASA ÇELİŞİYOR"
    assert card["risks"][0]["severity"] == "HARD"


def test_recommended_odds_falls_back_only_for_same_market():
    row = base_row()
    row["recommended_market"] = "1X2"
    row["recommended_selection"] = "2"
    row["recommended_odds"] = None
    row["features"]["market_selector"]["recommended_odds"] = None
    card = present_signal(row)
    assert card["recommendation"]["odds"] == 3.40


def test_cross_market_missing_odds_does_not_show_source_price():
    row = base_row()
    row["recommended_odds"] = None
    row["features"]["market_selector"]["recommended_odds"] = None
    card = present_signal(row)
    assert card["recommendation"]["market"] == "DC"
    assert card["recommendation"]["odds"] is None


def test_rows_are_counted_and_sorted():
    first = base_row("FIRSAT")
    second = base_row("IZLE")
    second["signal_id"] = "sig_2"
    second["trigger_at"] = "2026-10-03T13:00:00Z"

    result = present_signal_rows([first, second])
    assert result["count"] == 2
    assert result["counts"]["FIRSAT"] == 1
    assert result["counts"]["IZLE"] == 1
    assert result["signals"][0]["signal_id"] == "sig_2"
