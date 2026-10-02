from analysis_v2.poly_confirmation import (
    PolyConfirmationClient,
    PolyConfirmationConfig,
    apply_poly_to_trigger,
    evaluate_big_trades,
    evaluate_general_poly_direction,
    evaluate_poly_confirmation,
    evaluate_successful_wallet_consensus,
)


HOME = "Alpha FC"
AWAY = "Beta United"


def trade(selection, amount, *, action="buy", outcome="yes", wallet="0x1"):
    return {
        "wallet": wallet,
        "market_type": "1x2",
        "selection": selection,
        "side": action,
        "action": action,
        "outcome_raw": outcome,
        "amount_usdc": amount,
        "price": 0.5,
    }


def test_general_poly_direction_supports_target():
    rows = [
        trade(AWAY, 9000),
        trade(AWAY, 4000),
        trade(HOME, 4000),
        trade("Beraberlik", 2000),
    ]
    result = evaluate_general_poly_direction(
        "2", rows, home_team=HOME, away_team=AWAY
    )
    assert result["state"] == "SUPPORT"
    assert result["leader"] == "2"


def test_general_poly_direction_conflicts_with_target():
    rows = [
        trade(HOME, 14000),
        trade(AWAY, 3000),
        trade("Beraberlik", 1000),
    ]
    result = evaluate_general_poly_direction(
        "2", rows, home_team=HOME, away_team=AWAY
    )
    assert result["state"] == "CONFLICT"
    assert result["leader"] == "1"


def test_general_poly_high_volume_without_clear_lead_is_neutral():
    rows = [
        trade(HOME, 7000),
        trade(AWAY, 6500),
        trade("Draw", 2500),
    ]
    result = evaluate_general_poly_direction(
        "1", rows, home_team=HOME, away_team=AWAY
    )
    assert result["state"] == "NEUTRAL"


def test_no_yes_buy_data_is_unavailable_not_inferred_from_no():
    rows = [
        trade(AWAY, 20000, outcome="no"),
        trade(AWAY, 20000, action="sell"),
    ]
    result = evaluate_general_poly_direction(
        "2", rows, home_team=HOME, away_team=AWAY
    )
    assert result["state"] == "UNAVAILABLE"


def test_big_trade_component_supports_target():
    rows = [
        trade(AWAY, 10000),
        trade(HOME, 3000),
    ]
    result = evaluate_big_trades(
        "2", rows, home_team=HOME, away_team=AWAY
    )
    assert result["state"] == "SUPPORT"
    assert result["qualifying_trade_count"] == 1


def test_big_trades_can_conflict():
    rows = [
        trade(HOME, 13000),
        trade(AWAY, 6000),
    ]
    result = evaluate_big_trades(
        "2", rows, home_team=HOME, away_team=AWAY
    )
    assert result["state"] == "CONFLICT"


def wallet_stats(wallet, win_rate, resolved):
    return {
        "wallet": wallet,
        "win_rate": win_rate,
        "resolved_total": resolved,
    }


def test_successful_wallet_consensus_supports_target():
    stats = [
        wallet_stats("0xa", 62, 30),
        wallet_stats("0xb", 58, 20),
        wallet_stats("0xc", 51, 100),
    ]
    activity = [
        trade(AWAY, 3000, wallet="0xa"),
        trade(AWAY, 2200, wallet="0xb"),
        trade(HOME, 5000, wallet="0xc"),
    ]
    result = evaluate_successful_wallet_consensus(
        "2",
        activity,
        stats,
        home_team=HOME,
        away_team=AWAY,
    )
    assert result["state"] == "SUPPORT"
    assert result["wallet_votes"]["2"] == 2
    assert result["qualified_wallet_count"] == 2


def test_successful_wallet_consensus_ignores_small_bets():
    stats = [
        wallet_stats("0xa", 62, 30),
        wallet_stats("0xb", 58, 20),
    ]
    activity = [
        trade(AWAY, 500, wallet="0xa"),
        trade(AWAY, 900, wallet="0xb"),
    ]
    result = evaluate_successful_wallet_consensus(
        "2",
        activity,
        stats,
        home_team=HOME,
        away_team=AWAY,
    )
    assert result["state"] == "UNAVAILABLE"


def test_successful_wallet_consensus_can_conflict():
    stats = [
        wallet_stats("0xa", 70, 50),
        wallet_stats("0xb", 60, 25),
    ]
    activity = [
        trade(HOME, 4000, wallet="0xa"),
        trade(HOME, 3000, wallet="0xb"),
    ]
    result = evaluate_successful_wallet_consensus(
        "2",
        activity,
        stats,
        home_team=HOME,
        away_team=AWAY,
    )
    assert result["state"] == "CONFLICT"


def test_two_supporting_components_make_poly_confirmed():
    trades = [
        trade(AWAY, 12000, wallet="0xa"),
        trade(AWAY, 6000, wallet="0xb"),
        trade(HOME, 2000),
    ]
    stats = [
        wallet_stats("0xa", 65, 30),
        wallet_stats("0xb", 60, 20),
    ]
    result = evaluate_poly_confirmation(
        "2",
        home_team=HOME,
        away_team=AWAY,
        general_trades=trades,
        wallet_activity=trades,
        wallet_stats=stats,
    )
    assert result["status"] == "POLY_CONFIRMED"
    assert len(result["supporting_components"]) >= 2


def test_support_and_conflict_make_poly_mixed():
    general = [
        trade(AWAY, 15000),
        trade(HOME, 2000),
    ]
    stats = [
        wallet_stats("0xa", 65, 30),
        wallet_stats("0xb", 60, 20),
    ]
    activity = [
        trade(HOME, 3000, wallet="0xa"),
        trade(HOME, 2500, wallet="0xb"),
    ]
    result = evaluate_poly_confirmation(
        "2",
        home_team=HOME,
        away_team=AWAY,
        general_trades=general,
        wallet_activity=activity,
        wallet_stats=stats,
    )
    assert result["status"] == "POLY_MIXED"
    assert "POLY_INTERNAL_DISAGREEMENT" in result["risk_flags"]


def test_poly_does_not_change_primary_recommendation():
    poly = {
        "poly_confirmation_version": "v",
        "status": "POLY_CONFLICT",
        "reason_codes": ["x"],
        "risk_flags": ["POLY_OPPOSING_EVIDENCE"],
        "supporting_components": [],
        "conflicting_components": ["general_direction"],
        "components": {},
        "config_snapshot": {"a": 1},
    }
    trigger = {
        "recommended_market": "DC",
        "recommended_selection": "X2",
        "engine_reason": {"primary_class": "CONFIRMED_MOVE"},
        "config_snapshot": {"classification": {"x": 1}},
        "features": {"cross_market": {"status": "CROSS_CONFIRMED"}},
    }
    merged = apply_poly_to_trigger(trigger, poly)
    assert merged["recommended_market"] == "DC"
    assert merged["recommended_selection"] == "X2"
    assert merged["engine_reason"]["primary_class"] == "CONFIRMED_MOVE"
    assert merged["engine_reason"]["poly_confirmation"]["status"] == "POLY_CONFLICT"


class _Response:
    def __init__(self, rows, status=200):
        self._rows = rows
        self.status_code = status
        self.text = "json"

    def json(self):
        return self._rows


class _Session:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        params = kwargs["params"]
        if url.endswith("/polymarket_matches"):
            assert params["event_id"] == "eq.evt-1"
            return _Response([
                {
                    "event_id": "evt-1",
                    "slug": "alpha-beta",
                    "home": HOME,
                    "away": AWAY,
                    "kickoff_utc": "2026-10-03T18:00:00Z",
                }
            ])
        if url.endswith("/polymarket_trades"):
            return _Response([])
        if url.endswith("/tracked_wallet_activity"):
            return _Response([])
        if url.endswith("/tracked_wallets"):
            return _Response([])
        raise AssertionError(url)


def test_client_reads_by_exact_event_id():
    session = _Session()
    client = PolyConfirmationClient(
        "https://example.supabase.co",
        "read-key",
        session=session,
    )
    payload = client.fetch_event_payload("evt-1")
    assert payload["found"] is True
    assert payload["event_id"] == "evt-1"
    assert all(
        "event_id=eq" not in call[0]
        for call in session.calls
    )


def test_client_requires_exact_event_id():
    session = _Session()
    client = PolyConfirmationClient(
        "https://example.supabase.co",
        "read-key",
        session=session,
    )
    try:
        client.fetch_event_payload("")
    except ValueError:
        pass
    else:
        raise AssertionError("empty event_id must fail")


def test_thresholds_are_explicit_forward_test_config():
    cfg = PolyConfirmationConfig(
        big_trade_min_usdc=7500,
        successful_wallet_min_win_rate_pct=60,
    )
    assert cfg.big_trade_min_usdc == 7500
    assert cfg.successful_wallet_min_win_rate_pct == 60
