import json
import unittest
from unittest.mock import patch

import polymarket_scraper
from services import polymarket_client


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload
        self.text = json.dumps(payload or {})

    def json(self):
        return self._payload


class TrackedWalletStatsTests(unittest.TestCase):
    def test_profile_uses_persisted_stats_shared_with_tracked_list(self):
        wallet = "0xwallet"
        persisted = {
            "wallet": wallet,
            "nickname": "Tracked bettor",
            "notes": None,
            "created_at": "2026-09-08T00:00:00+00:00",
            "last_synced_at": "2026-09-12T00:00:00+00:00",
            "win_rate": 69.2,
            "resolved_won": 9,
            "resolved_lost": 4,
            "resolved_total": 13,
            "trade_count": 42,
            "total_invested_usdc": 42000.0,
            "avg_bet_size_usdc": 1000.0,
            "avg_price": 0.5,
            "avg_price_decimal": 2.0,
            "open_position_count": 1,
            "open_exposure_usdc": 1234.5,
        }
        activity = [{
            "wallet": wallet,
            "transaction_hash": "tx",
            "asset": "open-asset",
            "condition_id": "open-condition",
            "result": None,
            "title": "Open market",
            "slug": "open-market",
            "market_type": "moneyline",
            "selection": "Yes",
            "side": "BUY",
            "action": "buy",
            "outcome_raw": "Yes",
            "amount_usdc": 1000.0,
            "price": 0.5,
            "size": 2000.0,
            "traded_at": "2026-09-10T00:00:00+00:00",
        }]
        positions = [{
            "condition_id": "open-condition",
            "asset": "open-asset",
            "title": "Open market",
            "slug": "open-market",
            "outcome": "Yes",
            "size": 2000.0,
            "avg_price": 0.5,
            "cur_price": 0.5,
            "initial_value": 1000.0,
            "current_value": 1234.5,
            "cash_pnl": 234.5,
            "percent_pnl": 23.45,
            "redeemable": False,
            "end_date": "2026-09-20T00:00:00+00:00",
        }]

        def fake_get(url, **_kwargs):
            if "tracked_wallets" in url:
                return FakeResponse(200, [persisted])
            if "tracked_wallet_activity" in url:
                return FakeResponse(200, activity)
            if "tracked_wallet_positions" in url:
                return FakeResponse(200, positions)
            if "tracked_wallet_redeems" in url:
                return FakeResponse(200, [])
            raise AssertionError(url)

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://supabase.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "test"}), \
             patch.object(polymarket_client.requests, "get", side_effect=fake_get):
            profile = polymarket_client.get_wallet_profile(wallet)

        self.assertIsNotNone(profile)
        stats = profile["stats"]
        # The live rows intentionally describe only one open fill. The profile
        # must still expose the same persisted snapshot used by the list card.
        self.assertEqual(stats["trade_count"], 42)
        self.assertEqual(stats["resolved_won"], 9)
        self.assertEqual(stats["resolved_lost"], 4)
        self.assertEqual(stats["resolved_total"], 13)
        self.assertEqual(stats["win_rate_pct"], 69.2)
        self.assertEqual(stats["open_position_count"], 1)
        self.assertEqual(stats["open_exposure_usdc"], 1234.5)

    def test_tracked_wallet_threshold_is_applied_before_market_grouping(self):
        activity = [
            {
                "asset": "hidden-below-threshold",
                "condition_id": "hidden-condition",
                "result": "won",
                "amount_usdc": 999.99,
                "price": 0.5,
            },
            {
                "asset": "exact-threshold",
                "condition_id": "exact-condition",
                "result": "lost",
                "amount_usdc": 1000,
                "price": 0.4,
            },
            {
                "asset": "grouped-winner",
                "condition_id": "grouped-condition",
                "result": "won",
                "amount_usdc": 1000.01,
                "price": 0.6,
            },
            {
                "asset": "grouped-winner",
                "condition_id": "grouped-condition",
                "result": "won",
                "amount_usdc": 1500,
                "price": 0.7,
            },
            {
                "asset": "two-small-fills",
                "condition_id": "small-group",
                "result": "won",
                "amount_usdc": 600,
                "price": 0.8,
            },
            {
                "asset": "two-small-fills",
                "condition_id": "small-group",
                "result": "won",
                "amount_usdc": 600,
                "price": 0.8,
            },
        ]

        filtered = polymarket_client._filter_tracked_wallet_activity_amount(activity)
        stats = polymarket_client._compute_wallet_activity_stats(filtered, [], [])

        self.assertEqual(len(filtered), 3)
        self.assertEqual(stats["trade_count"], 3)
        self.assertEqual(stats["total_invested_usdc"], 3500.01)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 1)
        self.assertEqual(stats["resolved_total"], 2)
        self.assertEqual(stats["win_rate"], 50.0)
        self.assertEqual(polymarket_client.MIN_TRADE_AMOUNT_USDC, 100.0)

    def test_summary_filters_tracking_boundary_and_groups_fills_by_market(self):
        activity = [
            {
                "asset": "winner",
                "condition_id": "condition-1",
                "result": "won",
                "amount_usdc": 10,
                "price": 0.5,
                "traded_at": "2026-09-10T00:00:00+00:00",
            },
            {
                "asset": "winner",
                "condition_id": "condition-1",
                "result": "won",
                "amount_usdc": 20,
                "price": 0.6,
                "traded_at": "2026-09-10T00:01:00+00:00",
            },
            {
                "asset": "loser",
                "condition_id": "condition-2",
                "result": "lost",
                "amount_usdc": 5,
                "price": 0.2,
                "traded_at": "2026-09-11T00:00:00+00:00",
            },
            {
                "asset": "old",
                "condition_id": "condition-old",
                "result": "won",
                "amount_usdc": 99,
                "price": 0.9,
                "traded_at": "2026-09-01T00:00:00+00:00",
            },
        ]

        filtered = polymarket_client._filter_wallet_rows_since(
            activity,
            "2026-09-10T00:00:00+00:00",
        )
        stats = polymarket_client._compute_wallet_activity_stats(filtered, [], [])

        self.assertEqual(stats["trade_count"], 3)
        self.assertEqual(stats["total_invested_usdc"], 35)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 1)
        self.assertEqual(stats["resolved_total"], 2)
        self.assertEqual(stats["win_rate"], 50.0)

    def test_open_position_is_not_counted_as_resolved_market(self):
        activity = [
            {
                "asset": "open-asset",
                "condition_id": "open-condition",
                "result": None,
                "amount_usdc": 12,
                "price": 0.4,
            },
            {
                "asset": "won-asset",
                "condition_id": "won-condition",
                "result": "won",
                "amount_usdc": 8,
                "price": 0.7,
            },
        ]
        positions = [
            {
                "asset": "open-asset",
                "condition_id": "open-condition",
                "cur_price": 0.4,
                "current_value": 12,
                "redeemable": False,
            },
        ]

        stats = polymarket_client._compute_wallet_activity_stats(activity, positions, [])

        self.assertEqual(stats["trade_count"], 2)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 0)
        self.assertEqual(len(stats["open_positions"]), 1)
        self.assertEqual(stats["open_exposure"], 12)

    def test_stats_refresh_keeps_activity_when_positions_query_fails(self):
        wallet = "0xwallet"
        activity = [
            {"asset": "winner", "condition_id": "condition-1", "result": "won", "amount_usdc": 1000, "price": 0.5},
            {"asset": "loser", "condition_id": "condition-2", "result": "lost", "amount_usdc": 2000, "price": 0.25},
        ]
        patches = []

        def fake_get(url, **_kwargs):
            if "tracked_wallet_positions" in url:
                return FakeResponse(503, {"error": "temporary"})
            if "tracked_wallet_redeems" in url:
                return FakeResponse(200, [])
            if "tracked_wallet_activity" in url:
                return FakeResponse(200, activity)
            raise AssertionError(url)

        def fake_patch(url, **kwargs):
            if "tracked_wallet_activity" in url:
                return FakeResponse(204, [])
            if "tracked_wallets" in url:
                patches.append(kwargs["json"])
                return FakeResponse(204, [])
            raise AssertionError(url)

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://supabase.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "test"}), \
             patch.object(polymarket_client, "_fetch_market_resolution", return_value=None), \
             patch.object(polymarket_client.requests, "get", side_effect=fake_get), \
             patch.object(polymarket_client.requests, "patch", side_effect=fake_patch):
            self.assertTrue(polymarket_client.compute_and_save_wallet_stats(wallet))

        self.assertEqual(patches[0]["win_rate"], 50.0)
        self.assertEqual(patches[0]["resolved_won"], 1)
        self.assertEqual(patches[0]["resolved_lost"], 1)
        self.assertEqual(patches[0]["resolved_total"], 2)
        self.assertEqual(patches[0]["trade_count"], 2)
        self.assertEqual(patches[0]["avg_price"], 0.3333)
        self.assertEqual(patches[0]["avg_price_decimal"], 3.0)
        self.assertNotIn("open_position_count", patches[0])
        self.assertNotIn("open_exposure_usdc", patches[0])

    def test_stats_refresh_does_not_write_zeroes_when_activity_query_fails(self):
        patches = []

        def fake_get(url, **_kwargs):
            if "tracked_wallet_activity" in url:
                return FakeResponse(503, {"error": "temporary"})
            return FakeResponse(200, [])

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://supabase.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "test"}), \
             patch.object(polymarket_client.requests, "get", side_effect=fake_get), \
             patch.object(
                 polymarket_client.requests,
                 "patch",
                 side_effect=lambda _url, **kwargs: patches.append(kwargs) or FakeResponse(204, []),
             ):
            self.assertFalse(polymarket_client.compute_and_save_wallet_stats("0xwallet"))

        self.assertEqual(patches, [])

    def test_scraper_computes_stats_when_positions_api_fails(self):
        class FakeWriter:
            def __init__(self):
                self.positions_replaced = False

            def get_wallet_activity_checkpoint(self, _wallet):
                return None

            def get_wallet_redeem_checkpoint(self, _wallet):
                return None

            def replace_wallet_positions(self, _wallet, _rows):
                self.positions_replaced = True

        writer = FakeWriter()
        computed = []

        with patch.object(polymarket_scraper, "fetch_wallet_activity", return_value=([], False)), \
             patch.object(polymarket_scraper, "fetch_wallet_redeems", return_value=([], False)), \
             patch.object(polymarket_scraper, "fetch_wallet_positions", return_value=([], False)), \
             patch.object(
                 polymarket_scraper,
                 "compute_and_save_wallet_stats",
                 side_effect=lambda wallet: computed.append(wallet) or True,
             ):
            polymarket_scraper.process_tracked_wallet(
                writer,
                {"wallet": "0xwallet", "nickname": "new wallet"},
            )

        self.assertEqual(computed, ["0xwallet"])
        self.assertFalse(writer.positions_replaced)


if __name__ == "__main__":
    unittest.main()