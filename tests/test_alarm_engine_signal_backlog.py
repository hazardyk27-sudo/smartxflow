import importlib
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "anon-test-key")
os.environ.setdefault("SUPABASE_SERVICE_ROLE_KEY", "service-test-key")

import alarm_engine  # noqa: E402  (import after env vars are set)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=""):
        self.status_code = status_code
        self._payload = payload if payload is not None else []
        self.text = text or str(self._payload)
        self.headers = {}

    def json(self):
        return self._payload


class SignalBacklogTests(unittest.TestCase):
    """Regression test for the 2026-09-11 alarm engine OOM crash-loop.

    Root cause: the engine processed a 700+ signal backlog oldest-first, one
    full run_all_calculations() per stale signal, even though calculations
    always read live DB state and gain nothing from replaying old signals.
    Fix: always fetch the newest unprocessed signal and bulk-skip the rest.
    """

    def test_check_unprocessed_signals_orders_newest_first(self):
        captured = {}

        def fake_get(url, headers, timeout):
            captured["url"] = url
            return FakeResponse(200, [{"id": 39376, "created_at": "2026-09-11T10:08:02+00:00"}])

        with patch.object(alarm_engine.requests, "get", side_effect=fake_get):
            signal = alarm_engine.check_unprocessed_signals()

        self.assertIn("order=created_at.desc", captured["url"])
        self.assertEqual(signal["id"], 39376)

    def test_skip_stale_signals_marks_older_rows_processed_without_calculating(self):
        captured = {}

        def fake_patch(url, json, headers, timeout):
            captured["url"] = url
            captured["json"] = json
            # Simulate PostgREST returning the 700 rows it just updated.
            return FakeResponse(200, [{"id": i} for i in range(700)])

        with patch.object(alarm_engine.requests, "patch", side_effect=fake_patch):
            skipped = alarm_engine.skip_stale_signals(39376)

        self.assertEqual(skipped, 700)
        self.assertIn("id=lt.39376", captured["url"])
        self.assertIn("processed=eq.false", captured["url"])
        self.assertTrue(captured["json"]["processed"])

    def test_skip_stale_signals_is_a_noop_when_nothing_is_stale(self):
        def fake_patch(url, json, headers, timeout):
            return FakeResponse(200, [])

        with patch.object(alarm_engine.requests, "patch", side_effect=fake_patch):
            skipped = alarm_engine.skip_stale_signals(1)

        self.assertEqual(skipped, 0)

    def test_skip_stale_signals_handles_http_error_gracefully(self):
        def fake_patch(url, json, headers, timeout):
            return FakeResponse(500, text="server error")

        with patch.object(alarm_engine.requests, "patch", side_effect=fake_patch):
            skipped = alarm_engine.skip_stale_signals(5)

        self.assertEqual(skipped, 0)


if __name__ == "__main__":
    unittest.main()
