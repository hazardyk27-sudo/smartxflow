import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from services import polymarket_client


class PolymarketMatchDiscoveryPatchTests(unittest.TestCase):
    def test_discovery_uses_bounded_keyset_pages_without_unbounded_helpers(self):
        future = (
            datetime.now(timezone.utc) + timedelta(hours=2)
        ).isoformat().replace("+00:00", "Z")
        calls = []

        def fake_get_json(url, params=None):
            calls.append(dict(params or {}))
            return {
                "events": [{
                    "id": "evt-1",
                    "slug": "ars-che-2026-10-10",
                    "title": "Arsenal vs. Chelsea",
                    "endDate": future,
                }],
                "next_cursor": None,
            }

        with patch.object(polymarket_client, "_get_json", side_effect=fake_get_json), \
             patch.object(polymarket_client, "_fetch_soccer_events", side_effect=AssertionError("unbounded active fetch used")), \
             patch.object(polymarket_client, "_fetch_closed_soccer_events", side_effect=AssertionError("unbounded closed fetch used")):
            matches = polymarket_client.get_all_active_matches(hours_ahead=168)

        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]["event_id"], "evt-1")
        self.assertEqual(len(calls), 2)
        for params in calls:
            self.assertIn("end_date_min", params)
            self.assertIn("end_date_max", params)
            self.assertEqual(params["limit"], 100)

    def test_discovery_deduplicates_active_and_closed_event_identity(self):
        future = (
            datetime.now(timezone.utc) + timedelta(hours=1)
        ).isoformat().replace("+00:00", "Z")

        with patch.object(
            polymarket_client,
            "_get_json",
            return_value={
                "events": [{
                    "id": "same-event",
                    "slug": "ars-che-2026-10-10",
                    "title": "Arsenal vs. Chelsea",
                    "endDate": future,
                }],
                "next_cursor": None,
            },
        ):
            matches = polymarket_client.get_all_active_matches(hours_ahead=168)

        self.assertEqual([row["event_id"] for row in matches], ["same-event"])


if __name__ == "__main__":
    unittest.main()
