import unittest
from unittest.mock import patch

from services import polymarket_profile_v41_patch as p41


class _FakeClient:
    MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC = 1000
    TRACKED_WALLET_CANONICAL_RETENTION = "durable"
    TRACKED_WALLET_RAW_RETENTION_DAYS = 365
    TRACKED_WALLET_CLOSING_LINE_SOURCE = "snapshot"

    def _supabase_base_url(self):
        return "https://example.supabase.co"

    def _supabase_headers(self):
        return {"apikey": "x"}

    def _to_decimal_odds(self, p):
        return round(1 / p, 2) if p else None

    def _persisted_wallet_bet_to_display(self, row):
        return dict(row)

    def _wallet_bet_api_contract(self, row):
        return {
            "bet_id": row.get("bet_key"),
            "asset_id": row.get("asset"),
            "result": row.get("result"),
            "lifecycle_status": row.get("lifecycle_status"),
            "stake_usdc": row.get("stake_usdc"),
        }

    def _validate_wallet_profile_contract(self, stats, bets, coverage):
        return {"status": "ok", "issue_count": 0}


def _wallet_row():
    return {
        "wallet": "0xwallet",
        "nickname": "Large bettor",
        "notes": None,
        "created_at": "2026-10-01T00:00:00+00:00",
        "last_synced_at": "2026-10-10T17:00:00+00:00",
        "win_rate": 60.0,
        "resolved_won": 6,
        "resolved_lost": 4,
        "resolved_total": 10,
        "trade_count": 2869,
        "total_invested_usdc": 1000000,
        "avg_bet_size_usdc": 348.55,
        "avg_price": 0.5,
        "avg_price_decimal": 2.0,
        "open_position_count": 8,
        "open_exposure_usdc": 12345.67,
    }


class PolymarketProfileV41Tests(unittest.TestCase):
    def test_profile_is_bounded_and_omits_duplicate_activity(self):
        client = _FakeClient()
        history = [
            {
                "bet_key": f"bet-{i}",
                "asset": f"asset-{i}",
                "stake_usdc": 1000,
                "result": "unknown",
                "lifecycle_status": "resolved",
            }
            for i in range(250)
        ]
        open_rows = [
            {
                "bet_key": "open-1",
                "asset": "asset-open",
                "stake_usdc": 2500,
                "result": "unknown",
                "lifecycle_status": "open",
            }
        ]
        with patch.object(p41, "_client", return_value=client), \
             patch.object(p41.v4, "_fetch_wallet_row", return_value=_wallet_row()), \
             patch.object(p41, "_fetch_history_page", return_value=(history, True)), \
             patch.object(p41, "_fetch_open_bets", return_value=(open_rows, True)), \
             patch.object(p41.v4, "_fetch_positions_for_assets", return_value=([], True)), \
             patch.object(p41.v4, "_open_position_rows", return_value=[{"asset": "asset-open"}]):
            profile = p41.get_wallet_profile_v41("0xwallet")

        self.assertEqual(profile["contract_version"], "2026-10-10.v4.1-bounded-profile")
        self.assertEqual(len(profile["bets"]), 250)
        self.assertNotIn("activity", profile)
        self.assertEqual(profile["stats"]["bet_count"], 2869)
        self.assertEqual(profile["stats"]["open_position_count"], 8)
        self.assertEqual(len(profile["open_positions"]), 1)
        self.assertEqual(profile["coverage"]["expected_bet_count"], 2869)
        self.assertEqual(profile["coverage"]["returned_bet_count"], 250)
        self.assertTrue(profile["coverage"]["history_more_available"])
        self.assertTrue(profile["coverage"]["open_history_complete"])

    def test_stats_use_full_persisted_snapshot_not_visible_window(self):
        client = _FakeClient()
        stats = p41._stats_from_wallet_row(client, _wallet_row())
        self.assertEqual(stats["trade_count"], 2869)
        self.assertEqual(stats["resolved_total"], 10)
        self.assertEqual(stats["open_position_count"], 8)
        self.assertEqual(stats["open_exposure_usdc"], 12345.67)


if __name__ == "__main__":
    unittest.main()
