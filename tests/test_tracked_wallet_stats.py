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
            if "tracked_wallet_bets" in url:
                return FakeResponse(404, {"error": "migration pending"})
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

    def test_tracked_wallet_list_exposes_bet_count_alias(self):
        rows = [{
            "wallet": "0xwallet",
            "nickname": "A",
            "notes": None,
            "created_at": "2026-10-01T00:00:00+00:00",
            "win_rate": 50.0,
            "resolved_won": 1,
            "resolved_lost": 1,
            "resolved_total": 2,
            "trade_count": 7,
            "open_position_count": 0,
            "open_exposure_usdc": 0,
            "last_synced_at": "2026-10-02T12:00:00+00:00",
        }]

        with patch.object(
            polymarket_client.requests,
            "get",
            return_value=FakeResponse(200, rows),
        ), patch.object(
            polymarket_client,
            "_supabase_base_url",
            return_value="https://supabase.test",
        ), patch.object(
            polymarket_client,
            "_supabase_headers",
            return_value={"apikey": "test"},
        ):
            wallets = polymarket_client.list_tracked_wallets_with_stats()

        self.assertEqual(wallets[0]["bet_count"], 7)
        self.assertEqual(wallets[0]["trade_count"], 7)

    def test_profile_bet_reader_paginates_beyond_5000_without_truncation(self):
        page = [
            {
                "bet_key": f"bet-{i}",
                "stake_usdc": 1000,
                "last_traded_at": "2026-10-02T12:00:00+00:00",
            }
            for i in range(1000)
        ]
        calls = []

        def fake_get(_url, **kwargs):
            offset = kwargs["params"]["offset"]
            calls.append(offset)
            if offset < 5000:
                return FakeResponse(200, page)
            return FakeResponse(
                200,
                [{"bet_key": "bet-final", "stake_usdc": 1000}],
            )

        with patch.object(polymarket_client.requests, "get", side_effect=fake_get):
            rows, ok = polymarket_client._fetch_persisted_wallet_bets_for_profile(
                "https://supabase.test",
                {"apikey": "test"},
                "0xwallet",
            )

        self.assertTrue(ok)
        self.assertEqual(len(rows), 5001)
        self.assertEqual(calls, [0, 1000, 2000, 3000, 4000, 5000])

    def test_wallet_bet_api_contract_excludes_raw_execution_noise(self):
        row = {
            "bet_key": '["asset","0xwallet","france-yes"]',
            "asset": "france-yes",
            "condition_id": "condition",
            "event_id": "event",
            "match_name": "France - Spain",
            "market_type": "1x2",
            "market_label": "1X2",
            "selection_label": "France",
            "bet_label": "France",
            "lifecycle_status": "resolved",
            "status_label": "Kazandı",
            "result": "won",
            "stake_usdc": 1200,
            "avg_entry_price": 0.5,
            "avg_entry_decimal": 2.0,
            "closing_price": 0.6,
            "closing_decimal": 1.67,
            "clv_probability_pp": 10,
            "clv_pct": 20,
            "action": "BUY",
            "outcome_raw": "Yes",
        }

        bet = polymarket_client._wallet_bet_api_contract(row)

        self.assertEqual(bet["bet_id"], row["bet_key"])
        self.assertEqual(bet["match_name"], "France - Spain")
        self.assertEqual(bet["avg_entry_probability"], 0.5)
        self.assertEqual(bet["closing_probability"], 0.6)
        self.assertEqual(bet["clv_pct"], 20)
        self.assertNotIn("action", bet)
        self.assertNotIn("outcome_raw", bet)

    def test_wallet_profile_contract_validator_detects_core_invariants(self):
        stats = {"bet_count": 2}
        coverage = {"history_complete": True}
        bets = [
            {
                "bet_id": "same",
                "stake_usdc": 999,
                "result": "won",
                "lifecycle_status": "open",
                "avg_entry_probability": 0.5,
            },
            {
                "bet_id": "same",
                "stake_usdc": 1000,
                "result": "lost",
                "lifecycle_status": "resolved",
                "avg_entry_probability": 1.2,
            },
        ]

        quality = polymarket_client._validate_wallet_profile_contract(
            stats,
            bets,
            coverage,
        )

        codes = {issue["code"] for issue in quality["issues"]}
        self.assertEqual(quality["status"], "warning")
        self.assertIn("duplicate_bet_id", codes)
        self.assertIn("below_minimum_stake", codes)
        self.assertIn("resolved_state_mismatch", codes)
        self.assertIn("invalid_probability", codes)

    def test_profile_prefers_persisted_bets_without_raw_activity_reads(self):
        wallet = "0xwallet"
        persisted_wallet = {
            "wallet": wallet,
            "nickname": "Tracked bettor",
            "notes": None,
            "created_at": "2026-09-08T00:00:00+00:00",
            "last_synced_at": "2026-10-02T12:00:00+00:00",
            "win_rate": 100.0,
            "resolved_won": 1,
            "resolved_lost": 0,
            "resolved_total": 1,
            "trade_count": 1,
            "total_invested_usdc": 1000.0,
            "avg_bet_size_usdc": 1000.0,
            "avg_price": 0.5,
            "avg_price_decimal": 2.0,
            "open_position_count": 0,
            "open_exposure_usdc": 0,
        }
        persisted_bets = [{
            "bet_key": '["asset","0xwallet","france-yes"]',
            "asset": "france-yes",
            "condition_id": "france-market",
            "event_id": "99",
            "match_key": "event:99",
            "match_name": "France - Spain",
            "home": "France",
            "away": "Spain",
            "slug": "france-spain",
            "market_type": "1x2",
            "market_label": "1X2",
            "selection": "France",
            "selection_label": "France",
            "bet_label": "France",
            "lifecycle_status": "resolved",
            "result": "won",
            "status_label": "Kazandı",
            "stake_usdc": 1000.0,
            "sell_proceeds_usdc": 0.0,
            "redeem_proceeds_usdc": 2000.0,
            "avg_entry_price": 0.5,
            "avg_entry_decimal": 2.0,
            "pnl_usdc": 1000.0,
            "pnl_kind": "realized",
            "fill_count": 1,
            "buy_fill_count": 1,
            "sell_fill_count": 0,
            "first_traded_at": "2026-10-02T15:00:00+00:00",
            "last_traded_at": "2026-10-02T22:00:00+00:00",
        }]
        seen_urls = []

        def fake_get(url, **_kwargs):
            seen_urls.append(url)
            if "tracked_wallet_bets" in url:
                return FakeResponse(200, persisted_bets)
            if "tracked_wallets" in url:
                return FakeResponse(200, [persisted_wallet])
            if "tracked_wallet_positions" in url:
                return FakeResponse(200, [])
            if "tracked_wallet_activity" in url or "tracked_wallet_redeems" in url:
                raise AssertionError("raw ledger should not be read on persisted fast path")
            raise AssertionError(url)

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://supabase.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "test"}), \
             patch.object(polymarket_client.requests, "get", side_effect=fake_get):
            profile = polymarket_client.get_wallet_profile(wallet)

        self.assertIsNotNone(profile)
        self.assertEqual(len(profile["activity"]), 1)
        row = profile["activity"][0]
        self.assertEqual(row["match"], "France - Spain")
        self.assertEqual(row["amount_usdc"], 1000.0)
        self.assertEqual(row["price"], 2.0)
        self.assertEqual(row["status_label"], "Kazandı")
        self.assertEqual(profile["stats"]["realized_pnl_usdc"], 1000.0)
        self.assertEqual(profile["stats"]["total_redeemed_usdc"], 2000.0)
        self.assertEqual(
            profile["contract_version"],
            polymarket_client.TRACKED_WALLET_API_CONTRACT_VERSION,
        )
        self.assertEqual(profile["stats"]["bet_count"], 1)
        self.assertEqual(len(profile["bets"]), 1)
        self.assertEqual(
            profile["bets"][0]["bet_id"],
            persisted_bets[0]["bet_key"],
        )
        self.assertEqual(
            profile["coverage"]["history_source"],
            "tracked_wallet_bets",
        )
        self.assertTrue(profile["coverage"]["history_complete"])
        self.assertEqual(profile["quality"]["status"], "ok")
        self.assertFalse(any("tracked_wallet_activity" in url for url in seen_urls))
        self.assertFalse(any("tracked_wallet_redeems" in url for url in seen_urls))

    def test_tracked_wallet_threshold_is_applied_after_position_grouping(self):
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

        self.assertEqual(len(filtered), 5)
        self.assertEqual(stats["trade_count"], 3)
        self.assertEqual(stats["fill_count"], 5)
        self.assertEqual(stats["total_invested_usdc"], 4700.01)
        self.assertEqual(stats["resolved_won"], 2)
        self.assertEqual(stats["resolved_lost"], 1)
        self.assertEqual(stats["resolved_total"], 3)
        self.assertEqual(stats["win_rate"], 66.7)
        self.assertEqual(polymarket_client.MIN_TRADE_AMOUNT_USDC, 100.0)
        self.assertEqual(polymarket_client.MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC, 1000.0)

    def test_two_600_buy_fills_combine_into_1200_qualifying_position(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 600,
                "price": 0.5,
                "size": 1200,
            },
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 600,
                "price": 0.5,
                "size": 1200,
            },
        ]

        filtered = polymarket_client._filter_tracked_wallet_activity_amount(activity)
        grouped = polymarket_client._group_activity_into_canonical_bets(filtered)
        stats = polymarket_client._compute_wallet_activity_stats(filtered, [], [])

        self.assertEqual(len(filtered), 2)
        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["stake_usdc"], 1200.0)
        self.assertEqual(stats["trade_count"], 1)
        self.assertEqual(stats["fill_count"], 2)
        self.assertEqual(stats["total_invested_usdc"], 1200.0)

    def test_tracked_wallet_position_threshold_is_inclusive(self):
        activity = [
            {
                "asset": "below",
                "condition_id": "below-condition",
                "action": "BUY",
                "amount_usdc": 999.99,
                "price": 0.5,
                "size": 1999.98,
            },
            {
                "asset": "exact",
                "condition_id": "exact-condition",
                "action": "BUY",
                "amount_usdc": 1000.00,
                "price": 0.5,
                "size": 2000,
            },
        ]

        filtered = polymarket_client._filter_tracked_wallet_activity_amount(activity)
        stats = polymarket_client._compute_wallet_activity_stats(filtered, [], [])

        self.assertEqual([row["asset"] for row in filtered], ["exact"])
        self.assertEqual(stats["trade_count"], 1)
        self.assertEqual(stats["fill_count"], 1)
        self.assertEqual(stats["total_invested_usdc"], 1000.0)

    def test_sell_proceeds_do_not_help_position_reach_threshold(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 600,
                "price": 0.5,
                "size": 1200,
            },
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "SELL",
                "amount_usdc": 700,
                "price": 0.7,
                "size": 1000,
            },
        ]

        filtered = polymarket_client._filter_tracked_wallet_activity_amount(activity)
        stats = polymarket_client._compute_wallet_activity_stats(filtered, [], [])

        self.assertEqual(filtered, [])
        self.assertEqual(stats["trade_count"], 0)
        self.assertEqual(stats["total_invested_usdc"], 0.0)

    def test_stats_refresh_groups_fills_before_position_threshold(self):
        wallet = "0xwallet"
        activity = [
            {
                "wallet": wallet,
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "result": "won",
                "amount_usdc": 600,
                "price": 0.5,
                "size": 1200,
                "traded_at": "2026-09-10T00:00:00+00:00",
            },
            {
                "wallet": wallet,
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "result": "won",
                "amount_usdc": 600,
                "price": 0.5,
                "size": 1200,
                "traded_at": "2026-09-10T00:01:00+00:00",
            },
            {
                "wallet": wallet,
                "asset": "spain-yes",
                "condition_id": "spain-market",
                "action": "BUY",
                "result": "lost",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
                "traded_at": "2026-09-10T00:02:00+00:00",
            },
        ]
        wallet_patches = []

        def fake_get(url, **_kwargs):
            if "tracked_wallets" in url:
                return FakeResponse(200, [{"created_at": None}])
            if "tracked_wallet_activity" in url:
                return FakeResponse(200, activity)
            if "tracked_wallet_positions" in url:
                return FakeResponse(200, [])
            if "tracked_wallet_redeems" in url:
                return FakeResponse(200, [])
            raise AssertionError(url)

        def fake_patch(url, **kwargs):
            if "tracked_wallet_activity" in url:
                return FakeResponse(204, [])
            if "tracked_wallets" in url:
                wallet_patches.append(kwargs["json"])
                return FakeResponse(204, [])
            raise AssertionError(url)

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://supabase.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "test"}), \
             patch.object(polymarket_client, "_filter_verified_football_items", side_effect=lambda rows: (rows, True)), \
             patch.object(polymarket_client, "_persist_wallet_bet_rows", return_value=True), \
             patch.object(polymarket_client.requests, "get", side_effect=fake_get), \
             patch.object(polymarket_client.requests, "patch", side_effect=fake_patch):
            self.assertTrue(polymarket_client.compute_and_save_wallet_stats(wallet))

        self.assertEqual(len(wallet_patches), 1)
        saved = wallet_patches[0]
        self.assertEqual(saved["trade_count"], 2)
        self.assertEqual(saved["total_invested_usdc"], 2200.0)
        self.assertEqual(saved["resolved_won"], 1)
        self.assertEqual(saved["resolved_lost"], 1)
        self.assertEqual(saved["resolved_total"], 2)
        self.assertEqual(saved["win_rate"], 50.0)

    def test_v2_child_market_is_football_when_parent_event_is_soccer(self):
        items = [{
            "conditionId": "child-condition",
            "title": "Will Ukraine win on 2026-10-02?",
        }]

        def fake_json(url, params=None):
            if url.endswith("/markets") and params.get("tag_id"):
                # Child condition itself is omitted by Soccer-filtered market
                # lookup; parent-event verification must rescue it.
                return []
            if url.endswith("/markets"):
                return [{
                    "conditionId": "child-condition",
                    "events": [{"id": "event-1"}],
                }]
            if url.endswith("/events") and params.get("tag_id"):
                return [{"id": "event-1"}]
            if url.endswith("/events"):
                return [{"id": "event-1"}]
            raise AssertionError((url, params))

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            result = polymarket_client._classify_football_items(items)

        self.assertEqual(len(result["verified_football"]), 1)
        self.assertEqual(result["verified_non_football"], [])
        self.assertEqual(result["uncertain"], [])
        self.assertEqual(
            result["verified_football"][0]["_sport_resolved_event_id"],
            "event-1",
        )

    def test_v2_nonfootball_requires_condition_and_parent_event_double_negative(self):
        items = [{"conditionId": "politics-condition", "title": "France vs. Spain"}]

        def fake_json(url, params=None):
            if url.endswith("/markets") and params.get("tag_id"):
                return []
            if url.endswith("/markets"):
                return [{
                    "conditionId": "politics-condition",
                    "events": [{"id": "politics-event"}],
                }]
            if url.endswith("/events") and params.get("tag_id"):
                return []
            if url.endswith("/events"):
                return [{
                    "id": "politics-event",
                    "tags": [{"id": "2", "slug": "politics", "label": "Politics"}],
                }]
            raise AssertionError((url, params))

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            result = polymarket_client._classify_football_items(items)

        self.assertEqual(result["verified_football"], [])
        self.assertEqual(len(result["verified_non_football"]), 1)
        self.assertEqual(result["uncertain"], [])
        self.assertEqual(
            result["verified_non_football"][0]["_sport_reason"],
            "gamma_double_negative",
        )

    def test_v2_missing_parent_event_is_uncertain_not_nonfootball(self):
        items = [{"conditionId": "mystery-condition", "title": "Unknown"}]

        def fake_json(url, params=None):
            if url.endswith("/markets") and params.get("tag_id"):
                return []
            if url.endswith("/markets"):
                return [{"conditionId": "mystery-condition", "events": []}]
            if url.endswith("/events"):
                return []
            raise AssertionError((url, params))

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            result = polymarket_client._classify_football_items(items)

        self.assertEqual(result["verified_non_football"], [])
        self.assertEqual(len(result["uncertain"]), 1)
        self.assertEqual(
            result["uncertain"][0]["_sport_reason"],
            "parent_event_ambiguous",
        )

    def test_v2_direct_soccer_tag_rescues_filter_omission(self):
        items = [{"conditionId": "child-condition"}]

        def fake_json(url, params=None):
            if url.endswith("/markets") and params.get("tag_id"):
                return []
            if url.endswith("/markets"):
                return [{
                    "conditionId": "child-condition",
                    "tags": [{"id": str(polymarket_client.SOCCER_TAG_ID), "slug": "soccer"}],
                    "events": [{"id": "event-1"}],
                }]
            if url.endswith("/events") and params.get("tag_id"):
                return []
            if url.endswith("/events"):
                return [{
                    "id": "event-1",
                    "tags": [{"id": str(polymarket_client.SOCCER_TAG_ID), "slug": "soccer"}],
                }]
            raise AssertionError((url, params))

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            result = polymarket_client._classify_football_items(items)

        self.assertEqual(len(result["verified_football"]), 1)
        self.assertEqual(result["verified_non_football"], [])

    def test_v2_negative_without_explicit_parent_tags_stays_uncertain(self):
        items = [{"conditionId": "maybe-football"}]

        def fake_json(url, params=None):
            if url.endswith("/markets") and params.get("tag_id"):
                return []
            if url.endswith("/markets"):
                return [{
                    "conditionId": "maybe-football",
                    "events": [{"id": "event-1"}],
                }]
            if url.endswith("/events") and params.get("tag_id"):
                return []
            if url.endswith("/events"):
                return [{"id": "event-1", "tags": []}]
            raise AssertionError((url, params))

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            result = polymarket_client._classify_football_items(items)

        self.assertEqual(result["verified_non_football"], [])
        self.assertEqual(len(result["uncertain"]), 1)
        self.assertEqual(result["uncertain"][0]["_sport_reason"], "event_tags_missing")

    def test_v2_stale_nonfootball_registry_is_revalidated(self):
        now = polymarket_client.datetime.now(polymarket_client.timezone.utc)
        old = (
            now
            - polymarket_client.timedelta(
                seconds=polymarket_client.FOOTBALL_NON_FOOTBALL_RECHECK_SECONDS + 60
            )
        ).isoformat()
        row = {
            "classification": polymarket_client.FOOTBALL_CLASS_NON_FOOTBALL,
            "classifier_version": polymarket_client.FOOTBALL_CLASSIFIER_VERSION,
            "last_checked_at": old,
        }

        self.assertFalse(
            polymarket_client._persisted_classification_is_trusted(
                row,
                now=now,
            )
        )

    def test_v2_recent_nonfootball_registry_is_temporarily_trusted(self):
        now = polymarket_client.datetime.now(polymarket_client.timezone.utc)
        recent = (
            now - polymarket_client.timedelta(minutes=10)
        ).isoformat()
        row = {
            "classification": polymarket_client.FOOTBALL_CLASS_NON_FOOTBALL,
            "classifier_version": polymarket_client.FOOTBALL_CLASSIFIER_VERSION,
            "last_checked_at": recent,
        }

        self.assertTrue(
            polymarket_client._persisted_classification_is_trusted(
                row,
                now=now,
            )
        )

    def test_v2_persisted_parent_soccer_overrides_stale_condition_negative(self):
        items = [{"conditionId": "child-condition"}]

        def registry(identity_type, _ids):
            if identity_type == "condition":
                return {
                    "child-condition": {
                        "identity_id": "child-condition",
                        "event_id": "event-1",
                        "classification": polymarket_client.FOOTBALL_CLASS_NON_FOOTBALL,
                    }
                }
            return {
                "event-1": {
                    "identity_id": "event-1",
                    "event_id": "event-1",
                    "classification": polymarket_client.FOOTBALL_CLASS_VERIFIED,
                }
            }

        with patch.object(
            polymarket_client,
            "_load_persisted_sport_registry",
            side_effect=registry,
        ), patch.object(
            polymarket_client,
            "_persist_sport_registry_records",
        ):
            result = polymarket_client._classify_football_items(items)

        self.assertEqual(len(result["verified_football"]), 1)
        self.assertEqual(result["verified_non_football"], [])

    def test_v2_gamma_failure_is_uncertain_and_never_negative(self):
        items = [{"conditionId": "soccer-condition", "title": "Club A vs. Club B"}]

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", return_value=None):
            result = polymarket_client._classify_football_items(items)

        self.assertEqual(result["verified_football"], [])
        self.assertEqual(result["verified_non_football"], [])
        self.assertEqual(len(result["uncertain"]), 1)

    def test_strict_football_registry_rejects_title_heuristic_false_positive(self):
        items = [
            {
                "conditionId": "soccer-condition",
                "title": "Club A vs. Club B",
                "slug": "club-a-club-b",
            },
            {
                "conditionId": "politics-condition",
                # Deliberately football-looking title: title heuristics must
                # never override Gamma's category registry.
                "title": "France vs. Spain",
                "slug": "france-vs-spain-politics",
            },
        ]

        def fake_json(url, params=None):
            if url.endswith("/markets") and params.get("tag_id"):
                self.assertEqual(params["tag_id"], polymarket_client.SOCCER_TAG_ID)
                return [{"conditionId": "soccer-condition"}]
            if url.endswith("/markets"):
                return [
                    {
                        "conditionId": "soccer-condition",
                        "events": [{"id": "soccer-event"}],
                    },
                    {
                        "conditionId": "politics-condition",
                        "events": [{"id": "politics-event"}],
                    },
                ]
            if url.endswith("/events") and params.get("tag_id"):
                return [{"id": "soccer-event"}]
            if url.endswith("/events"):
                return [{
                    "id": "politics-event",
                    "tags": [{"id": "2", "slug": "politics", "label": "Politics"}],
                }]
            raise AssertionError((url, params))

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            filtered, ok = polymarket_client._filter_verified_football_items(items)

        self.assertTrue(ok)
        self.assertEqual([row["conditionId"] for row in filtered], ["soccer-condition"])

    def test_strict_football_registry_accepts_verified_event_id_fallback(self):
        items = [{"eventId": "12345", "title": "Unknown formatting"}]

        def fake_json(url, params=None):
            self.assertTrue(url.endswith("/events"))
            self.assertEqual(params["tag_id"], polymarket_client.SOCCER_TAG_ID)
            self.assertEqual(params["id"], ["12345"])
            return [{"id": "12345"}]

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            filtered, ok = polymarket_client._filter_verified_football_items(items)

        self.assertTrue(ok)
        self.assertEqual(filtered, items)

    def test_registry_failure_is_not_treated_as_verified_nonfootball(self):
        items = [{"conditionId": "soccer-condition", "title": "Club A vs. Club B"}]

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", return_value=None):
            filtered, ok = polymarket_client._filter_verified_football_items(items)

        self.assertFalse(ok)
        self.assertEqual(filtered, [])

    def test_wallet_activity_fetch_keeps_only_gamma_verified_soccer_rows(self):
        raw = [
            {
                "conditionId": "soccer-condition",
                "timestamp": 100,
                "title": "Club A vs. Club B",
            },
            {
                "conditionId": "crypto-condition",
                "timestamp": 99,
                "title": "Bitcoin above 100k?",
            },
        ]

        def fake_json(url, params=None):
            if url.endswith("/activity"):
                return raw
            if url.endswith("/markets") and params.get("tag_id"):
                return [{"conditionId": "soccer-condition"}]
            if url.endswith("/markets"):
                return [{
                    "conditionId": "crypto-condition",
                    "events": [{"id": "crypto-event"}],
                }]
            if url.endswith("/events") and params.get("tag_id"):
                return []
            if url.endswith("/events"):
                return [{
                    "id": "crypto-event",
                    "tags": [{"id": "21", "slug": "crypto", "label": "Crypto"}],
                }]
            raise AssertionError((url, params))

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            rows, truncated = polymarket_client.fetch_wallet_activity(
                "0xwallet",
                max_pages=1,
            )

        self.assertFalse(truncated)
        self.assertEqual([row["conditionId"] for row in rows], ["soccer-condition"])

    def test_activity_classification_details_returns_uncertain_without_dropping_verified(self):
        raw = [
            {"conditionId": "soccer", "timestamp": 100},
            {"conditionId": "mystery", "timestamp": 99},
            {"conditionId": "politics", "timestamp": 98},
        ]
        classified = {
            "verified_football": [dict(raw[0], _sport_classification="verified_football")],
            "uncertain": [dict(raw[1], _sport_classification="uncertain")],
            "verified_non_football": [dict(raw[2], _sport_classification="verified_non_football")],
            "verification_complete": False,
        }

        with patch.object(polymarket_client, "_get_json", return_value=raw), \
             patch.object(polymarket_client, "_classify_football_items", return_value=classified):
            football, truncated, uncertain, nonfootball = polymarket_client.fetch_wallet_activity(
                "0xwallet",
                max_pages=1,
                classification_details=True,
            )

        self.assertFalse(truncated)
        self.assertEqual(len(football), 1)
        self.assertEqual(len(uncertain), 1)
        self.assertEqual(len(nonfootball), 1)

    def test_positions_registry_failure_preserves_existing_snapshot_contract(self):
        raw = [{
            "conditionId": "soccer-condition",
            "asset": "soccer-asset",
            "title": "Club A vs. Club B",
        }]

        def fake_json(url, params=None):
            if url.endswith("/positions"):
                return raw
            if url.endswith("/markets"):
                return None
            raise AssertionError(url)

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            rows, ok = polymarket_client.fetch_wallet_positions("0xwallet")

        self.assertFalse(ok)
        self.assertEqual(rows, [])

    def test_stats_refresh_excludes_existing_nonfootball_db_rows(self):
        wallet = "0xwallet"
        activity = [
            {
                "wallet": wallet,
                "asset": "soccer-asset",
                "condition_id": "soccer-condition",
                "action": "BUY",
                "result": "won",
                "amount_usdc": 600,
                "price": 0.5,
                "size": 1200,
                "traded_at": "2026-09-10T00:00:00+00:00",
            },
            {
                "wallet": wallet,
                "asset": "soccer-asset",
                "condition_id": "soccer-condition",
                "action": "BUY",
                "result": "won",
                "amount_usdc": 600,
                "price": 0.5,
                "size": 1200,
                "traded_at": "2026-09-10T00:01:00+00:00",
            },
            {
                "wallet": wallet,
                "asset": "politics-asset",
                "condition_id": "politics-condition",
                "action": "BUY",
                "result": "won",
                "amount_usdc": 5000,
                "price": 0.5,
                "size": 10000,
                "traded_at": "2026-09-10T00:02:00+00:00",
            },
        ]
        wallet_patches = []

        def fake_get(url, **_kwargs):
            if "tracked_wallets" in url:
                return FakeResponse(200, [{"created_at": None}])
            if "tracked_wallet_activity" in url:
                return FakeResponse(200, activity)
            if "tracked_wallet_positions" in url:
                return FakeResponse(200, [])
            if "tracked_wallet_redeems" in url:
                return FakeResponse(200, [])
            raise AssertionError(url)

        def fake_patch(url, **kwargs):
            if "tracked_wallet_activity" in url:
                return FakeResponse(204, [])
            if "tracked_wallets" in url:
                wallet_patches.append(kwargs["json"])
                return FakeResponse(204, [])
            raise AssertionError(url)

        def fake_registry_json(url, params=None):
            if url.endswith("/markets") and params.get("tag_id"):
                return [{"conditionId": "soccer-condition"}]
            if url.endswith("/markets"):
                return [{
                    "conditionId": "politics-condition",
                    "events": [{"id": "politics-event"}],
                }]
            if url.endswith("/events") and params.get("tag_id"):
                return []
            if url.endswith("/events"):
                return [{
                    "id": "politics-event",
                    "tags": [{"id": "2", "slug": "politics", "label": "Politics"}],
                }]
            raise AssertionError((url, params))

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://supabase.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "test"}), \
             patch.object(polymarket_client, "_load_persisted_sport_registry", return_value={}), \
             patch.object(polymarket_client, "_persist_sport_registry_records"), \
             patch.object(polymarket_client, "_get_json", side_effect=fake_registry_json), \
             patch.object(polymarket_client.requests, "get", side_effect=fake_get), \
             patch.object(polymarket_client.requests, "patch", side_effect=fake_patch):
            self.assertTrue(polymarket_client.compute_and_save_wallet_stats(wallet))

        self.assertEqual(len(wallet_patches), 1)
        saved = wallet_patches[0]
        self.assertEqual(saved["trade_count"], 1)
        self.assertEqual(saved["total_invested_usdc"], 1200.0)
        self.assertEqual(saved["resolved_won"], 1)
        self.assertEqual(saved["resolved_lost"], 0)
        self.assertEqual(saved["resolved_total"], 1)
        self.assertEqual(saved["win_rate"], 100.0)

    def test_canonical_match_metadata_prefers_event_registry_over_raw_title(self):
        row = {
            "event_id": "42",
            "slug": "wrong-market-slug",
            "title": "Misleading Raw Market Title",
        }
        stored = [{
            "event_id": "42",
            "slug": "barcelona-real-madrid-2026-10-02",
            "home": "Barcelona",
            "away": "Real Madrid",
            "kickoff_utc": "2026-10-02T19:00:00+00:00",
        }]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=stored):
            meta = polymarket_client._canonical_match_metadata(row)

        self.assertEqual(meta["match_key"], "event:42")
        self.assertEqual(meta["event_id"], "42")
        self.assertEqual(meta["event_slug"], "barcelona-real-madrid-2026-10-02")
        self.assertEqual(meta["match_name"], "Barcelona - Real Madrid")
        self.assertEqual(meta["home"], "Barcelona")
        self.assertEqual(meta["away"], "Real Madrid")
        self.assertEqual(meta["kickoff_utc"], "2026-10-02T19:00:00+00:00")
        self.assertEqual(meta["source"], "polymarket_matches")

    def test_canonical_match_metadata_collapses_more_markets_slug(self):
        row = {
            "slug": "france-spain-2026-10-02-more-markets",
            "title": "France vs. Spain: O/U 2.5",
        }
        stored = [{
            "event_id": "99",
            "slug": "france-spain-2026-10-02",
            "home": "France",
            "away": "Spain",
            "kickoff_utc": "2026-10-02T20:00:00+00:00",
        }]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=stored):
            meta = polymarket_client._canonical_match_metadata(row)

        self.assertEqual(meta["match_key"], "event:99")
        self.assertEqual(meta["event_slug"], "france-spain-2026-10-02")
        self.assertEqual(meta["match_name"], "France - Spain")

    def test_display_activity_exposes_canonical_match_identity(self):
        activity = [{
            "wallet": "0xwallet",
            "asset": "france-yes",
            "condition_id": "france-market",
            "event_id": "99",
            "title": "Will France win on 2026-10-02?",
            "slug": "france-spain-2026-10-02-more-markets",
            "market_type": "1x2",
            "selection": "France",
            "side": "",
            "action": "BUY",
            "outcome_raw": "Yes",
            "amount_usdc": 1200,
            "price": 0.5,
            "traded_at": "2026-10-02T17:00:00+00:00",
            "result": "won",
        }]
        stored = [{
            "event_id": "99",
            "slug": "france-spain-2026-10-02",
            "home": "France",
            "away": "Spain",
            "kickoff_utc": "2026-10-02T20:00:00+00:00",
        }]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=stored):
            rows = polymarket_client._build_display_activity(activity, [], {"france-yes"}, set())

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["match"], "France - Spain")
        self.assertEqual(rows[0]["match_name"], "France - Spain")
        self.assertEqual(rows[0]["match_key"], "event:99")
        self.assertEqual(rows[0]["event_id"], "99")
        self.assertEqual(rows[0]["slug"], "france-spain-2026-10-02")
        self.assertEqual(rows[0]["kickoff_utc"], "2026-10-02T20:00:00+00:00")

    def test_wallet_bet_display_contract_1x2(self):
        fields = polymarket_client._wallet_bet_display_contract({
            "market_type": "1x2",
            "selection": "France",
            "outcome_raw": "France",
        })
        self.assertEqual(fields["market_label"], "1X2")
        self.assertEqual(fields["selection_label"], "France")
        self.assertEqual(fields["side_label"], "")
        self.assertEqual(fields["bet_label"], "France")

    def test_wallet_bet_display_contract_binary_1x2_keeps_yes_no_polarity(self):
        fields = polymarket_client._wallet_bet_display_contract({
            "market_type": "1x2",
            "selection": "France",
            "outcome_raw": "Yes",
        })
        self.assertEqual(fields["market_label"], "1X2")
        self.assertEqual(fields["selection_label"], "France")
        self.assertEqual(fields["side_label"], "Evet")
        self.assertEqual(fields["bet_label"], "France · Evet")

    def test_wallet_bet_display_contract_total_goals(self):
        fields = polymarket_client._wallet_bet_display_contract({
            "market_type": "ou25",
            "selection": "Toplam Gol 2.5",
            "outcome_raw": "Under",
        })
        self.assertEqual(fields["market_label"], "Toplam Gol 2.5")
        self.assertEqual(fields["selection_label"], "Alt")
        self.assertEqual(fields["bet_label"], "Alt")

    def test_wallet_bet_display_contract_btts(self):
        fields = polymarket_client._wallet_bet_display_contract({
            "market_type": "btts",
            "selection": "Karşılıklı Gol (KG)",
            "outcome_raw": "Yes",
        })
        self.assertEqual(fields["market_label"], "Karşılıklı Gol")
        self.assertEqual(fields["selection_label"], "Var")
        self.assertEqual(fields["bet_label"], "Var")

    def test_wallet_bet_display_contract_dynamic_total_and_handicap(self):
        total = polymarket_client._wallet_bet_display_contract({
            "market_type": "special",
            "title": "France vs. Spain: O/U 3.5",
            "selection": "O/U 3.5",
            "outcome_raw": "Over",
        })
        handicap = polymarket_client._wallet_bet_display_contract({
            "market_type": "special",
            "title": "France vs. Spain: France (-1.5)",
            "selection": "France -1.5",
            "outcome_raw": "Yes",
        })

        self.assertEqual(total["market_label"], "Toplam Gol 3.5")
        self.assertEqual(total["selection_label"], "Üst")
        self.assertEqual(handicap["market_label"], "Handikap")
        self.assertEqual(handicap["selection_label"], "France -1.5")
        self.assertEqual(handicap["bet_label"], "France -1.5 · Evet")

    def test_display_activity_includes_market_selection_contract(self):
        activity = [{
            "wallet": "0xwallet",
            "asset": "france-under",
            "condition_id": "france-total",
            "event_id": "99",
            "title": "France vs. Spain: O/U 2.5",
            "slug": "france-spain-2026-10-02-more-markets",
            "market_type": "ou25",
            "selection": "Toplam Gol 2.5",
            "side": "2.5 Alt",
            "action": "BUY",
            "outcome_raw": "Under",
            "amount_usdc": 1200,
            "price": 0.55,
            "traded_at": "2026-10-02T17:00:00+00:00",
            "result": "won",
        }]
        stored = [{
            "event_id": "99",
            "slug": "france-spain-2026-10-02",
            "home": "France",
            "away": "Spain",
            "kickoff_utc": "2026-10-02T20:00:00+00:00",
        }]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=stored):
            rows = polymarket_client._build_display_activity(activity, [], {"france-under"}, set())

        self.assertEqual(rows[0]["market_label"], "Toplam Gol 2.5")
        self.assertEqual(rows[0]["selection_label"], "Alt")
        self.assertEqual(rows[0]["side_label"], "")
        self.assertEqual(rows[0]["bet_label"], "Alt")

    def test_display_activity_merges_buy_and_sell_into_one_lifecycle_row(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "event_id": "99",
                "title": "France vs. Spain",
                "slug": "france-spain",
                "market_type": "1x2",
                "selection": "France",
                "action": "BUY",
                "outcome_raw": "France",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
                "traded_at": "2026-10-02T15:00:00+00:00",
            },
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "event_id": "99",
                "title": "France vs. Spain",
                "slug": "france-spain",
                "market_type": "1x2",
                "selection": "France",
                "action": "SELL",
                "outcome_raw": "France",
                "amount_usdc": 1200,
                "price": 0.6,
                "size": 2000,
                "traded_at": "2026-10-02T18:00:00+00:00",
            },
        ]
        stored = [{
            "event_id": "99",
            "slug": "france-spain",
            "home": "France",
            "away": "Spain",
            "kickoff_utc": "2026-10-02T20:00:00+00:00",
        }]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=stored):
            rows = polymarket_client._build_display_activity(activity, [], set(), set(), [])

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["asset"], "france-yes")
        self.assertEqual(row["stake_usdc"], 1000.0)
        self.assertEqual(row["sell_proceeds_usdc"], 1200.0)
        self.assertEqual(row["buy_fill_count"], 1)
        self.assertEqual(row["sell_fill_count"], 1)
        self.assertEqual(row["fill_count"], 2)
        self.assertEqual(row["status_label"], "Kapandı")
        self.assertEqual(row["lifecycle_status"], "closed")
        self.assertEqual(row["result"], "closed")
        self.assertEqual(row["price"], 2.0)
        self.assertEqual(row["pnl_usdc"], 200.0)
        self.assertEqual(row["pnl_kind"], "realized")
        self.assertEqual(row["traded_at"], "2026-10-02T18:00:00+00:00")

    def test_open_lifecycle_keeps_sell_inside_same_row_and_uses_current_pnl(self):
        activity = [
            {
                "asset": "france-yes",
                "condition_id": "france-market",
                "title": "France vs. Spain",
                "slug": "france-spain",
                "market_type": "1x2",
                "selection": "France",
                "action": "BUY",
                "outcome_raw": "France",
                "amount_usdc": 1200,
                "price": 0.6,
                "size": 2000,
                "traded_at": "2026-10-02T15:00:00+00:00",
            },
            {
                "asset": "france-yes",
                "condition_id": "france-market",
                "title": "France vs. Spain",
                "slug": "france-spain",
                "market_type": "1x2",
                "selection": "France",
                "action": "SELL",
                "outcome_raw": "France",
                "amount_usdc": 300,
                "price": 0.75,
                "size": 400,
                "traded_at": "2026-10-02T16:00:00+00:00",
            },
        ]
        positions = [{
            "asset": "france-yes",
            "condition_id": "france-market",
            "title": "France vs. Spain",
            "slug": "france-spain",
            "outcome": "France",
            "cash_pnl": 150,
            "current_value": 1050,
            "redeemable": False,
        }]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=[]):
            rows = polymarket_client._build_display_activity(activity, positions, set(), set(), [])

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status_label"], "Açık")
        self.assertEqual(row["result"], "open")
        self.assertEqual(row["stake_usdc"], 1200.0)
        self.assertEqual(row["sell_proceeds_usdc"], 300.0)
        self.assertEqual(row["pnl_usdc"], 150.0)
        self.assertEqual(row["pnl_kind"], "current")

    def test_redeemed_winner_lifecycle_uses_payout_for_realized_pnl(self):
        activity = [{
            "asset": "france-yes",
            "condition_id": "france-market",
            "title": "France vs. Spain",
            "slug": "france-spain",
            "market_type": "1x2",
            "selection": "France",
            "action": "BUY",
            "outcome_raw": "France",
            "amount_usdc": 1000,
            "price": 0.5,
            "size": 2000,
            "traded_at": "2026-10-02T15:00:00+00:00",
            "result": "won",
        }]
        redeems = [{
            "asset": "france-yes",
            "condition_id": "france-market",
            "amount_usdc": 2000,
            "traded_at": "2026-10-02T22:00:00+00:00",
        }]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=[]):
            rows = polymarket_client._build_display_activity(
                activity, [], {"france-yes"}, set(), redeems
            )

        self.assertEqual(len(rows), 1)
        row = rows[0]
        self.assertEqual(row["status_label"], "Kazandı")
        self.assertEqual(row["result"], "won")
        self.assertEqual(row["redeem_proceeds_usdc"], 2000.0)
        self.assertEqual(row["pnl_usdc"], 1000.0)
        self.assertEqual(row["pnl_kind"], "realized")
        self.assertEqual(row["traded_at"], "2026-10-02T22:00:00+00:00")

    def test_lost_lifecycle_realized_pnl_includes_prior_sell_proceeds(self):
        activity = [
            {
                "asset": "france-yes",
                "condition_id": "france-market",
                "title": "France vs. Spain",
                "market_type": "1x2",
                "selection": "France",
                "action": "BUY",
                "outcome_raw": "France",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
                "traded_at": "2026-10-02T15:00:00+00:00",
            },
            {
                "asset": "france-yes",
                "condition_id": "france-market",
                "title": "France vs. Spain",
                "market_type": "1x2",
                "selection": "France",
                "action": "SELL",
                "outcome_raw": "France",
                "amount_usdc": 250,
                "price": 0.5,
                "size": 500,
                "traded_at": "2026-10-02T16:00:00+00:00",
            },
        ]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=[]):
            rows = polymarket_client._build_display_activity(
                activity, [], set(), {"france-yes"}, []
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["status_label"], "Kaybetti")
        self.assertEqual(rows[0]["pnl_usdc"], -750.0)
        self.assertEqual(rows[0]["pnl_kind"], "realized")

    def test_fetch_clob_midpoints_parses_current_sdk_shape(self):
        calls = []

        def fake_post(url, **kwargs):
            calls.append((url, kwargs["json"]))
            return FakeResponse(200, {
                "asset-a": "0.42",
                "asset-b": "0.615",
                "bad": "not-a-price",
            })

        with patch.object(polymarket_client.requests, "post", side_effect=fake_post):
            prices, ok = polymarket_client._fetch_clob_midpoints(
                ["asset-a", "asset-b", "asset-a"]
            )

        self.assertTrue(ok)
        self.assertEqual(prices, {
            "asset-a": 0.42,
            "asset-b": 0.615,
        })
        self.assertEqual(calls[0][0], f"{polymarket_client.CLOB_BASE}/midpoints")
        self.assertEqual(
            calls[0][1],
            [{"token_id": "asset-a"}, {"token_id": "asset-b"}],
        )

    def test_fetch_clob_midpoints_keeps_partial_success(self):
        responses = [
            FakeResponse(200, {f"a{i}": "0.50" for i in range(100)}),
            FakeResponse(503, {"error": "temporary"}),
        ]

        with patch.object(
            polymarket_client.requests,
            "post",
            side_effect=responses,
        ):
            prices, ok = polymarket_client._fetch_clob_midpoints(
                [f"a{i}" for i in range(101)]
            )

        self.assertFalse(ok)
        self.assertEqual(len(prices), 100)
        self.assertNotIn("a100", prices)

    def test_closing_line_metrics_positive_when_market_moves_toward_bettor(self):
        metrics = polymarket_client._closing_line_metrics(0.50, 0.60)

        self.assertEqual(metrics["closing_decimal"], 1.67)
        self.assertEqual(metrics["clv_probability_pp"], 10.0)
        self.assertEqual(metrics["clv_pct"], 20.0)

    def test_closing_line_metrics_negative_when_entry_price_worsens(self):
        metrics = polymarket_client._closing_line_metrics(0.60, 0.50)

        self.assertEqual(metrics["closing_decimal"], 2.0)
        self.assertEqual(metrics["clv_probability_pp"], -10.0)
        self.assertEqual(metrics["clv_pct"], -16.67)

    def test_persisted_wallet_bet_stats_keep_all_history(self):
        rows = [
            {
                "bet_key": "old-win",
                "stake_usdc": 1500,
                "avg_entry_price": 0.50,
                "result": "won",
                "lifecycle_status": "resolved",
                "fill_count": 2,
            },
            {
                "bet_key": "old-loss",
                "stake_usdc": 2500,
                "avg_entry_price": 0.25,
                "result": "lost",
                "lifecycle_status": "resolved",
                "fill_count": 3,
            },
            {
                "bet_key": "recent-open",
                "stake_usdc": 1000,
                "avg_entry_price": 0.60,
                "result": "open",
                "lifecycle_status": "open",
                "fill_count": 1,
            },
            {
                "bet_key": "sub-threshold-corrupt-row",
                "stake_usdc": 999,
                "avg_entry_price": 0.90,
                "result": "won",
                "fill_count": 1,
            },
        ]

        stats = polymarket_client._compute_persisted_wallet_bet_stats(rows)

        self.assertEqual(stats["trade_count"], 3)
        self.assertEqual(stats["fill_count"], 6)
        self.assertEqual(stats["total_invested_usdc"], 5000.0)
        self.assertEqual(stats["avg_bet_size_usdc"], 1666.67)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 1)
        self.assertEqual(stats["resolved_total"], 2)
        self.assertEqual(stats["win_rate"], 50.0)
        # stake-weighted probability: (1500*.5 + 2500*.25 + 1000*.6) / 5000
        self.assertEqual(stats["avg_price"], 0.395)
        self.assertEqual(stats["avg_price_decimal"], 2.53)

    def test_incomplete_normalized_rollout_preserves_larger_baseline(self):
        baseline = {
            "last_synced_at": "2026-10-01T00:00:00+00:00",
            "trade_count": 42,
            "total_invested_usdc": 42000,
            "avg_bet_size_usdc": 1000,
            "avg_price": 0.5,
            "avg_price_decimal": 2.0,
            "resolved_won": 20,
            "resolved_lost": 10,
            "resolved_total": 30,
            "win_rate": 66.7,
        }
        raw = {
            "trade_count": 4,
            "fill_count": 8,
            "total_invested_usdc": 5000,
        }

        preserved = polymarket_client._baseline_wallet_history_stats(
            baseline,
            raw,
        )

        self.assertEqual(preserved["trade_count"], 42)
        self.assertEqual(preserved["total_invested_usdc"], 42000.0)
        self.assertEqual(preserved["resolved_total"], 30)
        self.assertEqual(preserved["win_rate"], 66.7)
        self.assertEqual(preserved["fill_count"], 8)

    def test_persisted_wallet_bet_stats_reader_paginates_full_history(self):
        calls = []
        page1 = [
            {"bet_key": f"b{i}", "stake_usdc": 1000}
            for i in range(1000)
        ]
        page2 = [{"bet_key": "b1000", "stake_usdc": 1000}]

        def fake_get(_url, **kwargs):
            calls.append(kwargs["params"]["offset"])
            if kwargs["params"]["offset"] == 0:
                return FakeResponse(200, page1)
            return FakeResponse(200, page2)

        with patch.object(polymarket_client.requests, "get", side_effect=fake_get):
            rows, ok = polymarket_client._fetch_persisted_wallet_bets_for_stats(
                "https://supabase.test",
                {"apikey": "test"},
                "0xwallet",
            )

        self.assertTrue(ok)
        self.assertEqual(len(rows), 1001)
        self.assertEqual(calls, [0, 1000])

    def test_canonical_bet_key_is_deterministic_for_same_asset(self):
        first = polymarket_client._canonical_bet_identity({
            "wallet": "0xABC",
            "asset": "france-yes",
            "condition_id": "one",
        })
        second = polymarket_client._canonical_bet_identity({
            "wallet": "0xabc",
            "asset": "france-yes",
            "condition_id": "different-metadata",
        })

        self.assertEqual(first, second)
        self.assertEqual(
            polymarket_client._canonical_bet_key_text(first),
            '["asset","0xabc","france-yes"]',
        )

    def test_persist_wallet_bets_upserts_wallet_and_bet_key(self):
        posts = []
        lifecycle = [{
            "bet_key": '["asset","0xwallet","france-yes"]',
            "asset": "france-yes",
            "condition_id": "france-market",
            "event_id": "99",
            "match_key": "event:99",
            "match_name": "France - Spain",
            "market_type": "1x2",
            "market_label": "1X2",
            "selection": "France",
            "selection_label": "France",
            "bet_label": "France",
            "lifecycle_status": "closed",
            "result": "closed",
            "status_label": "Kapandı",
            "stake_usdc": 1000.0,
            "sell_proceeds_usdc": 1200.0,
            "avg_entry_price": 0.5,
            "avg_entry_decimal": 2.0,
            "pnl_usdc": 200.0,
            "pnl_kind": "realized",
            "fill_count": 2,
            "buy_fill_count": 1,
            "sell_fill_count": 1,
            "first_traded_at": "2026-10-02T15:00:00+00:00",
            "last_traded_at": "2026-10-02T18:00:00+00:00",
        }]

        def fake_post(url, **kwargs):
            posts.append((url, kwargs))
            return FakeResponse(201, [])

        with patch.object(polymarket_client.requests, "post", side_effect=fake_post):
            ok = polymarket_client._persist_wallet_bet_rows(
                "https://supabase.test",
                {"apikey": "test"},
                "0xwallet",
                lifecycle,
            )

        self.assertTrue(ok)
        self.assertEqual(len(posts), 1)
        url, kwargs = posts[0]
        self.assertIn("tracked_wallet_bets?on_conflict=wallet,bet_key", url)
        saved = kwargs["json"][0]
        self.assertEqual(saved["wallet"], "0xwallet")
        self.assertEqual(saved["bet_key"], lifecycle[0]["bet_key"])
        self.assertEqual(saved["stake_usdc"], 1000.0)
        self.assertEqual(saved["sell_proceeds_usdc"], 1200.0)
        self.assertEqual(saved["pnl_usdc"], 200.0)
        self.assertEqual(saved["lifecycle_status"], "closed")

    def test_display_lifecycle_contains_persistable_bet_key(self):
        activity = [{
            "wallet": "0xwallet",
            "asset": "france-yes",
            "condition_id": "france-market",
            "title": "France vs. Spain",
            "market_type": "1x2",
            "selection": "France",
            "action": "BUY",
            "outcome_raw": "France",
            "amount_usdc": 1000,
            "price": 0.5,
            "size": 2000,
            "traded_at": "2026-10-02T15:00:00+00:00",
        }]

        with patch.object(polymarket_client, "_fetch_stored_matches", return_value=[]):
            rows = polymarket_client._build_display_activity(
                activity, [], set(), set(), []
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(
            rows[0]["bet_key"],
            '["asset","0xwallet","france-yes"]',
        )

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

        self.assertEqual(stats["trade_count"], 2)
        self.assertEqual(stats["fill_count"], 3)
        self.assertEqual(stats["total_invested_usdc"], 35)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 1)
        self.assertEqual(stats["resolved_total"], 2)
        self.assertEqual(stats["win_rate"], 50.0)

    def test_ten_repeated_fills_of_same_outcome_count_as_one_bet(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "market_type": "moneyline",
                "selection": "France",
                "outcome_raw": "Yes",
                "action": "BUY",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
            }
            for _ in range(10)
        ]

        grouped = polymarket_client._group_activity_into_canonical_bets(activity)
        stats = polymarket_client._compute_wallet_activity_stats(activity, [], [])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["fill_count"], 10)
        self.assertEqual(grouped[0]["gross_fill_volume_usdc"], 10000.0)
        self.assertEqual(grouped[0]["buy_stake_usdc"], 10000.0)
        self.assertEqual(grouped[0]["sell_proceeds_usdc"], 0.0)
        self.assertEqual(grouped[0]["stake_usdc"], 10000.0)
        self.assertEqual(grouped[0]["avg_entry_price"], 0.5)
        self.assertEqual(stats["trade_count"], 1)
        self.assertEqual(stats["fill_count"], 10)
        self.assertEqual(stats["total_invested_usdc"], 10000.0)
        self.assertEqual(stats["avg_bet_size_usdc"], 10000.0)
        self.assertEqual(stats["avg_price"], 0.5)
        self.assertEqual(stats["avg_price_decimal"], 2.0)

    def test_buy_stake_excludes_sell_proceeds_and_uses_share_weighted_entry(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
            },
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 1500,
                "price": 0.6,
                "size": 2500,
            },
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "SELL",
                "amount_usdc": 1100,
                "price": 0.55,
                "size": 2000,
            },
        ]

        grouped = polymarket_client._group_activity_into_canonical_bets(activity)
        stats = polymarket_client._compute_wallet_activity_stats(activity, [], [])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["fill_count"], 3)
        self.assertEqual(grouped[0]["buy_fill_count"], 2)
        self.assertEqual(grouped[0]["sell_fill_count"], 1)
        self.assertEqual(grouped[0]["gross_fill_volume_usdc"], 3600.0)
        self.assertEqual(grouped[0]["buy_stake_usdc"], 2500.0)
        self.assertEqual(grouped[0]["sell_proceeds_usdc"], 1100.0)
        self.assertEqual(grouped[0]["stake_usdc"], 2500.0)
        self.assertEqual(grouped[0]["avg_entry_price"], 0.555556)
        self.assertEqual(stats["trade_count"], 1)
        self.assertEqual(stats["fill_count"], 3)
        self.assertEqual(stats["total_invested_usdc"], 2500.0)
        self.assertEqual(stats["avg_bet_size_usdc"], 2500.0)
        self.assertEqual(stats["avg_price"], 0.5556)
        self.assertEqual(stats["avg_price_decimal"], 1.8)

    def test_sell_only_activity_is_exit_not_new_bet(self):
        activity = [{
            "wallet": "0xwallet",
            "asset": "old-france-yes",
            "condition_id": "france-market",
            "action": "SELL",
            "amount_usdc": 1500,
            "price": 0.6,
            "size": 2500,
        }]

        grouped = polymarket_client._group_activity_into_canonical_bets(activity)
        stats = polymarket_client._compute_wallet_activity_stats(activity, [], [])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["sell_proceeds_usdc"], 1500.0)
        self.assertEqual(grouped[0]["stake_usdc"], 0.0)
        self.assertEqual(grouped[0]["stake_source"], "none")
        self.assertEqual(stats["trade_count"], 0)
        self.assertEqual(stats["total_invested_usdc"], 0.0)
        self.assertEqual(stats["avg_bet_size_usdc"], 0.0)
        self.assertEqual(stats["avg_price"], 0.0)
        self.assertIsNone(stats["avg_price_decimal"])

    def test_actionless_legacy_position_keeps_historical_stake(self):
        activity = [
            {
                "asset": "legacy-france-yes",
                "condition_id": "france-market",
                "amount_usdc": 1000,
                "price": 0.5,
            },
            {
                "asset": "legacy-france-yes",
                "condition_id": "france-market",
                "amount_usdc": 1500,
                "price": 0.6,
            },
        ]

        grouped = polymarket_client._group_activity_into_canonical_bets(activity)
        stats = polymarket_client._compute_wallet_activity_stats(activity, [], [])

        self.assertEqual(len(grouped), 1)
        self.assertEqual(grouped[0]["stake_source"], "legacy_unknown")
        self.assertEqual(grouped[0]["stake_usdc"], 2500.0)
        self.assertEqual(grouped[0]["avg_entry_price"], 0.555556)
        self.assertEqual(stats["trade_count"], 1)
        self.assertEqual(stats["total_invested_usdc"], 2500.0)

    def test_legacy_same_condition_keeps_opposite_outcomes_separate(self):
        activity = [
            {
                "wallet": "0xwallet",
                "condition_id": "france-market",
                "market_type": "moneyline",
                "selection": "France",
                "outcome_raw": "Yes",
                "amount_usdc": 1000,
                "price": 0.5,
            },
            {
                "wallet": "0xwallet",
                "condition_id": "france-market",
                "market_type": "moneyline",
                "selection": "France",
                "outcome_raw": "Yes",
                "amount_usdc": 1200,
                "price": 0.55,
            },
            {
                "wallet": "0xwallet",
                "condition_id": "france-market",
                "market_type": "moneyline",
                "selection": "France",
                "outcome_raw": "No",
                "amount_usdc": 1300,
                "price": 0.45,
            },
        ]

        grouped = polymarket_client._group_activity_into_canonical_bets(activity)
        stats = polymarket_client._compute_wallet_activity_stats(activity, [], [])

        self.assertEqual(len(grouped), 2)
        self.assertEqual(sorted(group["fill_count"] for group in grouped), [1, 2])
        self.assertEqual(stats["trade_count"], 2)
        self.assertEqual(stats["fill_count"], 3)

    def test_repeated_winning_fills_count_as_one_resolved_bet(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
                "result": "won",
            }
            for _ in range(10)
        ]

        stats = polymarket_client._compute_wallet_activity_stats(activity, [], [])

        self.assertEqual(stats["trade_count"], 1)
        self.assertEqual(stats["fill_count"], 10)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 0)
        self.assertEqual(stats["resolved_total"], 1)
        self.assertEqual(stats["win_rate"], 100.0)

    def test_opposite_outcomes_same_condition_are_two_resolved_bets(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "market_type": "moneyline",
                "selection": "France",
                "outcome_raw": "Yes",
                "action": "BUY",
                "amount_usdc": 1200,
                "price": 0.6,
                "size": 2000,
                "result": "won",
            },
            {
                "wallet": "0xwallet",
                "asset": "france-no",
                "condition_id": "france-market",
                "market_type": "moneyline",
                "selection": "France",
                "outcome_raw": "No",
                "action": "BUY",
                "amount_usdc": 1100,
                "price": 0.55,
                "size": 2000,
                "result": "lost",
            },
        ]

        stats = polymarket_client._compute_wallet_activity_stats(activity, [], [])

        self.assertEqual(stats["trade_count"], 2)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 1)
        self.assertEqual(stats["resolved_total"], 2)
        self.assertEqual(stats["win_rate"], 50.0)

    def test_asset_resolution_does_not_fall_back_to_shared_condition_winner(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
            },
            {
                "wallet": "0xwallet",
                "asset": "france-no",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
            },
        ]
        redeems = [{
            "condition_id": "france-market",
            "asset": None,
            "amount_usdc": 2000,
        }]

        stats = polymarket_client._compute_wallet_activity_stats(activity, [], redeems)

        self.assertEqual(stats["trade_count"], 2)
        self.assertEqual(stats["resolved_won"], 0)
        self.assertEqual(stats["resolved_lost"], 0)
        self.assertEqual(stats["resolved_total"], 0)
        self.assertIsNone(stats["win_rate"])

    def test_resolved_position_asset_counts_once_without_persisted_fill_result(self):
        activity = [
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 1000,
                "price": 0.5,
                "size": 2000,
                "result": None,
            },
            {
                "wallet": "0xwallet",
                "asset": "france-yes",
                "condition_id": "france-market",
                "action": "BUY",
                "amount_usdc": 1200,
                "price": 0.6,
                "size": 2000,
                "result": None,
            },
        ]
        positions = [{
            "asset": "france-yes",
            "condition_id": "france-market",
            "cur_price": 1.0,
            "current_value": 4000,
            "cash_pnl": 1800,
            "redeemable": True,
        }]

        stats = polymarket_client._compute_wallet_activity_stats(activity, positions, [])

        self.assertEqual(stats["trade_count"], 1)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 0)
        self.assertEqual(stats["resolved_total"], 1)
        self.assertEqual(stats["win_rate"], 100.0)

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
             patch.object(polymarket_client, "_filter_verified_football_items", side_effect=lambda rows: (rows, True)), \
             patch.object(polymarket_client, "_persist_wallet_bet_rows", return_value=True), \
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

    def test_quarantine_key_is_stable_for_same_source_item(self):
        item = {
            "transactionHash": "0xtx",
            "asset": "asset",
            "conditionId": "condition",
            "side": "BUY",
            "timestamp": 123,
        }
        first = polymarket_scraper._sport_quarantine_item_key(
            "activity",
            item,
        )
        second = polymarket_scraper._sport_quarantine_item_key(
            "activity",
            dict(item),
        )
        self.assertEqual(first, second)

    def test_scraper_quarantines_uncertain_without_dropping_verified_activity(self):
        class FakeWriter:
            def __init__(self):
                self.activity = []
                self.quarantine = []
                self.positions = None

            def get_wallet_activity_checkpoint(self, _wallet):
                return None

            def get_wallet_redeem_checkpoint(self, _wallet):
                return None

            def upsert_wallet_activity(self, rows):
                self.activity.extend(rows)
                return True

            def upsert_wallet_redeems(self, _rows):
                return True

            def upsert_sport_quarantine(self, wallet, kind, rows):
                self.quarantine.append((wallet, kind, rows))
                return True

            def replace_wallet_positions(self, _wallet, rows):
                self.positions = rows
                return True

        verified = {
            "transactionHash": "0xfootball",
            "asset": "football-asset",
            "conditionId": "football-condition",
            "eventId": "football-event",
            "title": "Club A vs. Club B",
            "outcome": "Club A",
            "side": "BUY",
            "timestamp": 100,
            "price": 0.5,
            "size": 2000,
            "_sport_classification": "verified_football",
            "_sport_resolved_event_id": "football-event",
        }
        uncertain = {
            "transactionHash": "0xmystery",
            "asset": "mystery-asset",
            "conditionId": "mystery-condition",
            "title": "Unknown",
            "side": "BUY",
            "timestamp": 99,
            "_sport_classification": "uncertain",
            "_sport_reason": "event_tags_missing",
        }

        writer = FakeWriter()
        with patch.object(
            polymarket_scraper,
            "fetch_wallet_activity",
            return_value=([verified], False, [uncertain], []),
        ), patch.object(
            polymarket_scraper,
            "fetch_wallet_redeems",
            return_value=([], False, [], []),
        ), patch.object(
            polymarket_scraper,
            "fetch_wallet_positions",
            return_value=([], True, [], []),
        ), patch.object(
            polymarket_scraper,
            "compute_and_save_wallet_stats",
            return_value=True,
        ):
            polymarket_scraper.process_tracked_wallet(
                writer,
                {"wallet": "0xwallet", "nickname": "bettor"},
            )

        self.assertEqual(len(writer.activity), 1)
        self.assertEqual(writer.activity[0]["asset"], "football-asset")
        self.assertEqual(len(writer.quarantine), 1)
        self.assertEqual(writer.quarantine[0][1], "activity")
        self.assertEqual(
            writer.quarantine[0][2][0]["_sport_reason"],
            "event_tags_missing",
        )

    def test_scraper_computes_stats_when_positions_api_fails(self):
        class FakeWriter:
            def __init__(self):
                self.positions_replaced = False

            def get_wallet_activity_checkpoint(self, _wallet):
                return None

            def get_wallet_redeem_checkpoint(self, _wallet):
                return None

            def upsert_sport_quarantine(self, _wallet, _kind, _rows):
                return True

            def replace_wallet_positions(self, _wallet, _rows):
                self.positions_replaced = True

        writer = FakeWriter()
        computed = []

        with patch.object(polymarket_scraper, "fetch_wallet_activity", return_value=([], False, [], [])), \
             patch.object(polymarket_scraper, "fetch_wallet_redeems", return_value=([], False, [], [])), \
             patch.object(polymarket_scraper, "fetch_wallet_positions", return_value=([], False, [], [])), \
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

    def test_price_snapshot_cadence_tightens_near_kickoff(self):
        self.assertEqual(
            polymarket_scraper._price_snapshot_cadence_minutes(24),
            60,
        )
        self.assertEqual(
            polymarket_scraper._price_snapshot_cadence_minutes(3),
            15,
        )
        self.assertEqual(
            polymarket_scraper._price_snapshot_cadence_minutes(0.5),
            5,
        )

    def test_price_snapshot_bucket_is_deterministic(self):
        now = polymarket_scraper.datetime.fromisoformat(
            "2026-10-02T19:58:41+00:00"
        )
        bucket = polymarket_scraper._price_snapshot_bucket(now, 5)
        self.assertEqual(
            bucket.isoformat(),
            "2026-10-02T19:55:00+00:00",
        )

    def test_price_snapshot_runner_dedupes_assets_and_finalizes_clv(self):
        now = polymarket_scraper.datetime.fromisoformat(
            "2026-10-02T19:30:00+00:00"
        )

        class FakeWriter:
            def __init__(self):
                self.snapshots = []
                self.latest = []
                self.finalized = []

            def get_price_snapshot_candidates(self, _now, _horizon):
                return [
                    {
                        "asset": "asset-a",
                        "condition_id": "condition-a",
                        "event_id": "event-a",
                        "kickoff_utc": "2026-10-02T20:00:00+00:00",
                        "first_traded_at": "2026-10-02T17:00:00+00:00",
                    },
                    {
                        "asset": "asset-a",
                        "condition_id": "condition-a",
                        "event_id": "event-a",
                        "kickoff_utc": "2026-10-02T20:00:00+00:00",
                        "first_traded_at": "2026-10-02T18:00:00+00:00",
                    },
                ]

            def upsert_price_snapshots(self, rows):
                self.snapshots.extend(rows)
                return True

            def update_latest_market_price(self, asset, price, observed_at):
                self.latest.append((asset, price, observed_at))
                return True

            def get_pending_closing_bets(self, _now):
                return []

            def get_last_pre_kickoff_snapshot(self, _asset, _kickoff):
                raise AssertionError("no closing lookup expected")

            def finalize_bet_closing_line(self, *_args):
                raise AssertionError("no finalize expected")

        writer = FakeWriter()
        with patch.object(
            polymarket_scraper,
            "_fetch_clob_midpoints",
            return_value=({"asset-a": 0.60}, True),
        ):
            count = polymarket_scraper.run_tracked_price_snapshots(
                writer,
                now=now,
            )

        self.assertEqual(count, 1)
        self.assertEqual(len(writer.snapshots), 1)
        row = writer.snapshots[0]
        self.assertEqual(row["asset"], "asset-a")
        self.assertEqual(row["market_price"], 0.60)
        self.assertEqual(row["decimal_odds"], 1.67)
        self.assertEqual(row["cadence_minutes"], 5)
        self.assertEqual(len(writer.latest), 1)

    def test_closing_line_uses_recent_pre_kickoff_snapshot_only(self):
        now = polymarket_scraper.datetime.fromisoformat(
            "2026-10-02T20:05:00+00:00"
        )

        class FakeWriter:
            def __init__(self):
                self.finalized = []

            def get_price_snapshot_candidates(self, _now, _horizon):
                return []

            def upsert_price_snapshots(self, _rows):
                return True

            def update_latest_market_price(self, *_args):
                return True

            def get_pending_closing_bets(self, _now):
                return [{
                    "wallet": "0xwallet",
                    "bet_key": '["asset","0xwallet","asset-a"]',
                    "asset": "asset-a",
                    "kickoff_utc": "2026-10-02T20:00:00+00:00",
                    "first_traded_at": "2026-10-02T18:00:00+00:00",
                    "last_traded_at": "2026-10-02T19:10:00+00:00",
                    "avg_entry_price": 0.50,
                }]

            def get_last_pre_kickoff_snapshot(self, asset, kickoff):
                self.lookup = (asset, kickoff)
                return {
                    "market_price": 0.60,
                    "observed_at": "2026-10-02T19:58:00+00:00",
                    "source": "clob_midpoint",
                }

            def finalize_bet_closing_line(
                self,
                wallet,
                bet_key,
                closing_price,
                observed_at,
                metrics,
            ):
                self.finalized.append(
                    (wallet, bet_key, closing_price, observed_at, metrics)
                )
                return True

        writer = FakeWriter()
        with patch.object(
            polymarket_scraper,
            "_fetch_clob_midpoints",
            return_value=({}, True),
        ):
            polymarket_scraper.run_tracked_price_snapshots(writer, now=now)

        self.assertEqual(len(writer.finalized), 1)
        saved = writer.finalized[0]
        self.assertEqual(saved[2], 0.60)
        self.assertEqual(saved[4]["clv_probability_pp"], 10.0)
        self.assertEqual(saved[4]["clv_pct"], 20.0)

    def test_clv_is_not_finalized_for_lifecycle_with_live_activity(self):
        kickoff = polymarket_scraper.datetime.fromisoformat(
            "2026-10-02T20:00:00+00:00"
        )
        bet = {
            "first_traded_at": "2026-10-02T18:00:00+00:00",
            "last_traded_at": "2026-10-02T20:03:00+00:00",
        }

        self.assertFalse(
            polymarket_scraper._is_clv_eligible_lifecycle(bet, kickoff)
        )

    def test_wallet_resume_checkpoint_prefers_last_successful_sync(self):
        writer = polymarket_scraper.PolymarketSupabaseWriter(
            "https://supabase.test",
            "key",
        )

        def fake_get(url, **_kwargs):
            if "tracked_wallet_activity" in url:
                return FakeResponse(200, [])
            if "tracked_wallet_redeems" in url:
                return FakeResponse(200, [])
            if "tracked_wallets" in url:
                return FakeResponse(200, [{
                    "created_at": "2026-01-01T00:00:00+00:00",
                    "last_synced_at": "2026-10-01T12:34:56+00:00",
                }])
            raise AssertionError(url)

        expected = int(
            polymarket_scraper.datetime.fromisoformat(
                "2026-10-01T12:34:56+00:00"
            ).timestamp()
        )
        with patch.object(
            polymarket_scraper.requests,
            "get",
            side_effect=fake_get,
        ):
            self.assertEqual(
                writer.get_wallet_activity_checkpoint("0xwallet"),
                expected,
            )
            self.assertEqual(
                writer.get_wallet_redeem_checkpoint("0xwallet"),
                expected,
            )

    def test_wallet_resume_checkpoint_first_sync_falls_back_to_created_at(self):
        writer = polymarket_scraper.PolymarketSupabaseWriter(
            "https://supabase.test",
            "key",
        )

        with patch.object(
            polymarket_scraper.requests,
            "get",
            return_value=FakeResponse(200, [{
                "created_at": "2026-09-01T00:00:00+00:00",
                "last_synced_at": None,
            }]),
        ):
            checkpoint = writer.get_wallet_resume_checkpoint("0xwallet")

        expected = int(
            polymarket_scraper.datetime.fromisoformat(
                "2026-09-01T00:00:00+00:00"
            ).timestamp()
        )
        self.assertEqual(checkpoint, expected)

    def test_poly_cleanup_uses_tiered_retention_and_never_deletes_bets(self):
        class FakeWriter:
            def __init__(self):
                self.deletes = []

            def delete_before(self, table, date_column, cutoff):
                self.deletes.append((table, date_column, cutoff))
                return 0

        writer = FakeWriter()
        original_timedelta = polymarket_scraper.timedelta
        timedelta_calls = []

        def capture_timedelta(*args, **kwargs):
            timedelta_calls.append((args, kwargs))
            return original_timedelta(*args, **kwargs)

        with patch.object(
            polymarket_scraper,
            "timedelta",
            side_effect=capture_timedelta,
        ):
            self.assertEqual(polymarket_scraper.cleanup_old_poly_data(writer), 0)

        days = [kwargs.get("days") for _args, kwargs in timedelta_calls]
        self.assertEqual(
            days,
            [
                polymarket_scraper.POLYMARKET_TRADE_RETENTION_DAYS,
                polymarket_scraper.TRACKED_WALLET_RAW_RETENTION_DAYS,
            ],
        )
        deleted_tables = [
            table for table, _column, _cutoff in writer.deletes
        ]
        self.assertEqual(
            deleted_tables,
            [
                "polymarket_trades",
                "tracked_wallet_activity",
                "tracked_wallet_redeems",
            ],
        )
        self.assertNotIn("tracked_wallet_bets", deleted_tables)
        self.assertTrue(
            all(
                column == "traded_at"
                for _table, column, _cutoff in writer.deletes
            )
        )


if __name__ == "__main__":
    unittest.main()