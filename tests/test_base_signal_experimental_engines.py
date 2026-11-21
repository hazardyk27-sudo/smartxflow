"""Strict, deterministic tests for prospective EKOL 3 / OVER_STRONG tags."""
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from base_signal_engine.rules import Fixture, Quote, Snapshot, evaluate_base
from base_signal_engine.experimental_engines import evaluate_t6_experiments

KICK = datetime(2026, 11, 22, 20, tzinfo=timezone.utc)
FX = Fixture("fixture-experimental-test", KICK)


def snap(market, hours, quotes, lag=3):
    return Snapshot(market, KICK-timedelta(hours=hours, minutes=lag),
                    {side: Quote(*values) for side, values in quotes.items()})


def _x(h, a, x, two, odds="1.75", side="1"):
    money = (a, x, two)
    total = sum(money)
    return snap("1X2", h, {
        "1": (odds, str(a), str(100 * a/total)),
        "X": ("3.5", str(x), str(100 * x/total)),
        "2": ("4.2", str(two), str(100 * two/total)),
    })


def _over(h, money, share, lag=3):
    return snap("OU25", h, {"O": ("1.60", str(money), str(share)),
                            "U": ("2.40", "100", str(100-share))}, lag=lag)


def _btts(h, yes_odds, lag=3):
    return snap("BTTS", h, {"Y": (str(yes_odds), "1900", "70"),
                            "N": ("2.20", "500", "30")}, lag=lag)


def run(*snaps):
    core = evaluate_base(FX, 6, snaps)
    return evaluate_t6_experiments(FX, snaps, core)


def test_ekol3_pass_and_no_change_to_core_signals():
    # 80% base share -> 90% first-hour inflow -> 90% two-hour inflow.
    snaps = (_x(8, 1600, 200, 200), _x(7, 1960, 220, 220),
             _x(6, 2320, 240, 240, odds="1.70"))
    tags, states = run(*snaps)
    assert states["EKOL_3"] == "PASS"
    assert [t["engine"] for t in tags] == ["EKOL_3"]
    assert tags[0]["checkpoint"] == 6
    assert tags[0]["label"] == "EXPERIMENTAL"
    assert "t7_observed_at" in tags[0]["evidence"]


def test_ekol3_rejects_no_t7_and_stale_t7_and_future_t6():
    a = _x(8, 1600, 200, 200)
    c = _x(6, 2320, 240, 240, odds="1.70")
    assert run(a, c)[1]["EKOL_3"] == "MISSING_FRESH_T8_T7_T6"
    stale = _x(7, 1960, 220, 220)
    stale = Snapshot(stale.market, stale.observed_at - timedelta(minutes=12), stale.quotes)
    assert run(a, stale, c)[1]["EKOL_3"] == "MISSING_FRESH_T8_T7_T6"
    future = Snapshot(c.market, KICK-timedelta(hours=6)+timedelta(seconds=1), c.quotes)
    assert run(a, _x(7, 1960, 220, 220), future)[1]["EKOL_3"] == "NO_CORE_V1"


def test_ekol3_rejects_first_second_and_price():
    base = _x(8, 1600, 200, 200)
    assert run(base, _x(7, 1700, 240, 240), _x(6, 2300, 260, 260))[1]["EKOL_3"] == "FIRST_HOUR_ACCEL_FAIL"
    assert run(base, _x(7, 1960, 220, 220), _x(6, 2200, 275, 275))[1]["EKOL_3"] == "TWO_HOUR_ACCEL_FAIL"
    assert run(base, _x(7, 1960, 220, 220), _x(6, 2320, 240, 240, odds="1.85"))[1]["EKOL_3"] == "DEVIG_PRICE_CONFIRM_FAIL"


def test_ekol3_rejects_negative_selection_flow():
    a = _x(8, 1600, 200, 200)
    b = _x(7, 2000, 190, 200)
    c = _x(6, 2500, 240, 240)
    assert run(a, b, c)[1]["EKOL_3"] == "NEGATIVE_SELECTION_FLOW"


def test_over_strong_pass_requires_matching_market_provenance():
    o8 = _over(8, 3000, 84)
    o6 = _over(6, 3800, 83)
    b6 = _btts(6, "1.78")
    tags, states = run(o8, o6, b6)
    assert states["OVER_STRONG"] == "PASS"
    assert [t["engine"] for t in tags] == ["OVER_STRONG"]
    assert tags[0]["evidence"]["over_share_delta_pp"] == "-1"
    assert tags[0]["label"] == "EXPERIMENTAL"


def test_over_strong_rejects_missing_stale_or_unsynced_cross_market():
    o8, o6 = _over(8, 3000, 84), _over(6, 3800, 83)
    assert run(o8, o6)[1]["OVER_STRONG"] == "CROSSMARKET_UNVERIFIED"
    assert run(o8, o6, _btts(6, "1.78", lag=4))[1]["OVER_STRONG"] == "CROSSMARKET_TIMESTAMP_MISMATCH"
    assert run(_over(8, 3000, 84, lag=20), o6, _btts(6, "1.78"))[1]["OVER_STRONG"] == "CROSSMARKET_UNVERIFIED"


def test_over_strong_rejects_limits_without_modifying_premium():
    o8 = _over(8, 3000, 84)
    assert run(o8, _over(6, 3800, 83), _btts(6, "1.60"))[1]["OVER_STRONG"] == "BTTS_YES_PRICE_FAIL"
    assert run(o8, _over(6, 2400, 83), _btts(6, "1.78"))[1]["OVER_STRONG"] == "OVER_MONEY_FAIL"
    assert run(o8, _over(6, 3800, 82), _btts(6, "1.78"))[1]["OVER_STRONG"] == "SHARE_RETENTION_FAIL"
    tags, state = run(o8, _over(6, 3800, 83), _btts(6, "1.78"))
    assert state["OVER_STRONG"] == "PASS"
    core = evaluate_base(FX, 6, (o8, _over(6, 3800, 83), _btts(6, "1.78")))
    assert {s.engine for s in core.signals} >= {"STABLE_OVER_2_5", "PREMIUM_OVER_2_5"}
