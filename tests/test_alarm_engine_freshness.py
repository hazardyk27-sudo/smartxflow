from __future__ import annotations

import alarm_engine


class _FakeCalculator:
    def __init__(self, result=3):
        self.result = result
        self._active_signal = None
        self.run_calls = 0

    def run_all_calculations(self):
        self.run_calls += 1
        return self.result


def test_stale_signal_is_processed_without_calculation(monkeypatch):
    events = []
    calculator_calls = []

    monkeypatch.setattr(
        alarm_engine,
        "_signal_queue_wait_seconds",
        lambda signal: alarm_engine.MAX_SIGNAL_AGE_SECONDS + 1,
    )
    monkeypatch.setattr(
        alarm_engine,
        "mark_signal_processed",
        lambda signal_id: events.append(("processed", signal_id)) or True,
    )
    monkeypatch.setattr(
        alarm_engine,
        "update_engine_heartbeat",
        lambda status, alarm_count=0, error_msg=None: events.append(
            ("heartbeat", status, alarm_count, error_msg)
        ) or True,
    )
    monkeypatch.setattr(
        alarm_engine,
        "get_calculator",
        lambda: calculator_calls.append(True),
    )

    signal = {
        "id": 101,
        "source": "replit",
        "signal_type": "scrape_complete",
        "created_at": "2026-10-05T00:00:00+00:00",
        "match_count": 500,
    }

    assert alarm_engine.process_signal(signal) is True
    assert calculator_calls == []
    assert ("processed", 101) in events
    stale_events = [event for event in events if event[:2] == ("heartbeat", "stale_input")]
    assert len(stale_events) == 1
    assert "calculation skipped" in stale_events[0][3]


def test_invalid_signal_timestamp_is_processed_without_calculation(monkeypatch):
    events = []

    monkeypatch.setattr(alarm_engine, "_signal_queue_wait_seconds", lambda signal: None)
    monkeypatch.setattr(
        alarm_engine,
        "mark_signal_processed",
        lambda signal_id: events.append(("processed", signal_id)) or True,
    )
    monkeypatch.setattr(
        alarm_engine,
        "update_engine_heartbeat",
        lambda status, alarm_count=0, error_msg=None: events.append(
            ("heartbeat", status, alarm_count, error_msg)
        ) or True,
    )
    monkeypatch.setattr(
        alarm_engine,
        "get_calculator",
        lambda: (_ for _ in ()).throw(AssertionError("calculator must not run")),
    )

    signal = {
        "id": 102,
        "source": "replit",
        "signal_type": "scrape_complete",
        "created_at": "not-a-time",
    }

    assert alarm_engine.process_signal(signal) is True
    assert ("processed", 102) in events
    stale_events = [event for event in events if event[:2] == ("heartbeat", "stale_input")]
    assert len(stale_events) == 1
    assert "created_at invalid" in stale_events[0][3]


def test_fresh_signal_runs_incremental_calculation(monkeypatch):
    events = []
    fake = _FakeCalculator(result=4)

    monkeypatch.setattr(alarm_engine, "_signal_queue_wait_seconds", lambda signal: 45.0)
    monkeypatch.setattr(alarm_engine, "get_calculator", lambda: fake)
    monkeypatch.setattr(
        alarm_engine,
        "mark_signal_processed",
        lambda signal_id: events.append(("processed", signal_id)) or True,
    )
    monkeypatch.setattr(
        alarm_engine,
        "update_engine_heartbeat",
        lambda status, alarm_count=0, error_msg=None: events.append(
            ("heartbeat", status, alarm_count, error_msg)
        ) or True,
    )
    monkeypatch.setattr(alarm_engine, "clear_recent_alarm_cache", lambda calc: None)

    signal = {
        "id": 103,
        "source": "replit",
        "signal_type": "scrape_complete",
        "created_at": "2026-10-05T01:00:00+00:00",
        "match_count": 600,
    }

    assert alarm_engine.process_signal(signal) is True
    assert fake.run_calls == 1
    assert fake._active_signal is signal
    assert ("processed", 103) in events
    assert ("heartbeat", "calculating", 0, None) in events
    assert ("heartbeat", "idle", 4, None) in events
    assert not any(event[:2] == ("heartbeat", "stale_input") for event in events)


def test_stale_signal_mark_failure_returns_false(monkeypatch):
    events = []

    monkeypatch.setattr(
        alarm_engine,
        "_signal_queue_wait_seconds",
        lambda signal: alarm_engine.MAX_SIGNAL_AGE_SECONDS + 300,
    )
    monkeypatch.setattr(alarm_engine, "mark_signal_processed", lambda signal_id: False)
    monkeypatch.setattr(
        alarm_engine,
        "update_engine_heartbeat",
        lambda status, alarm_count=0, error_msg=None: events.append(
            ("heartbeat", status, alarm_count, error_msg)
        ) or True,
    )

    signal = {
        "id": 104,
        "source": "replit",
        "signal_type": "scrape_complete",
        "created_at": "2026-10-05T00:00:00+00:00",
    }

    assert alarm_engine.process_signal(signal) is False
    error_events = [event for event in events if event[:2] == ("heartbeat", "error")]
    assert len(error_events) == 1
    assert "mark processed failed" in error_events[0][3]
