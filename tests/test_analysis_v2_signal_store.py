from datetime import datetime, timezone

from analysis_v2.signal_store import (
    SignalLedger,
    build_settlement_event,
    build_state_event,
    build_trigger_event,
    initial_state_for_trigger,
    is_transition_allowed,
    make_signal_uid,
)


BASE_TRIGGER = {
    "engine_key": "confirmed_money",
    "engine_version": "2.0.0",
    "match_id_hash": "a1b2c3d4e5f6",
    "home_team": "Home FC",
    "away_team": "Away",
    "league": "League",
    "kickoff_utc": "2026-10-02T18:00:00+00:00",
    "market_key": "1X2",
    "selection_code": "1",
    "selection_label": "Home",
    "triggered_at": "2026-10-02T12:34:56+00:00",
    "opening_odds": "2.00",
    "trigger_odds": "1.82",
    "trigger_pct": "86.5%",
    "trigger_amount": "£ 8,500",
    "trigger_volume": "£ 10,000",
    "evidence": {"price_confirmed": True},
}


def test_signal_uid_is_deterministic():
    a = make_signal_uid("confirmed_money", "2.0.0", "a1b2c3d4e5f6", "1X2", "1", "2026-10-02T12:34:56Z")
    b = make_signal_uid("confirmed_money", "2.0.0", "a1b2c3d4e5f6", "1X2", "1", "2026-10-02T12:34:56+00:00")
    assert a == b


def test_trigger_event_freezes_numeric_trigger_values():
    event = build_trigger_event(BASE_TRIGGER)
    assert event["match_id_hash"] == "a1b2c3d4e5f6"
    assert event["trigger_odds"] == 1.82
    assert event["trigger_pct"] == 86.5
    assert event["trigger_amount"] == 8500.0
    assert event["trigger_volume"] == 10000.0
    assert event["evidence"] == {"price_confirmed": True}


def test_trigger_rejects_noncanonical_match_identity():
    bad = dict(BASE_TRIGGER, match_id_hash="Home|Away")
    try:
        build_trigger_event(bad)
    except ValueError:
        pass
    else:
        raise AssertionError("noncanonical match hash must be rejected")


def test_initial_state_matches_trigger_snapshot():
    event = build_trigger_event(BASE_TRIGGER)
    state = initial_state_for_trigger(event)
    assert state["status"] == "ACTIVE"
    assert state["observed_at"] == event["triggered_at"]
    assert state["current_odds"] == event["trigger_odds"]
    assert state["current_pct"] == event["trigger_pct"]


def test_lifecycle_does_not_resurrect_invalidated_signal():
    assert is_transition_allowed(None, "ACTIVE")
    assert is_transition_allowed("ACTIVE", "WEAKENED")
    assert is_transition_allowed("WEAKENED", "ACTIVE")
    assert is_transition_allowed("ACTIVE", "INVALIDATED")
    assert not is_transition_allowed("INVALIDATED", "ACTIVE")
    assert is_transition_allowed("INVALIDATED", "SETTLED")
    assert not is_transition_allowed("SETTLED", "ACTIVE")


def test_settlement_requires_canonical_hash():
    try:
        build_settlement_event(
            signal_uid="sig_x",
            match_id_hash="wrong",
            settled_at="2026-10-02T20:00:00Z",
            home_score=1,
            away_score=0,
            selection_result="WIN",
        )
    except ValueError:
        pass
    else:
        raise AssertionError("settlement must reject noncanonical match hash")


class _Response:
    status_code = 201
    text = "[]"

    def json(self):
        return []


class _PostOnlySession:
    def __init__(self):
        self.calls = []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        return _Response()

    def patch(self, *args, **kwargs):
        raise AssertionError("immutable ledger must never PATCH")

    def delete(self, *args, **kwargs):
        raise AssertionError("immutable ledger must never DELETE")


def test_ledger_uses_only_append_posts_for_trigger_and_state():
    session = _PostOnlySession()
    ledger = SignalLedger("https://example.supabase.co", "service-key", session=session)
    event = ledger.append_trigger(BASE_TRIGGER)
    assert event["signal_uid"].startswith("sig_")
    assert len(session.calls) == 2
    assert "analysis_v2_signal_events" in session.calls[0][0]
    assert "analysis_v2_signal_state_events" in session.calls[1][0]


def test_state_uid_is_idempotent_for_same_observation():
    a = build_state_event(
        "sig_abc",
        "WEAKENED",
        datetime(2026, 10, 2, 13, 0, tzinfo=timezone.utc),
        current_odds=1.91,
        reason_code="PRICE_REOPENED",
    )
    b = build_state_event(
        "sig_abc",
        "WEAKENED",
        "2026-10-02T13:00:00+00:00",
        current_odds=1.95,
        reason_code="PRICE_REOPENED",
    )
    # UID identifies the lifecycle observation identity, while metrics can
    # still differ if a retry rebuilt the payload.
    assert a["state_uid"] == b["state_uid"]
