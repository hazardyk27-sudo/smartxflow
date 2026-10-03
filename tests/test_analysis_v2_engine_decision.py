from analysis_v2.engine_decision import decide_engine_candidate
from analysis_v2.engine_first import candidate_from_v1_signal


def _candidate(engine="confirmed_money", selection="1", odds="1.80"):
    return candidate_from_v1_signal(
        engine,
        {
            "id": 1,
            "match_id_hash": "abcdef123456",
            "home_team": "Home",
            "away_team": "Away",
            "league": "League",
            "selection_code": selection,
            "created_at": "2026-10-03T12:00:00Z",
            "odds_now": odds,
            "pct_now": "87.0",
            "volume_now": "12000",
        },
    )


def _holdout_edge(market="1X2"):
    return {
        "evidence_status": "HOLDOUT_SUPPORTED",
        "market_key": market,
        "n": 80,
        "roi_pct": 8.2,
    }


def test_confirmed_money_needs_out_of_sample_edge_for_firsat():
    candidate = _candidate()
    research = decide_engine_candidate(
        candidate,
        movement={"primary_class": "CONFIRMED_MOVE"},
        edge={"evidence_status": "RESEARCH_CANDIDATE", "market_key": "1X2"},
    )
    assert research.user_state == "IZLE"
    assert "EDGE_NOT_OUT_OF_SAMPLE_VALIDATED" in research.risks

    validated = decide_engine_candidate(
        candidate,
        movement={"primary_class": "CONFIRMED_MOVE"},
        edge=_holdout_edge(),
    )
    assert validated.user_state == "FIRSAT"
    assert validated.recommended_market == "1X2"
    assert validated.recommended_selection == "1"


def test_divergence_is_hard_stop_and_does_not_flip_side():
    candidate = _candidate()
    decision = decide_engine_candidate(
        candidate,
        movement={"primary_class": "PRICE_MONEY_DIVERGENCE"},
        edge=_holdout_edge(),
    )
    assert decision.user_state == "UZAK_DUR"
    assert decision.recommended_market is None
    assert decision.recommended_selection is None


def test_fake_sharp_is_warning_only_never_opposite_bet():
    candidate = _candidate(engine="fake_sharp", selection="2")
    decision = decide_engine_candidate(
        candidate,
        movement={"primary_class": "PRICE_MONEY_DIVERGENCE"},
        market_selection={
            "recommended_market": "1X2",
            "recommended_selection": "1",
            "recommended_odds": 1.70,
        },
        edge=_holdout_edge(),
    )
    assert decision.user_state == "UZAK_DUR"
    assert decision.recommended_selection is None


def test_underdog_is_not_automatic_ml():
    candidate = candidate_from_v1_signal(
        "underdog",
        {
            "id": 2,
            "match_id_hash": "abcdef123456",
            "home_team": "Home",
            "away_team": "Away",
            "league": "League",
            "selection_code": "2",
            "created_at": "2026-10-03T12:00:00Z",
            "odds": "3.40",
            "pct": "68",
            "volume": "14000",
        },
    )
    decision = decide_engine_candidate(
        candidate,
        movement={"primary_class": "CONFIRMED_MOVE"},
        edge={"evidence_status": "HOLDOUT_SUPPORTED", "market_key": "1X2"},
    )
    assert decision.user_state == "IZLE"
    assert decision.recommended_market is None
    assert "UNDERDOG_MARKET_NOT_SELECTED" in decision.risks


def test_underdog_can_use_real_dnb_when_edge_is_validated_for_dnb():
    candidate = candidate_from_v1_signal(
        "underdog",
        {
            "id": 3,
            "match_id_hash": "abcdef123456",
            "home_team": "Home",
            "away_team": "Away",
            "league": "League",
            "selection_code": "2",
            "created_at": "2026-10-03T12:00:00Z",
            "odds": "3.40",
            "pct": "68",
            "volume": "14000",
        },
    )
    decision = decide_engine_candidate(
        candidate,
        movement={"primary_class": "CONFIRMED_MOVE"},
        edge={"evidence_status": "HOLDOUT_SUPPORTED", "market_key": "DNB"},
        market_selection={
            "recommended_market": "DNB",
            "recommended_selection": "2",
            "recommended_odds": 2.25,
            "real_market_data": True,
        },
    )
    assert decision.user_state == "FIRSAT"
    assert decision.recommended_market == "DNB"
    assert decision.recommended_selection == "2"


def test_synthetic_dc_is_rejected():
    candidate = _candidate()
    decision = decide_engine_candidate(
        candidate,
        movement={"primary_class": "CONFIRMED_MOVE"},
        edge={"evidence_status": "HOLDOUT_SUPPORTED", "market_key": "DC"},
        market_selection={
            "recommended_market": "DC",
            "recommended_selection": "1X",
            "recommended_odds": 1.30,
            "real_market_data": False,
        },
    )
    assert decision.user_state == "IZLE"
    assert decision.recommended_market is None
    assert "DC_REAL_MARKET_DATA_REQUIRED" in decision.risks


def test_cross_market_conflict_is_hard_stop():
    candidate = _candidate()
    decision = decide_engine_candidate(
        candidate,
        movement={"primary_class": "CONFIRMED_MOVE"},
        edge=_holdout_edge(),
        cross_market={"status": "CONFLICT"},
    )
    assert decision.user_state == "UZAK_DUR"
    assert "CROSS_MARKET_CONFLICT" in decision.risks


def test_poly_support_cannot_create_firsat_without_validated_edge():
    candidate = _candidate()
    decision = decide_engine_candidate(
        candidate,
        movement={"primary_class": "CONFIRMED_MOVE"},
        edge={"evidence_status": "RESEARCH_CANDIDATE", "market_key": "1X2"},
        poly={"status": "POLY_CONFIRMED"},
    )
    assert decision.user_state == "IZLE"
    assert "POLY_SUPPORT" in decision.reasons


def test_poly_conflict_downgrades_otherwise_ready_candidate():
    candidate = _candidate()
    decision = decide_engine_candidate(
        candidate,
        movement={"primary_class": "CONFIRMED_MOVE"},
        edge=_holdout_edge(),
        poly={"status": "CONFLICT"},
    )
    assert decision.user_state == "IZLE"
    assert "POLY_CONFLICT" in decision.risks
