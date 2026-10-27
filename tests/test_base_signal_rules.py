"""Frozen Moneyway Base rules: deterministic checks, no I/O or user bets."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from base_signal_engine import (
    Fixture, Quote, Snapshot, choose_base_checkpoint, evaluate_base,
    evaluate_early, evaluate_early_t12, select_snapshot,
)

KICKOFF = datetime(2026, 10, 19, 21, tzinfo=timezone.utc)
FX = Fixture("provider-fixture-uid-123", KICKOFF)


def snapshot(market, hours, **kwargs):
    when = KICKOFF - timedelta(hours=hours, minutes=5)
    if market == "1X2":
        params = {"1": ("1.80", "1600", "82"), "X": ("3.4", "200", "10"), "2": ("4.0", "160", "8")}
    elif market == "OU25":
        params = {"O": ("1.72", "3000", "80"), "U": ("2.1", "750", "20")}
    else:
        params = {"Y": ("1.75", "850", "65"), "N": ("2.1", "450", "35")}
    params.update(kwargs)
    return Snapshot(market, when, {s: Quote(*vals) for s, vals in params.items()})


def names(result):
    return {s.engine for s in result.signals}


def test_all_base_markets_and_tags():
    snaps = [snapshot("1X2", 6, **{"1": ("1.74", "12000", "90"), "X": ("4.0", "700", "5"), "2": ("6", "700", "5")}),
             snapshot("OU25", 6), snapshot("BTTS", 6)]
    # Previous 3h complete coverage, without a price increase or share break.
    snaps += [snapshot("1X2", h) for h in (9, 8, 7)]
    result = evaluate_base(FX, 6, snaps)
    assert names(result) == {"1X2_CONCENTRATION_V1", "1X2_CONCENTRATION_V2", "HEAVY_1X2_CONCENTRATION",
                             "STABLE_OVER_2_5", "PREMIUM_OVER_2_5", "PREMIUM_OVER_MIN1_70", "BTTS_YES"}
    assert result.v2_state == "QUALIFIED"
    assert next(s for s in result.signals if s.engine == "HEAVY_1X2_CONCENTRATION").label == "STRENGTH_TAG"


def test_v2_requires_all_hourly_history():
    result = evaluate_base(FX, 6, [snapshot("1X2", 6)])
    assert "1X2_CONCENTRATION_V1" in names(result)
    assert "1X2_CONCENTRATION_V2" not in names(result)
    assert result.v2_state == "MISSING_THREE_HOUR_COVERAGE"


def test_v2_fails_for_adverse_odds_or_share_break():
    basic = [snapshot("1X2", h) for h in (9, 8, 7, 6)]
    high_odds = basic + [snapshot("1X2", 7.5, **{"1": ("1.90", "1600", "82"), "X": ("3.4", "200", "10"), "2": ("4.0", "160", "8")})]
    assert evaluate_base(FX, 6, high_odds).v2_state == "THREE_HOUR_ADVERSE_ODDS"
    low_share = basic + [snapshot("1X2", 7.5, **{"1": ("1.80", "1600", "69"), "X": ("3.4", "300", "15"), "2": ("4.0", "350", "16")})]
    assert evaluate_base(FX, 6, low_share).v2_state == "THREE_HOUR_SHARE_BREAK"


def test_surprise_no_absolute_money_threshold_and_no_draw():
    snap = snapshot("1X2", 8, **{"1": ("3.50", "12", "60"), "X": ("3.5", "4", "20"), "2": ("2", "4", "20")})
    r = evaluate_base(FX, 8, [snap])
    s = [x for x in r.signals if x.engine == "SURPRISE_TEAM"]
    assert len(s) == 1 and s[0].side == "1" and s[0].amount == Decimal("12")


def test_premium_min170_and_boundaries():
    r = evaluate_base(FX, 8, [snapshot("OU25", 8, **{"O": ("1.69", "2500", "75"), "U": ("2.1", "850", "25")})])
    assert "PREMIUM_OVER_2_5" in names(r)
    assert "PREMIUM_OVER_MIN1_70" not in names(r)
    r2 = evaluate_base(FX, 8, [snapshot("OU25", 8, **{"O": ("1.80", "2500", "75"), "U": ("2.1", "850", "25")})])
    assert "PREMIUM_OVER_MIN1_70" in names(r2)


def test_heavy_uses_its_own_amount_share_threshold_without_v1_odds_band():
    for odds in ("1.32", "1.38", "2.51"):
        snap = snapshot("1X2", 6, **{
            "1": (odds, "143569.34", "84.4"),
            "X": ("3", "17000", "10"),
            "2": ("8", "11200", "5.6"),
        })
        result = evaluate_base(FX, 6, [snap])
        assert "HEAVY_1X2_CONCENTRATION" in names(result)
        assert "1X2_CONCENTRATION_V1" not in names(result)
    for odds in ("1.40", "2.50"):
        snap = snapshot("1X2", 6, **{
            "1": (odds, "143569.34", "84.4"),
            "X": ("3", "17000", "10"),
            "2": ("8", "11200", "5.6"),
        })
        assert {"1X2_CONCENTRATION_V1", "HEAVY_1X2_CONCENTRATION"} <= names(
            evaluate_base(FX, 6, [snap])
        )


def test_heavy_still_requires_ten_thousand_and_80_percent():
    for amount, share, draw_share, away_share in (
        ("9999", "84", "10", "6"),
        ("12000", "79.9", "12", "8.1"),
    ):
        snap = snapshot("1X2", 6, **{
            "1": ("1.80", amount, share),
            "X": ("3.4", "500", draw_share),
            "2": ("4.0", "400", away_share),
        })
        result = evaluate_base(FX, 6, [snap])
        assert "HEAVY_1X2_CONCENTRATION" not in names(result)


def test_v2_rejects_wolfsburg_three_hour_rebound_from_intra_window_low():
    # T-9 -> T-6: 2.10 -> 2.14 (+1.90%) would pass first-anchor only.
    # A later 2.04 -> 2.14 rebound (+4.90%) must reject V2.
    odds = {9: "2.10", 8: "2.06", 7: "2.04", 6: "2.14"}
    snaps = [snapshot("1X2", h, **{
        "1": ("3.40", "1300", "10"),
        "X": ("3.60", "1000", "8"),
        "2": (o, "12217.01", "82"),
    }) for h, o in odds.items()]
    result = evaluate_base(FX, 6, snaps)
    assert "1X2_CONCENTRATION_V1" in names(result)
    assert "HEAVY_1X2_CONCENTRATION" in names(result)
    assert "1X2_CONCENTRATION_V2" not in names(result)
    assert result.v2_state == "THREE_HOUR_ADVERSE_ODDS"


def test_v2_intra_window_peak_does_not_use_future_trough():
    # Earlier high cannot be compared with a trough which occurs later.
    snaps = [snapshot("1X2", h, **{
        "1": (price, "12000", "82"), "X": ("3.4", "1700", "10"),
        "2": ("4", "1000", "8"),
    }) for h, price in {9: "1.95", 8: "1.96", 7: "1.94", 6: "1.95"}.items()]
    result = evaluate_base(FX, 6, snaps)
    assert result.v2_state == "QUALIFIED"
    assert "1X2_CONCENTRATION_V2" in names(result)


def test_v2_adverse_rebound_in_dense_midpoint_and_3pct_boundary():
    base = [snapshot("1X2", h, **{
        "1": ("2.00", "12000", "82"), "X": ("3.4", "1700", "10"),
        "2": ("4", "1000", "8"),
    }) for h in (9, 8, 7, 6)]
    # Exactly 3% is allowed; anything above 3% in the 3h window fails.
    at_boundary = snapshot("1X2", 7.5, **{
        "1": ("2.0600", "12000", "82"), "X": ("3.4", "1700", "10"),
        "2": ("4", "1000", "8"),
    })
    above_boundary = snapshot("1X2", 7.5, **{
        "1": ("2.0601", "12000", "82"), "X": ("3.4", "1700", "10"),
        "2": ("4", "1000", "8"),
    })
    assert evaluate_base(FX, 6, base + [at_boundary]).v2_state == "QUALIFIED"
    assert evaluate_base(FX, 6, base + [above_boundary]).v2_state == "THREE_HOUR_ADVERSE_ODDS"


def test_v2_t8_preliminary_uses_same_trough_rule():
    odds = {11: "2.24", 10: "2.10", 9: "2.13", 8: "2.20"}
    snaps = [snapshot("1X2", h, **{
        "1": (o, "14000", "85"), "X": ("3.4", "1500", "10"),
        "2": ("4", "800", "5"),
    }) for h, o in odds.items()]
    result = evaluate_base(FX, 8, snaps)
    assert result.v2_state == "THREE_HOUR_ADVERSE_ODDS"
    assert "1X2_CONCENTRATION_V1" in names(result)
    assert "1X2_CONCENTRATION_V2" not in names(result)


def test_market_completeness_and_no_stale_or_future_data():
    partial = Snapshot("OU25", KICKOFF - timedelta(hours=6, minutes=2), {"O": Quote("1.7", "9000", "100")})
    stale = snapshot("OU25", 7)
    future = Snapshot("OU25", KICKOFF - timedelta(hours=6) + timedelta(seconds=1), {"O": Quote("1.7", "9000", "90"), "U": Quote("2.1", "900", "10")})
    assert select_snapshot(FX, "OU25", 6, [partial, stale, future]) is None
    assert evaluate_base(FX, 6, [partial, stale, future]).market_states["OU25"] == "INSUFFICIENT_DATA"


def test_t6_authority_even_if_engine_rule_fails():
    t8 = snapshot("1X2", 8)
    t6 = snapshot("1X2", 6, **{"1": ("1.8", "800", "80"), "X": ("3.4", "120", "12"), "2": ("4", "80", "8")})
    assert choose_base_checkpoint(FX, "1X2", [t8, t6], KICKOFF-timedelta(hours=5)) == (6, "AUTHORITATIVE_T6")
    assert "1X2_CONCENTRATION_V1" not in names(evaluate_base(FX, 6, [t8, t6]))
    assert choose_base_checkpoint(FX, "1X2", [t8], KICKOFF-timedelta(hours=7)) == (8, "PRELIMINARY_T8")
    assert choose_base_checkpoint(FX, "1X2", [t8], KICKOFF-timedelta(hours=5)) == (None, "INSUFFICIENT_DATA")


def test_no_late_checkpoint_except_early_retention():
    with pytest.raises(ValueError, match="T-5/4/3"):
        evaluate_base(FX, 5, [])


def test_early_t24_is_cohort_and_early_t12_independent():
    core = snapshot("1X2", 24, **{"1": ("1.52", "12000", "85"), "X": ("3.4", "1200", "10"), "2": ("5", "600", "5")})
    ret = [snapshot("1X2", h) for h in (6, 5, 4, 3)]
    result = evaluate_early(FX, [core, *ret])
    assert result.core_signal and result.core_signal.checkpoint == 24
    assert result.t24_cohort and result.retention_status == "RETAINED"
    t12 = evaluate_early_t12(FX, [snapshot("1X2", 12)])
    assert t12 and t12.engine == "EARLY_MONEY_T12"


def test_early_retention_break_never_reopens():
    core = snapshot("1X2", 72, **{"1": ("1.50", "5200", "55"), "X": ("3.4", "2500", "27"), "2": ("5", "1800", "18")})
    bad = snapshot("1X2", 5, **{"1": ("1.7", "1800", "54"), "X": ("3.4", "700", "21"), "2": ("4", "850", "25")})
    r = evaluate_early(FX, [core, snapshot("1X2", 6),bad,snapshot("1X2", 4),snapshot("1X2", 3)])
    assert r.retention_status == "RETENTION_BREAK"
    assert (5, "RETENTION_BREAK") in r.retention_checkpoints


def test_early_price_floor_preserves_raw_signal():
    core = snapshot("1X2", 72, **{"1": ("1.20", "5200", "80"), "X": ("3.4", "750", "12"), "2": ("5", "500", "8")})
    r = evaluate_early(FX, [core])
    assert r.core_signal and r.core_signal.selection_status == "PRICE_FILTER_REJECT"


def test_naive_time_and_bad_quotes_fail_closed():
    with pytest.raises(ValueError, match="timezone"):
        Fixture("uid", datetime(2026, 10, 20, 21))
    with pytest.raises(ValueError, match="finite"):
        Quote("NaN", "1000", "80")