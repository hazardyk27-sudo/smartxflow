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
            self.assertTrue(url.endswith("/markets"))
            self.assertEqual(params["tag_id"], polymarket_client.SOCCER_TAG_ID)
            self.assertEqual(params["related_tags"], "false")
            self.assertEqual(
                set(params["condition_ids"]),
                {"soccer-condition", "politics-condition"},
            )
            return [{"conditionId": "soccer-condition"}]

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_get_json", side_effect=fake_json):
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

        with patch.object(polymarket_client, "_get_json", side_effect=fake_json):
            filtered, ok = polymarket_client._filter_verified_football_items(items)

        self.assertTrue(ok)
        self.assertEqual(filtered, items)

    def test_registry_failure_is_not_treated_as_verified_nonfootball(self):
        items = [{"conditionId": "soccer-condition", "title": "Club A vs. Club B"}]

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_get_json", return_value=None):
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
            if url.endswith("/markets"):
                self.assertEqual(params["tag_id"], polymarket_client.SOCCER_TAG_ID)
                return [{"conditionId": "soccer-condition"}]
            raise AssertionError(url)

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
            if url.endswith("/markets"):
                self.assertEqual(params["tag_id"], polymarket_client.SOCCER_TAG_ID)
                return [{"conditionId": "soccer-condition"}]
            raise AssertionError(url)

        with polymarket_client._soccer_registry_lock:
            polymarket_client._soccer_condition_registry_cache.clear()
            polymarket_client._soccer_event_registry_cache.clear()

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://supabase.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "test"}), \
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

    def test_poly_cleanup_keeps_last_seven_days_of_wallet_history(self):
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

        self.assertEqual(timedelta_calls, [((), {"days": 7})])
        self.assertEqual(
            [table for table, _column, _cutoff in writer.deletes],
            [
                "tracked_wallet_activity",
                "tracked_wallet_redeems",
                "polymarket_trades",
            ],
        )
        self.assertTrue(all(column == "traded_at" for _table, column, _cutoff in writer.deletes))


if __name__ == "__main__":
    unittest.main()