import unittest
from unittest.mock import patch

from services import polymarket_client
from services import polymarket_lifecycle_v4_patch as v4


class PolymarketLifecycleV4Tests(unittest.TestCase):
    def _wallet_row(self, trade_count=2, open_count=1):
        return {
            "wallet": "0xwallet",
            "nickname": "Tester",
            "created_at": "2026-10-01T00:00:00+00:00",
            "last_synced_at": "2026-10-10T12:00:00+00:00",
            "trade_count": trade_count,
            "open_position_count": open_count,
            "open_exposure_usdc": 500.0,
        }

    def _bet(self, asset, result, lifecycle, stake=1000.0):
        return {
            "bet_key": f"bet-{asset}",
            "asset": asset,
            "condition_id": f"condition-{asset}",
            "event_id": f"event-{asset}",
            "match_name": f"Match {asset}",
            "title": f"Match {asset}",
            "market_type": "1x2",
            "market_label": "1X2",
            "selection": "Home",
            "selection_label": "Home",
            "bet_label": "Home",
            "lifecycle_status": lifecycle,
            "result": result,
            "status_label": "Açık" if lifecycle == "open" else "Kazandı",
            "stake_usdc": stake,
            "avg_entry_price": 0.5,
            "avg_entry_decimal": 2.0,
            "redeem_proceeds_usdc": 0.0,
            "pnl_usdc": None,
            "pnl_kind": None,
            "fill_count": 1,
            "buy_fill_count": 1,
            "sell_fill_count": 0,
            "last_traded_at": "2026-10-10T10:00:00+00:00",
        }

    def test_profile_uses_normalized_history_and_targeted_open_positions(self):
        open_bet = self._bet("asset-open", "open", "open")
        won_bet = self._bet("asset-won", "won", "resolved")
        position = {
            "asset": "asset-open",
            "condition_id": "condition-asset-open",
            "current_value": 525.0,
            "cash_pnl": 25.0,
            "avg_price": 0.5,
            "cur_price": 0.525,
        }

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://db.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "x"}), \
             patch.object(v4, "_fetch_wallet_row", return_value=self._wallet_row()), \
             patch.object(v4, "_fetch_normalized_bets", return_value=([open_bet, won_bet], True)), \
             patch.object(v4, "_fetch_positions_for_assets", return_value=([position], True)), \
             patch.object(polymarket_client, "_persisted_wallet_bet_to_display", side_effect=lambda row: dict(row)), \
             patch.object(polymarket_client, "_wallet_bet_api_contract", side_effect=lambda row: dict(row)), \
             patch.object(polymarket_client, "_with_wallet_bet_display_metadata", side_effect=lambda row: dict(row)), \
             patch.object(polymarket_client, "_validate_wallet_profile_contract", return_value={"status": "ok", "issue_count": 0, "issues": []}):
            profile = v4.get_wallet_profile_v4("0xwallet")

        self.assertEqual(profile["coverage"]["history_source"], "tracked_wallet_bets")
        self.assertTrue(profile["coverage"]["history_complete"])
        self.assertEqual(profile["coverage"]["returned_bet_count"], 2)
        self.assertEqual(len(profile["bets"]), 2)
        self.assertEqual(profile["stats"]["open_position_count"], 1)
        self.assertEqual(profile["stats"]["open_exposure_usdc"], 525.0)
        self.assertEqual(len(profile["open_positions"]), 1)
        self.assertEqual(profile["open_positions"][0]["match_name"], "Match asset-open")
        self.assertFalse(profile["open_positions"][0]["snapshot_missing"])

    def test_profile_synthesizes_open_row_when_snapshot_detail_is_missing(self):
        open_bet = self._bet("asset-open", "open", "open")
        wallet_row = self._wallet_row(trade_count=1, open_count=1)

        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://db.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "x"}), \
             patch.object(v4, "_fetch_wallet_row", return_value=wallet_row), \
             patch.object(v4, "_fetch_normalized_bets", return_value=([open_bet], True)), \
             patch.object(v4, "_fetch_positions_for_assets", return_value=([], True)), \
             patch.object(polymarket_client, "_persisted_wallet_bet_to_display", side_effect=lambda row: dict(row)), \
             patch.object(polymarket_client, "_wallet_bet_api_contract", side_effect=lambda row: dict(row)), \
             patch.object(polymarket_client, "_with_wallet_bet_display_metadata", side_effect=lambda row: dict(row)), \
             patch.object(polymarket_client, "_validate_wallet_profile_contract", return_value={"status": "ok", "issue_count": 0, "issues": []}):
            profile = v4.get_wallet_profile_v4("0xwallet")

        self.assertEqual(len(profile["open_positions"]), 1)
        self.assertTrue(profile["open_positions"][0]["snapshot_missing"])
        self.assertEqual(profile["open_positions"][0]["match_name"], "Match asset-open")
        self.assertEqual(profile["stats"]["open_position_count"], 1)
        self.assertEqual(profile["stats"]["open_exposure_usdc"], 500.0)

    def test_clob_reconciliation_resolves_unknown_and_stale_open_rows(self):
        unknown = self._bet("asset-a", "unknown", "unknown")
        unknown["condition_id"] = "cid-a"
        stale_open = self._bet("asset-b", "open", "open")
        stale_open["condition_id"] = "cid-b"
        persisted = []

        def fake_resolution(cid):
            if cid == "cid-a":
                return {"asset-a": True}
            if cid == "cid-b":
                return {"asset-b": False}
            return None

        def fake_persist(_base, _headers, _wallet, rows):
            persisted.extend(dict(row) for row in rows)
            return True

        with patch.object(polymarket_client, "_fetch_market_resolution", side_effect=fake_resolution), \
             patch.object(polymarket_client, "_persist_wallet_bet_rows", side_effect=fake_persist):
            result = v4._reconcile_rows(
                polymarket_client,
                "https://db.test",
                {"apikey": "x"},
                "0xwallet",
                [unknown, stale_open],
                max_condition_ids=None,
                apply=True,
            )

        self.assertEqual(result["resolved_rows"], 2)
        by_asset = {row["asset"]: row for row in persisted}
        self.assertEqual(by_asset["asset-a"]["result"], "won")
        self.assertEqual(by_asset["asset-a"]["lifecycle_status"], "resolved")
        self.assertEqual(by_asset["asset-b"]["result"], "lost")
        self.assertEqual(by_asset["asset-b"]["lifecycle_status"], "resolved")

    def test_normalized_stats_ignore_unrelated_position_snapshot_rows(self):
        won = self._bet("asset-w", "won", "resolved", 1200)
        lost = self._bet("asset-l", "lost", "resolved", 1800)
        open_bet = self._bet("asset-o", "open", "open", 2000)
        positions = [
            {"asset": "asset-o", "current_value": 1500},
            {"asset": "unrelated-1", "current_value": 999999},
            {"asset": "unrelated-2", "current_value": 999999},
        ]

        stats = v4._normalized_stats(
            polymarket_client,
            [won, lost, open_bet],
            positions,
            self._wallet_row(trade_count=3, open_count=1),
        )

        self.assertEqual(stats["trade_count"], 3)
        self.assertEqual(stats["resolved_won"], 1)
        self.assertEqual(stats["resolved_lost"], 1)
        self.assertEqual(stats["open_position_count"], 1)
        self.assertEqual(stats["open_exposure_usdc"], 1500.0)

    def test_failed_incremental_refresh_does_not_advance_last_synced(self):
        wallet_row = self._wallet_row()
        with patch.object(polymarket_client, "_supabase_base_url", return_value="https://db.test"), \
             patch.object(polymarket_client, "_supabase_headers", return_value={"apikey": "x"}), \
             patch.object(v4, "_fetch_wallet_row", return_value=wallet_row), \
             patch.object(v4, "_refresh_touched_normalized", return_value=False), \
             patch.object(v4, "_patch_wallet_stats") as patch_stats:
            ok = v4.compute_and_save_wallet_stats_v4("0xwallet")

        self.assertFalse(ok)
        patch_stats.assert_not_called()


if __name__ == "__main__":
    unittest.main()
