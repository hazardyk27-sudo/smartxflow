import unittest
from unittest.mock import Mock, patch

from services import polymarket_client


class PolymarketVisibilityPatchTests(unittest.TestCase):
    def test_stored_rows_are_never_removed_by_sport_gate(self):
        rows = [
            {"asset": "football", "title": "Liverpool market"},
            {"asset": "nfl", "title": "NFL market"},
            {"asset": "unknown", "title": "Unknown market"},
        ]

        visible, complete = polymarket_client._filter_verified_football_items(rows)

        self.assertTrue(complete)
        self.assertEqual(visible, rows)

    def test_activity_returns_verified_uncertain_and_nonfootball_together(self):
        raw = [
            {"asset": "a", "timestamp": 30},
            {"asset": "b", "timestamp": 20},
            {"asset": "c", "timestamp": 10},
        ]

        def classify(rows):
            self.assertEqual(rows, raw)
            return {
                "verified_football": [raw[0]],
                "uncertain": [raw[1]],
                "verified_non_football": [raw[2]],
                "verification_complete": False,
            }

        with patch.object(polymarket_client, "_get_json", return_value=raw), \
             patch.object(polymarket_client, "_classify_football_items", side_effect=classify):
            visible, truncated, uncertain, nonfootball = polymarket_client.fetch_wallet_activity(
                "0xwallet",
                classification_details=True,
            )

        self.assertFalse(truncated)
        self.assertEqual([row["asset"] for row in visible], ["a", "b", "c"])
        self.assertEqual([row["asset"] for row in uncertain], ["b"])
        self.assertEqual([row["asset"] for row in nonfootball], ["c"])

    def test_uncertain_positions_do_not_turn_successful_api_read_into_failure(self):
        raw = [
            {"asset": "a", "currentValue": 100},
            {"asset": "b", "currentValue": 50},
        ]

        def classify(rows):
            return {
                "verified_football": [rows[0]],
                "uncertain": [rows[1]],
                "verified_non_football": [],
                "verification_complete": False,
            }

        with patch.object(polymarket_client, "_get_json", return_value=raw), \
             patch.object(polymarket_client, "_classify_football_items", side_effect=classify):
            visible, ok, uncertain, nonfootball = polymarket_client.fetch_wallet_positions(
                "0xwallet",
                classification_details=True,
            )

        self.assertTrue(ok)
        self.assertEqual({row["asset"] for row in visible}, {"a", "b"})
        self.assertEqual([row["asset"] for row in uncertain], ["b"])
        self.assertEqual(nonfootball, [])

    def test_persisted_profile_reader_has_no_sport_filter(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = []

        with patch.object(polymarket_client.requests, "get", return_value=response) as get:
            rows, ok = polymarket_client._fetch_persisted_wallet_bets_for_profile(
                "https://example.supabase.co",
                {"apikey": "test"},
                "0xwallet",
            )

        self.assertTrue(ok)
        self.assertEqual(rows, [])
        params = get.call_args.kwargs["params"]
        self.assertNotIn("sport_classification", params)

    def test_persisted_stats_reader_has_no_sport_filter(self):
        response = Mock()
        response.status_code = 200
        response.json.return_value = []

        with patch.object(polymarket_client.requests, "get", return_value=response) as get:
            rows, ok = polymarket_client._fetch_persisted_wallet_bets_for_stats(
                "https://example.supabase.co",
                {"apikey": "test"},
                "0xwallet",
            )

        self.assertTrue(ok)
        self.assertEqual(rows, [])
        params = get.call_args.kwargs["params"]
        self.assertNotIn("sport_classification", params)


if __name__ == "__main__":
    unittest.main()
