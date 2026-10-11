import unittest
from unittest.mock import patch

from services import polymarket_profile_v42_patch as p42


class _FakeClient:
    TRACKED_WALLET_API_CONTRACT_VERSION = "old"


def _profile(snapshot_count=13, open_count=11, missing=7):
    rows = []
    for i in range(open_count):
        row = {
            "asset": f"asset-{i}",
            "current_value": 100 + i,
            "snapshot_missing": i < missing,
        }
        rows.append(row)
    return {
        "contract_version": "2026-10-10.v4.1-bounded-profile",
        "stats": {
            "bet_count": 2869,
            "trade_count": 2869,
            "total_invested_usdc": 1000000,
            "resolved_total": 100,
            "win_rate_pct": 55.0,
            "open_position_count": snapshot_count,
            "open_exposure_usdc": 50000,
        },
        "coverage": {"history_source": "tracked_wallet_bets"},
        "summary": ["stale"],
        "open_positions": rows,
        "bets": [],
    }


class PolymarketProfileV42Tests(unittest.TestCase):
    def test_open_count_uses_canonical_open_rows_not_stale_snapshot(self):
        with patch.object(p42.v41, "get_wallet_profile_v41", return_value=_profile()):
            profile = p42.get_wallet_profile_v42("0xwallet")

        self.assertEqual(profile["contract_version"], "2026-10-11.v4.2-open-count-ledger")
        self.assertEqual(profile["stats"]["open_position_count"], 11)
        self.assertEqual(profile["coverage"]["open_position_count_snapshot"], 13)
        self.assertTrue(profile["coverage"]["open_position_count_reconciled"])
        self.assertEqual(profile["coverage"]["open_position_snapshot_missing_count"], 7)
        self.assertFalse(profile["coverage"]["open_exposure_complete"])
        self.assertEqual(profile["coverage"]["open_exposure_source"], "persisted_snapshot_partial")
        self.assertIn("11 canonical açık bahsi", profile["summary"][-1])
        self.assertIn("7 pozisyon snapshot", profile["summary"][-1])
        self.assertEqual(profile["stats"]["open_exposure_usdc"], 50000)

    def test_exposure_recomputed_when_all_open_snapshots_are_complete(self):
        source = _profile(snapshot_count=2, open_count=2, missing=0)
        with patch.object(p42.v41, "get_wallet_profile_v41", return_value=source):
            profile = p42.get_wallet_profile_v42("0xwallet")

        self.assertEqual(profile["stats"]["open_position_count"], 2)
        self.assertFalse(profile["coverage"]["open_position_count_reconciled"])
        self.assertTrue(profile["coverage"]["open_exposure_complete"])
        self.assertEqual(profile["coverage"]["open_exposure_source"], "canonical_open_positions")
        self.assertEqual(profile["stats"]["open_exposure_usdc"], 201.0)

    def test_bind_overrides_profile_reader(self):
        client = _FakeClient()
        with patch.object(p42, "_client", return_value=client):
            p42.bind_polymarket_profile_v42_patch()
        self.assertIs(client.get_wallet_profile, p42.get_wallet_profile_v42)
        self.assertEqual(
            client.TRACKED_WALLET_API_CONTRACT_VERSION,
            "2026-10-11.v4.2-open-count-ledger",
        )


if __name__ == "__main__":
    unittest.main()
