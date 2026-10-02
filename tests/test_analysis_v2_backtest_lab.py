import math

from analysis_v2.backtest_lab import (
    BacktestConfig,
    BacktestDataClient,
    calculate_metrics,
    period_report,
    prepare_backtest_records,
    run_backtest,
)
from analysis_v2.entry_price import (
    resolve_entry_odds,
    resolve_entry_odds_with_source,
)


def row(
    signal_id,
    outcome,
    *,
    trigger_odds=3.40,
    recommended_market="DC",
    recommended_selection="X2",
    recommended_odds=1.60,
    entry_odds=None,
    pnl_units=None,
    closing_odds=None,
    state="FIRSAT",
    primary="CONFIRMED_MOVE",
    trigger_at="2026-01-01T10:00:00Z",
    settled_at="2026-01-01T20:00:00Z",
    engine_key="confirmed_money_v2",
    engine_version="2.0",
    component_level="STRONG",
):
    if pnl_units is None:
        if outcome == "WIN":
            pnl_units = (
                recommended_odds - 1
                if recommended_odds
                else None
            )
        elif outcome == "LOSS":
            pnl_units = -1
        elif outcome in ("PUSH", "VOID"):
            pnl_units = 0

    return {
        "signal_id": signal_id,
        "match_id_hash": "a1b2c3d4e5f6",
        "market_key": "1X2",
        "selection_code": "2",
        "recommended_market": recommended_market,
        "recommended_selection": recommended_selection,
        "recommended_odds": recommended_odds,
        "trigger_odds": trigger_odds,
        "entry_odds": entry_odds,
        "outcome": outcome,
        "pnl_units": pnl_units,
        "closing_odds": closing_odds,
        "trigger_at": trigger_at,
        "settled_at": settled_at,
        "engine_key": engine_key,
        "engine_version": engine_version,
        "engine_reason": {
            "primary_class": primary,
            "explainable_confidence": {
                "user_state": state
            },
        },
        "features": {
            "explainable_confidence": {
                "user_state": state,
                "components": {
                    "price_confirmation": {
                        "level": component_level
                    },
                    "money_flow": {
                        "level": component_level
                    },
                    "timing": {
                        "level": "MEDIUM"
                    },
                    "cross_market": {
                        "level": component_level
                    },
                    "poly": {
                        "level": "NEUTRAL"
                    },
                    "risk": {
                        "level": "NEUTRAL"
                    },
                },
            }
        },
        "config_snapshot": {
            "classification": {
                "confirmed_price_drop_pct": 5.0
            }
        },
    }


def test_recommended_market_odds_not_source_trigger_odds():
    signal = {
        "market_key": "1X2",
        "selection_code": "2",
        "trigger_odds": 3.40,
        "recommended_market": "DC",
        "recommended_selection": "X2",
        "recommended_odds": 1.62,
    }
    odds, source = resolve_entry_odds_with_source(
        signal
    )
    assert odds == 1.62
    assert source == "recommended_odds"


def test_changed_market_without_recommended_odds_never_falls_back():
    signal = {
        "market_key": "1X2",
        "selection_code": "2",
        "trigger_odds": 3.40,
        "recommended_market": "DC",
        "recommended_selection": "X2",
    }
    odds, source = resolve_entry_odds_with_source(
        signal
    )
    assert odds is None
    assert (
        source
        == "missing_recommended_market_odds"
    )


def test_same_market_legacy_signal_can_fall_back_to_trigger_odds():
    signal = {
        "market_key": "1X2",
        "selection_code": "2",
        "trigger_odds": 3.40,
        "recommended_market": "1X2",
        "recommended_selection": "2",
    }
    assert resolve_entry_odds(signal) == 3.40


def test_prepare_records_repairs_old_wrong_settlement_price():
    record = row(
        "s1",
        "WIN",
        recommended_odds=1.60,
        entry_odds=3.40,
        pnl_units=2.40,
    )
    result = prepare_backtest_records(
        [record]
    )[0]
    assert (
        result["backtest_entry_odds"]
        == 1.60
    )
    assert math.isclose(
        result["backtest_pnl_units"],
        0.60,
    )
    assert (
        "SETTLEMENT_ENTRY_ODDS_MISMATCH"
        in result["quality_flags"]
    )
    assert (
        "SETTLEMENT_PNL_MISMATCH"
        in result["quality_flags"]
    )


def test_legacy_cross_market_without_recommended_odds_is_not_trusted():
    record = row(
        "s_missing",
        "WIN",
        recommended_odds=None,
        entry_odds=3.40,
        pnl_units=2.40,
    )
    result = prepare_backtest_records(
        [record]
    )[0]
    assert (
        result["backtest_entry_odds"]
        is None
    )
    assert (
        result["backtest_pnl_units"]
        is None
    )
    assert (
        "ENTRY_ODDS_MISSING"
        in result["quality_flags"]
    )
    assert (
        "SETTLEMENT_ENTRY_ODDS_MISMATCH"
        in result["quality_flags"]
    )


def test_basic_metrics_hit_roi_avg_odds():
    rows = [
        row(
            "s1",
            "WIN",
            recommended_odds=2.0,
            pnl_units=1.0,
        ),
        row(
            "s2",
            "LOSS",
            recommended_odds=2.0,
            pnl_units=-1.0,
        ),
        row(
            "s3",
            "WIN",
            recommended_odds=2.0,
            pnl_units=1.0,
        ),
        row(
            "s4",
            "PUSH",
            recommended_market="DNB",
            recommended_selection="2",
            recommended_odds=2.0,
            pnl_units=0.0,
        ),
    ]
    metrics = calculate_metrics(
        prepare_backtest_records(rows)
    )
    assert metrics["n_staked"] == 4
    assert metrics["wins"] == 2
    assert metrics["losses"] == 1
    assert metrics["pushes"] == 1
    assert math.isclose(
        metrics["hit_rate_pct"],
        66.66666666666666,
    )
    assert metrics["avg_odds"] == 2.0
    assert metrics["profit_units"] == 1.0
    assert metrics["roi_pct"] == 25.0


def test_clv_positive_when_entry_beats_closing_price():
    rows = [
        row(
            "s1",
            "WIN",
            recommended_odds=2.0,
            closing_odds=1.80,
            pnl_units=1.0,
        ),
        row(
            "s2",
            "LOSS",
            recommended_odds=1.80,
            closing_odds=1.90,
            pnl_units=-1.0,
        ),
    ]
    metrics = calculate_metrics(
        prepare_backtest_records(rows)
    )
    assert metrics["clv_n"] == 2
    assert (
        metrics["avg_clv_pct"]
        is not None
    )
    assert (
        metrics["positive_clv_rate_pct"]
        == 50.0
    )


def test_max_drawdown_uses_realized_settlement_order():
    rows = [
        row(
            "s1",
            "WIN",
            recommended_odds=2.0,
            pnl_units=1.0,
            settled_at="2026-01-01T20:00:00Z",
        ),
        row(
            "s2",
            "LOSS",
            recommended_odds=2.0,
            pnl_units=-1.0,
            settled_at="2026-01-02T20:00:00Z",
        ),
        row(
            "s3",
            "LOSS",
            recommended_odds=2.0,
            pnl_units=-1.0,
            settled_at="2026-01-03T20:00:00Z",
        ),
        row(
            "s4",
            "WIN",
            recommended_odds=2.0,
            pnl_units=1.0,
            settled_at="2026-01-04T20:00:00Z",
        ),
    ]
    metrics = calculate_metrics(
        prepare_backtest_records(rows)
    )
    assert (
        metrics["max_drawdown_units"]
        == 2.0
    )
    assert (
        metrics["ending_equity_units"]
        == 0.0
    )


def test_market_implied_calibration_excludes_dnb_push_market():
    rows = [
        row(
            "s1",
            "WIN",
            recommended_market="DC",
            recommended_odds=2.0,
            pnl_units=1.0,
        ),
        row(
            "s2",
            "LOSS",
            recommended_market="DC",
            recommended_odds=2.0,
            pnl_units=-1.0,
        ),
        row(
            "s3",
            "PUSH",
            recommended_market="DNB",
            recommended_odds=2.0,
            pnl_units=0.0,
        ),
    ]
    metrics = calculate_metrics(
        prepare_backtest_records(rows)
    )
    calibration = (
        metrics[
            "market_implied_calibration"
        ]
    )
    assert calibration["n"] == 2
    assert (
        calibration[
            "avg_market_implied_pct"
        ]
        == 50.0
    )
    assert (
        calibration[
            "observed_hit_rate_pct"
        ]
        == 50.0
    )
    assert (
        calibration[
            "observed_minus_implied_pp"
        ]
        == 0.0
    )


def test_run_backtest_has_state_and_component_calibration():
    rows = [
        row(
            "s1",
            "WIN",
            state="FIRSAT",
        ),
        row(
            "s2",
            "LOSS",
            state="FIRSAT",
        ),
        row(
            "s3",
            "LOSS",
            state="IZLE",
            component_level="MEDIUM",
        ),
    ]
    report = run_backtest(rows)
    assert (
        report["by_user_state"][
            "FIRSAT"
        ]["n_staked"]
        == 2
    )
    assert (
        report["by_user_state"][
            "IZLE"
        ]["n_staked"]
        == 1
    )
    assert (
        report["firsat_only"][
            "n_staked"
        ]
        == 2
    )
    assert (
        report["component_calibration"][
            "price_confirmation"
        ]["STRONG"]["n_staked"]
        == 2
    )
    assert (
        report["component_calibration"][
            "price_confirmation"
        ]["MEDIUM"]["n_staked"]
        == 1
    )


def test_config_fingerprint_cohort_is_stable():
    report = run_backtest(
        [
            row("s1", "WIN"),
            row("s2", "LOSS"),
        ]
    )
    assert (
        len(
            report[
                "by_config_fingerprint"
            ]
        )
        == 1
    )


def test_small_sample_warning_is_explicit():
    metrics = calculate_metrics(
        prepare_backtest_records(
            [row("s1", "WIN")]
        ),
        config=BacktestConfig(
            small_sample_n=30
        ),
    )
    assert (
        "SMALL_SAMPLE"
        in metrics["warnings"]
    )


def test_period_report_is_trigger_time_bounded():
    rows = [
        row(
            "s1",
            "WIN",
            trigger_at=(
                "2026-01-10T10:00:00Z"
            ),
        ),
        row(
            "s2",
            "LOSS",
            trigger_at=(
                "2026-02-10T10:00:00Z"
            ),
        ),
        row(
            "s3",
            "WIN",
            trigger_at=(
                "2026-03-10T10:00:00Z"
            ),
        ),
    ]
    report = period_report(
        rows,
        {
            "jan": (
                "2026-01-01T00:00:00Z",
                "2026-02-01T00:00:00Z",
            ),
            "feb": (
                "2026-02-01T00:00:00Z",
                "2026-03-01T00:00:00Z",
            ),
        },
    )
    assert report["jan"]["n_staked"] == 1
    assert report["jan"]["wins"] == 1
    assert report["feb"]["n_staked"] == 1
    assert report["feb"]["losses"] == 1


class Response:
    def __init__(
        self,
        rows,
        status=200,
    ):
        self._rows = rows
        self.status_code = status
        self.text = "json"

    def json(self):
        return self._rows


class Session:
    def __init__(self):
        self.calls = []

    def get(
        self,
        url,
        **kwargs,
    ):
        self.calls.append(
            (url, kwargs)
        )
        if url.endswith(
            "/analysis_v2_signal_current"
        ):
            return Response([])
        if url.endswith(
            "/moneyway_snapshots"
        ):
            return Response(
                [
                    {
                        "odds": 1.55,
                        "scraped_at_utc": (
                            "2026-01-01T17:55:00Z"
                        ),
                    }
                ]
            )
        raise AssertionError(url)


def test_data_client_reads_only_settled_immutable_view():
    session = Session()
    client = BacktestDataClient(
        "https://example.supabase.co",
        "key",
        session=session,
    )
    client.fetch_settled_signals(
        engine_key="confirmed_money_v2"
    )
    params = session.calls[0][1][
        "params"
    ]
    assert (
        params["settlement_id"]
        == "not.is.null"
    )
    assert (
        params["engine_key"]
        == "eq.confirmed_money_v2"
    )


def test_closing_odds_query_uses_recommended_market_pre_kickoff():
    session = Session()
    client = BacktestDataClient(
        "https://example.supabase.co",
        "key",
        session=session,
    )
    signal = row("s1", "WIN")
    signal["kickoff_utc"] = (
        "2026-01-01T18:00:00Z"
    )
    close = client.fetch_closing_odds(
        signal,
        max_age_minutes=10,
    )
    assert close == 1.55
    params = session.calls[0][1][
        "params"
    ]
    assert params["market"] == "eq.DC"
    assert params["selection"] == "eq.X2"
    assert (
        params["scraped_at_utc"]
        == "lt.2026-01-01T18:00:00+00:00"
    )


def test_stale_closing_snapshot_is_rejected():
    class StaleSession(Session):
        def get(
            self,
            url,
            **kwargs,
        ):
            self.calls.append(
                (url, kwargs)
            )
            return Response(
                [
                    {
                        "odds": 1.55,
                        "scraped_at_utc": (
                            "2026-01-01T12:00:00Z"
                        ),
                    }
                ]
            )

    session = StaleSession()
    client = BacktestDataClient(
        "https://example.supabase.co",
        "key",
        session=session,
    )
    signal = row("s1", "WIN")
    signal["kickoff_utc"] = (
        "2026-01-01T18:00:00Z"
    )
    assert (
        client.fetch_closing_odds(
            signal,
            max_age_minutes=60,
        )
        is None
    )
