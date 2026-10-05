from __future__ import annotations

import alarm_recent


class _FakeCalculator:
    def __init__(self, active_signal=None):
        self._active_signal = active_signal
        self.queries = []

    def _get(self, table, query):
        self.queries.append((table, query))
        return [{"id": 9, "created_at": "2026-10-05T11:55:00Z", "source": "replit"}]


def test_previous_signal_lookup_filters_scrape_complete():
    calc = _FakeCalculator()
    signal = {
        "id": 10,
        "source": "replit",
        "created_at": "2026-10-05T12:00:00Z",
    }

    rows = alarm_recent._load_previous_scrape_complete_signals(calc, signal, count=5)

    assert len(rows) == 1
    assert len(calc.queries) == 1
    table, query = calc.queries[0]
    assert table == "scraper_signal"
    assert "id=lt.10" in query
    assert "source=eq.replit" in query
    assert "signal_type=eq.scrape_complete" in query
    assert "limit=5" in query


def test_previous_signal_guard_is_installed_in_all_incremental_modules():
    assert alarm_recent._base._load_previous_signals is alarm_recent._load_previous_scrape_complete_signals
    assert alarm_recent._part2._load_previous_signals is alarm_recent._load_previous_scrape_complete_signals
    assert alarm_recent._part3._load_previous_signals is alarm_recent._load_previous_scrape_complete_signals


def test_fixture_guard_rejects_started_and_missing_kickoff(monkeypatch):
    signal = {
        "id": 10,
        "source": "replit",
        "created_at": "2026-10-05T12:00:00Z",
    }
    calc = _FakeCalculator(active_signal=signal)
    fixtures = {
        "future": {"kickoff_utc": "2026-10-05T12:01:00Z"},
        "equal": {"kickoff_utc": "2026-10-05T12:00:00Z"},
        "past": {"kickoff_utc": "2026-10-05T11:59:00Z"},
        "missing": {"kickoff_utc": None},
    }
    monkeypatch.setattr(alarm_recent, "_ORIGINAL_LOAD_FIXTURES", lambda calculator, hashes: fixtures)

    active = alarm_recent._load_active_prematch_fixtures(calc, fixtures.keys())

    assert set(active) == {"future"}


def test_fixture_guard_preserves_legacy_behavior_without_active_signal(monkeypatch):
    calc = _FakeCalculator(active_signal=None)
    fixtures = {
        "a": {"kickoff_utc": None},
        "b": {"kickoff_utc": "2020-01-01T00:00:00Z"},
    }
    monkeypatch.setattr(alarm_recent, "_ORIGINAL_LOAD_FIXTURES", lambda calculator, hashes: fixtures)

    result = alarm_recent._load_active_prematch_fixtures(calc, fixtures.keys())

    assert result == fixtures


def test_fixture_guard_fails_closed_on_invalid_active_signal_timestamp(monkeypatch):
    calc = _FakeCalculator(active_signal={"id": 10, "created_at": "bad-time"})
    fixtures = {"future": {"kickoff_utc": "2026-10-05T12:01:00Z"}}
    monkeypatch.setattr(alarm_recent, "_ORIGINAL_LOAD_FIXTURES", lambda calculator, hashes: fixtures)

    assert alarm_recent._load_active_prematch_fixtures(calc, fixtures.keys()) == {}
