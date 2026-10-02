from copy import deepcopy

import pytest

from analysis_v2.signal_store import (
    SignalStore,
    build_state_event,
    build_trigger_event,
    is_transition_allowed,
    make_signal_id,
)


BASE_TRIGGER = {
    "engine_key": "confirmed_money",
    "engine_version": "2.0.0",
    "match_id_hash": "a1b2c3d4e5f6",
    "home_team": "Home FC",
    "away_team": "Away FC",
    "league": "League",
    "kickoff_utc": "2026-10-02T18:00:00Z",
    "market_key": "1X2",
    "selection_code": "1",
    "recommended_market": "1X2",
    "recommended_selection": "1",
    "trigger_at": "2026-10-02T12:34:56Z",
    "opening_odds": "2.00",
    "odds_6h": "1.96",
    "odds_2h": "1.88",
    "odds_30m": "1.84",
    "trigger_odds": "1.82",
    "pct_6h": "80.0",
    "pct_2h": "84.0",
    "trigger_pct": "86.5%",
    "amount_6h": "£ 6,000",
    "amount_2h": "£ 8,000",
    "trigger_amount": "£ 8,500",
    "trigger_volume": "£ 10,000",
    "money_added_6h": "£ 2,500",
    "money_added_2h": "£ 500",
    "hours_before_kickoff": 5.4,
    "engine_reason": {"kind": "price_confirmed_money"},
    "features": {"price_confirmed": True},
    "config_snapshot": {"min_pct": 80, "min_price_drop_pct": 5},
}


class _Response:
    def __init__(self, status_code=200, rows=None):
        self.status_code = status_code
        self._rows = [] if rows is None else rows
        self.text = "" if status_code == 204 else "json"

    def json(self):
        return deepcopy(self._rows)


class _MemorySession:
    def __init__(self):
        self.tables = {
            "analysis_v2_signal_events": [],
            "analysis_v2_signal_state_events": [],
            "analysis_v2_signal_settlements": [],
        }
        self.patch_calls = 0
        self.delete_calls = 0

    @staticmethod
    def _table(url):
        return url.split("/rest/v1/", 1)[1].split("?", 1)[0]

    @staticmethod
    def _matches(row, params):
        for key, value in (params or {}).items():
            if key in {"select", "order", "limit", "on_conflict"}:
                continue
            if isinstance(value, str) and value.startswith("eq."):
                expected = value[3:]
                if str(row.get(key)) != expected:
                    return False
        return True

    def get(self, url, **kwargs):
        table = self._table(url)
        rows = [
            deepcopy(row)
            for row in self.tables.get(table, [])
            if self._matches(row, kwargs.get("params"))
        ]
        order = (kwargs.get("params") or {}).get("order")
        if order:
            first = order.split(",", 1)[0]
            field, direction = first.split(".", 1)
            rows.sort(
                key=lambda row: (row.get(field) is not None, row.get(field)),
                reverse=direction == "desc",
            )
        limit = (kwargs.get("params") or {}).get("limit")
        if limit is not None:
            rows = rows[: int(limit)]
        return _Response(200, rows)

    def post(self, url, **kwargs):
        table = self._table(url)
        record = deepcopy(kwargs["json"][0])
        conflict = (kwargs.get("params") or {}).get("on_conflict")
        rows = self.tables.setdefault(table, [])
        if conflict and any(
            str(row.get(conflict)) == str(record.get(conflict)) for row in rows
        ):
            return _Response(201, [])
        record.setdefault("id", len(rows) + 1)
        rows.append(record)
        return _Response(201, [record])

    def patch(self, *args, **kwargs):
        self.patch_calls += 1
        raise AssertionError("V2 immutable store must never PATCH")

    def delete(self, *args, **kwargs):
        self.delete_calls += 1
        raise AssertionError("V2 immutable store must never DELETE")


def _store():
    session = _MemorySession()
    return SignalStore(
        "https://example.supabase.co",
        "service-key",
        session=session,
    ), session


def test_signal_identity_does_not_include_trigger_time():
    a = make_signal_id(
        "confirmed_money",
        "2.0.0",
        "a1b2c3d4e5f6",
        "1X2",
        "1",
    )
    later = dict(BASE_TRIGGER, trigger_at="2026-10-02T12:40:00Z")
    b = build_trigger_event(later)["signal_id"]
    assert a == b


def test_same_logical_signal_is_inserted_once_and_first_snapshot_wins():
    store, session = _store()

    first = store.create_signal_once(BASE_TRIGGER)
    retry = dict(
        BASE_TRIGGER,
        trigger_at="2026-10-02T12:45:00Z",
        trigger_odds="1.70",
        trigger_pct="93.0",
        trigger_amount="£ 12,000",
    )
    second = store.create_signal_once(retry)

    assert first["signal_id"] == second["signal_id"]
    assert len(session.tables["analysis_v2_signal_events"]) == 1
    assert second["trigger_at"] == "2026-10-02T12:34:56+00:00"
    assert second["trigger_odds"] == 1.82
    assert second["trigger_pct"] == 86.5
    assert second["trigger_amount"] == 8500.0
    assert len(session.tables["analysis_v2_signal_state_events"]) == 1


def test_state_change_never_mutates_trigger_snapshot():
    store, session = _store()
    trigger = store.create_signal_once(BASE_TRIGGER)
    before = deepcopy(store.get_signal(trigger["signal_id"]))

    store.append_state(
        build_state_event(
            trigger["signal_id"],
            "WEAKENED",
            "2026-10-02T13:00:00Z",
            current_odds=1.93,
            current_pct=78.0,
            current_amount=9100,
            current_volume=11700,
            reason_code="PRICE_REOPENED",
            reason={"odds_direction": "up"},
        )
    )

    after = store.get_signal(trigger["signal_id"])
    assert after == before
    assert after["trigger_odds"] == 1.82
    assert after["trigger_pct"] == 86.5
    assert after["trigger_amount"] == 8500.0
    assert after["trigger_volume"] == 10000.0
    assert len(session.tables["analysis_v2_signal_events"]) == 1


def test_invalidation_is_append_only_and_signal_survives():
    store, session = _store()
    trigger = store.create_signal_once(BASE_TRIGGER)

    store.append_state(
        build_state_event(
            trigger["signal_id"],
            "INVALIDATED",
            "2026-10-02T13:05:00Z",
            reason_code="PRICE_DIVERGED",
        )
    )

    assert store.get_signal(trigger["signal_id"]) is not None
    assert len(session.tables["analysis_v2_signal_events"]) == 1
    assert store.get_latest_state(trigger["signal_id"])["state"] == "INVALIDATED"
    assert session.patch_calls == 0
    assert session.delete_calls == 0


def test_invalidated_signal_cannot_be_resurrected():
    assert is_transition_allowed("INVALIDATED", "SETTLED")
    assert not is_transition_allowed("INVALIDATED", "ACTIVE")
    assert not is_transition_allowed("INVALIDATED", "CONFIRMED")


def test_settlement_rejects_non_exact_match_hash():
    store, session = _store()
    trigger = store.create_signal_once(BASE_TRIGGER)

    with pytest.raises(ValueError, match="exact match_id_hash"):
        store.settle_signal(
            signal_id=trigger["signal_id"],
            match_id_hash="ffffffffffff",
            final_home_score=2,
            final_away_score=0,
            outcome="WIN",
            settled_at="2026-10-02T20:00:00Z",
            pnl_units=0.82,
        )

    assert session.tables["analysis_v2_signal_settlements"] == []


def test_second_settlement_is_idempotent_and_not_duplicated():
    store, session = _store()
    trigger = store.create_signal_once(BASE_TRIGGER)

    first = store.settle_signal(
        signal_id=trigger["signal_id"],
        match_id_hash=trigger["match_id_hash"],
        final_home_score=2,
        final_away_score=0,
        outcome="WIN",
        settled_at="2026-10-02T20:00:00Z",
        pnl_units=0.82,
    )
    second = store.settle_signal(
        signal_id=trigger["signal_id"],
        match_id_hash=trigger["match_id_hash"],
        final_home_score=9,
        final_away_score=9,
        outcome="LOSS",
        settled_at="2026-10-02T21:00:00Z",
        pnl_units=-1.0,
    )

    assert second == first
    assert len(session.tables["analysis_v2_signal_settlements"]) == 1
    assert first["entry_odds"] == trigger["trigger_odds"]
    assert first["engine_version"] == trigger["engine_version"]


def test_engine_config_and_feature_snapshot_are_persisted():
    event = build_trigger_event(BASE_TRIGGER)
    assert event["engine_version"] == "2.0.0"
    assert event["engine_reason"] == {"kind": "price_confirmed_money"}
    assert event["features"] == {"price_confirmed": True}
    assert event["config_snapshot"] == {
        "min_pct": 80,
        "min_price_drop_pct": 5,
    }


def test_legacy_boundary_keys_map_to_canonical_snapshot():
    payload = dict(BASE_TRIGGER)
    payload.pop("trigger_at")
    payload.pop("features")
    payload.pop("config_snapshot")
    payload["triggered_at"] = "2026-10-02T12:34:56Z"
    payload["evidence"] = {"legacy": True}
    payload["engine_params"] = {"threshold": 5}

    event = build_trigger_event(payload)
    assert event["trigger_at"] == "2026-10-02T12:34:56+00:00"
    assert event["features"] == {"legacy": True}
    assert event["config_snapshot"] == {"threshold": 5}


def test_recommended_odds_are_part_of_immutable_trigger_snapshot():
    payload = dict(
        BASE_TRIGGER,
        recommended_market="DC",
        recommended_selection="1X",
        recommended_odds="1.44",
    )
    event = build_trigger_event(payload)
    assert event["trigger_odds"] == 1.82
    assert event["recommended_odds"] == 1.44


def test_store_settlement_uses_recommended_odds_when_market_changed():
    store, session = _store()
    trigger = store.create_signal_once(
        dict(
            BASE_TRIGGER,
            recommended_market="DC",
            recommended_selection="1X",
            recommended_odds=1.44,
        )
    )

    settled = store.settle_signal(
        signal_id=trigger["signal_id"],
        match_id_hash=trigger["match_id_hash"],
        final_home_score=1,
        final_away_score=1,
        outcome="WIN",
        settled_at="2026-10-02T20:00:00Z",
        pnl_units=0.44,
    )

    assert settled["entry_odds"] == 1.44
    assert len(session.tables["analysis_v2_signal_settlements"]) == 1
