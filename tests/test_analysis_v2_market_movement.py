from analysis_v2.market_movement import (
    build_market_movement,
    build_selection_points,
    movement_to_signal_fields,
)

HASH = "a1b2c3d4e5f6"


def row(
    at,
    selection,
    odds,
    amount,
    share,
    market="1X2",
    row_id=1,
):
    return {
        "id": row_id,
        "match_id_hash": HASH,
        "market": market,
        "selection": selection,
        "odds": odds,
        "volume": amount,
        "share": share,
        "scraped_at_utc": at,
    }


def cycle(at, one, draw, two, start_id):
    return [
        row(
            at, "1", one[0], one[1], one[2],
            row_id=start_id,
        ),
        row(
            at, "X", draw[0], draw[1], draw[2],
            row_id=start_id + 1,
        ),
        row(
            at, "2", two[0], two[1], two[2],
            row_id=start_id + 2,
        ),
    ]


def history():
    rows = []
    rows += cycle(
        "2026-10-02T05:00:00Z",
        (2.10, 4000, 40),
        (3.30, 2500, 25),
        (3.50, 3500, 35),
        1,
    )
    rows += cycle(
        "2026-10-02T05:59:00Z",
        (2.05, 5000, 45),
        (3.35, 2500, 23),
        (3.55, 3500, 32),
        10,
    )
    rows += cycle(
        "2026-10-02T06:01:00Z",
        (2.04, 5100, 45.5),
        (3.35, 2500, 22.5),
        (3.56, 3600, 32),
        20,
    )
    rows += cycle(
        "2026-10-02T09:58:00Z",
        (1.95, 7000, 55),
        (3.50, 2300, 18),
        (3.80, 3500, 27),
        30,
    )
    rows += cycle(
        "2026-10-02T11:29:00Z",
        (1.88, 8200, 62),
        (3.60, 2100, 16),
        (4.00, 3000, 22),
        40,
    )
    rows += cycle(
        "2026-10-02T11:31:00Z",
        (1.86, 8400, 63),
        (3.62, 2100, 16),
        (4.05, 2900, 21),
        50,
    )
    rows += cycle(
        "2026-10-02T11:55:00Z",
        (1.82, 9000, 67),
        (3.70, 1900, 14),
        (4.20, 2600, 19),
        60,
    )
    rows += cycle(
        "2026-10-02T12:01:00Z",
        (1.70, 12000, 75),
        (3.90, 1800, 11),
        (4.50, 2200, 14),
        70,
    )
    return rows


def test_no_future_leakage_for_windows_or_current():
    features = build_market_movement(
        history(),
        match_id_hash=HASH,
        market_key="1X2",
        selection_code="1",
        as_of="2026-10-02T12:00:00Z",
    )
    assert (
        features["anchors"]["6h"]["at"]
        == "2026-10-02T05:59:00+00:00"
    )
    assert (
        features["anchors"]["2h"]["at"]
        == "2026-10-02T09:58:00+00:00"
    )
    assert (
        features["anchors"]["30m"]["at"]
        == "2026-10-02T11:29:00+00:00"
    )
    assert (
        features["current"]["at"]
        == "2026-10-02T11:55:00+00:00"
    )
    assert features["current"]["odds"] == 1.82


def test_market_volume_uses_real_same_cycle_sibling_amounts():
    points = build_selection_points(
        history(),
        match_id_hash=HASH,
        market_key="1X2",
        selection_code="1",
        as_of="2026-10-02T12:00:00Z",
    )
    current = points[-1]
    assert current.amount == 9000.0
    assert current.market_volume == 13500.0


def test_opening_and_movement_metrics_have_clear_signs():
    features = build_market_movement(
        history(),
        match_id_hash=HASH,
        market_key="1X2",
        selection_code="1",
        as_of="2026-10-02T12:00:00Z",
    )
    assert features["opening"]["odds"] == 2.10
    expected = (2.05 - 1.82) / 2.05 * 100
    assert round(
        features["movement"]["6h"]["odds_drop_pct"], 4
    ) == round(expected, 4)
    assert features["movement"]["6h"]["amount_delta"] == 4000.0
    assert features["movement"]["6h"]["pct_delta"] == 22.0


def test_signal_fields_match_part2_immutable_snapshot_contract():
    features = build_market_movement(
        history(),
        match_id_hash=HASH,
        market_key="1X2",
        selection_code="1",
        as_of="2026-10-02T12:00:00Z",
        kickoff_utc="2026-10-02T18:00:00Z",
    )
    fields = movement_to_signal_fields(features)
    assert fields["opening_odds"] == 2.10
    assert fields["odds_6h"] == 2.05
    assert fields["odds_2h"] == 1.95
    assert fields["odds_30m"] == 1.88
    assert fields["trigger_odds"] == 1.82
    assert fields["trigger_pct"] == 67.0
    assert fields["trigger_amount"] == 9000.0
    assert fields["trigger_volume"] == 13500.0
    assert fields["money_added_6h"] == 4000.0
    assert fields["money_added_2h"] == 2000.0
    assert fields["money_added_30m"] == 800.0
    assert fields["hours_before_kickoff"] == 6.0
    assert (
        fields["features"]["market_movement"]["market_key"]
        == "1X2"
    )


def test_missing_or_stale_anchor_stays_none_not_zero():
    rows = cycle(
        "2026-10-02T11:55:00Z",
        (1.82, 9000, 67),
        (3.7, 1900, 14),
        (4.2, 2600, 19),
        1,
    )
    features = build_market_movement(
        rows,
        match_id_hash=HASH,
        market_key="1X2",
        selection_code="1",
        as_of="2026-10-02T12:00:00Z",
        anchor_tolerance_minutes=30,
    )
    assert features["anchors"]["6h"] is None
    assert features["anchors"]["2h"] is None
    assert features["anchors"]["30m"] is None
    fields = movement_to_signal_fields(features)
    assert fields["odds_6h"] is None
    assert fields["money_added_6h"] is None


def test_real_dc_rows_are_measured_without_using_1x2_rows():
    rows = [
        row(
            "2026-10-02T11:00:00Z", "X2",
            1.62, 5000, 55, market="DC", row_id=1,
        ),
        row(
            "2026-10-02T11:00:00Z", "1X",
            1.30, 3000, 33, market="DC", row_id=2,
        ),
        row(
            "2026-10-02T11:00:00Z", "12",
            1.15, 1100, 12, market="DC", row_id=3,
        ),
        row(
            "2026-10-02T11:55:00Z", "X2",
            1.49, 8000, 64, market="DC", row_id=4,
        ),
        row(
            "2026-10-02T11:55:00Z", "1X",
            1.38, 3200, 26, market="DC", row_id=5,
        ),
        row(
            "2026-10-02T11:55:00Z", "12",
            1.17, 1300, 10, market="DC", row_id=6,
        ),
        row(
            "2026-10-02T11:55:00Z", "2",
            3.05, 99999, 95, market="1X2", row_id=7,
        ),
    ]
    features = build_market_movement(
        rows,
        match_id_hash=HASH,
        market_key="DC",
        selection_code="X2",
        as_of="2026-10-02T12:00:00Z",
    )
    assert features["current"]["amount"] == 8000.0
    assert features["current"]["market_volume"] == 12500.0
    assert features["current"]["pct"] == 64.0


def test_unknown_selection_is_rejected():
    try:
        build_market_movement(
            history(),
            match_id_hash=HASH,
            market_key="DC",
            selection_code="2",
            as_of="2026-10-02T12:00:00Z",
        )
    except ValueError:
        pass
    else:
        raise AssertionError(
            "DC selection 2 must not be accepted"
        )


class _Response:
    def __init__(self, rows, status_code=200):
        self._rows = rows
        self.status_code = status_code
        self.text = "json"

    def json(self):
        return self._rows


class _FetchSession:
    def __init__(self):
        self.calls = []

    def get(self, url, **kwargs):
        self.calls.append((url, kwargs))
        params = kwargs.get("params") or {}
        if params.get("selection") == "eq.1":
            return _Response([
                row(
                    "2026-10-02T05:00:00Z", "1",
                    2.10, 4000, 40, row_id=1,
                )
            ])
        if (
            params.get("scraped_at_utc")
            == "eq.2026-10-02T05:00:00Z"
        ):
            return _Response(
                cycle(
                    "2026-10-02T05:00:00Z",
                    (2.10, 4000, 40),
                    (3.30, 2500, 25),
                    (3.50, 3500, 35),
                    1,
                )
            )
        return _Response(
            cycle(
                "2026-10-02T11:55:00Z",
                (1.82, 9000, 67),
                (3.70, 1900, 14),
                (4.20, 2600, 19),
                20,
            )
        )


def test_snapshot_client_uses_exact_opening_and_bounded_recent_query():
    from analysis_v2.market_movement import SnapshotHistoryClient

    session = _FetchSession()
    client = SnapshotHistoryClient(
        "https://example.supabase.co",
        "read-key",
        session=session,
        page_size=1000,
    )
    rows = client.fetch_market_rows(
        match_id_hash=HASH,
        market_key="1X2",
        selection_code="1",
        as_of="2026-10-02T12:00:00Z",
    )

    assert len(session.calls) == 3
    opening_params = session.calls[0][1]["params"]
    opening_cycle_params = session.calls[1][1]["params"]
    recent_params = session.calls[2][1]["params"]
    assert opening_params["selection"] == "eq.1"
    assert opening_params["limit"] == "1"
    assert (
        opening_cycle_params["scraped_at_utc"]
        == "eq.2026-10-02T05:00:00Z"
    )
    assert (
        "scraped_at_utc.gte.2026-10-02T05:00:00+00:00"
        in recent_params["and"]
    )
    assert (
        "scraped_at_utc.lte.2026-10-02T12:00:00+00:00"
        in recent_params["and"]
    )
    assert any(
        item["scraped_at_utc"] == "2026-10-02T05:00:00Z"
        for item in rows
    )
