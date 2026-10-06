from __future__ import annotations

import unittest
from unittest.mock import patch

import sinyal_engine as se


class _Response:
    status_code = 200
    text = "[]"

    @staticmethod
    def json():
        return []


class SignalCooldownTimestampEncodingTests(unittest.TestCase):
    def _assert_safe_timestamp_url(self, func):
        seen = []

        def fake_get(url, **_kwargs):
            seen.append(url)
            return _Response()

        with patch.object(se.requests, "get", side_effect=fake_get):
            result = func()

        self.assertEqual(result, set())
        self.assertEqual(len(seen), 1)
        self.assertIn("created_at=gte.", seen[0])
        self.assertIn("Z", seen[0])
        self.assertNotIn("+00:00", seen[0])
        self.assertNotIn(" 00:00", seen[0])

    def test_confirmed_money_cooldown_uses_url_safe_utc(self):
        self._assert_safe_timestamp_url(se.fetch_cm_recent_cooldowns)

    def test_confirmed_money_v2_cooldown_uses_url_safe_utc(self):
        self._assert_safe_timestamp_url(se.fetch_cm_v2_recent_cooldowns)

    def test_fake_sharp_cooldown_uses_url_safe_utc(self):
        self._assert_safe_timestamp_url(se.fetch_fs_cooldown)


if __name__ == "__main__":
    unittest.main()
