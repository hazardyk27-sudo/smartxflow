from __future__ import annotations

from datetime import datetime, timedelta, timezone
import unittest

from predictor_orchestrator.sxf_source import SXFSourceError, SXFStage1Source


class FakeSXFSource(SXFStage1Source):
    def __init__(self):
        self.fixture_rows = [
            {
                "match_id_hash": "m1",
                "home_team": "Home",
                "away_team": "Away",
                "league": "League",
                "kickoff_utc": "2026-10-07T20:00:00+00:00",
            }
        ]
        self.market_rows = {
            "moneyway_1x2_history": [
                {"match_id_hash":"m1","odds1":"2.10","oddsx":"3.30","odds2":"3.60","pct1":"55%","pctx":"20%","pct2":"25%","amt1":"£55","amtx":"£20","amt2":"£25","volume":"£100","scraped_at":"2026-10-07T18:00:00+00:00"},
                {"match_id_hash":"m1","odds1":"1.90","oddsx":"3.50","odds2":"4.00","pct1":"75%","pctx":"15%","pct2":"10%","amt1":"£225","amtx":"£45","amt2":"£30","volume":"£300","scraped_at":"2026-10-07T19:30:00+00:00"},
            ],
            "moneyway_ou25_history": [
                {"match_id_hash":"m1","under":"2.00","over":"2.00","pctunder":"50%","pctover":"50%","amtunder":"£25","amtover":"£25","volume":"£50","scraped_at":"2026-10-07T18:00:00+00:00"},
                {"match_id_hash":"m1","under":"2.20","over":"1.82","pctunder":"30%","pctover":"70%","amtunder":"£30","amtover":"£70","volume":"£100","scraped_at":"2026-10-07T19:30:00+00:00"},
            ],
            "moneyway_btts_history": [],
        }

    def close(self):
        pass

    def _fixtures_window(self, start_utc, end_utc):
        return list(self.fixture_rows)

    def _history_rows(self, table, select, hashes):
        return list(self.market_rows.get(table, []))


class BatchProbeSource(SXFStage1Source):
    def __init__(self, *, timeout_above: int | None = None):
        self.timeout_above = timeout_above
        self.request_batch_sizes: list[int] = []

    def _get(self, table, params):
        encoded = str(params["match_id_hash"])
        inner = encoded.removeprefix("in.(").removesuffix(")")
        batch = [item for item in inner.split(",") if item]
        self.request_batch_sizes.append(len(batch))
        if self.timeout_above is not None and len(batch) > self.timeout_above:
            raise SXFSourceError(
                f'{table} read failed: HTTP 500: {{"code":"57014","message":"canceling statement due to statement timeout"}}'
            )
        return [{"match_id_hash": item} for item in batch]


class SXFStage1SourceTests(unittest.TestCase):
    def test_server_context_binds_native_prices_to_fixture(self):
        source = FakeSXFSource()
        context = source.build_stage1_context(
            {"date":"2026-10-07","window_tr":["21:00","24:00"],"timezone":"Europe/Istanbul","future_only":False},
            now=datetime(2026,10,7,19,40,tzinfo=timezone.utc),
        )
        self.assertEqual(context["source_fixture_ids"], ["m1"])
        prices = {(p["fixture_id"],p["market"],p["selection"]):p["price"] for p in context["price_evidence"]}
        self.assertEqual(prices[("m1","1X2","Home")], 1.90)
        self.assertEqual(prices[("m1","OU2.5","Over 2.5")], 1.82)
        self.assertTrue(all(p["fixture_id"] == "m1" for p in context["price_evidence"]))

    def test_temporal_features_include_late_and_open_deltas(self):
        source = FakeSXFSource()
        context = source.build_stage1_context(
            {"date":"2026-10-07","window_tr":["21:00","24:00"],"timezone":"Europe/Istanbul","future_only":False},
            now=datetime(2026,10,7,19,40,tzinfo=timezone.utc),
        )
        home = context["fixtures"][0]["markets"]["1X2"]["Home"]
        self.assertAlmostEqual(home["open_to_latest"]["odds_delta"], -0.2)
        self.assertAlmostEqual(home["open_to_latest"]["share_delta"], 20.0)
        self.assertAlmostEqual(home["open_to_latest"]["amount_delta"], 170.0)
        self.assertEqual(home["last"]["odds"], 1.9)
        self.assertGreaterEqual(home["history_count"], 2)
        for checkpoint in ("h24", "h12", "h6", "h3", "h1", "m30", "m15"):
            self.assertIn(checkpoint, home)
            self.assertIn(f"{checkpoint}_to_latest", home)
        self.assertIsNone(home["h24"])
        self.assertIsNone(home["h12"])
        self.assertIsNone(home["h6"])
        self.assertIsNone(home["h3"])

    def test_temporal_features_resolve_expanded_checkpoint_ladder(self):
        now = datetime(2026, 10, 8, 0, 0, tzinfo=timezone.utc)
        samples = [
            (timedelta(hours=24, minutes=30), 2.50, 10, 10),
            (timedelta(hours=12, minutes=30), 2.40, 20, 20),
            (timedelta(hours=6, minutes=30), 2.30, 30, 30),
            (timedelta(hours=3, minutes=30), 2.20, 40, 40),
            (timedelta(hours=1, minutes=30), 2.10, 50, 50),
            (timedelta(minutes=40), 2.00, 60, 60),
            (timedelta(minutes=20), 1.90, 70, 70),
            (timedelta(minutes=5), 1.80, 80, 80),
        ]
        rows = [
            {
                "odds1": str(odds),
                "pct1": str(share),
                "amt1": str(amount),
                "volume": str(amount),
                "scraped_at": (now - age).isoformat(),
            }
            for age, odds, share, amount in samples
        ]

        feature = SXFStage1Source._selection_feature(rows, "odds1", "pct1", "amt1", now)

        self.assertIsNotNone(feature)
        self.assertEqual(feature["first"]["odds"], 2.5)
        self.assertEqual(feature["h24"]["odds"], 2.5)
        self.assertEqual(feature["h12"]["odds"], 2.4)
        self.assertEqual(feature["h6"]["odds"], 2.3)
        self.assertEqual(feature["h3"]["odds"], 2.2)
        self.assertEqual(feature["h1"]["odds"], 2.1)
        self.assertEqual(feature["m30"]["odds"], 2.0)
        self.assertEqual(feature["m15"]["odds"], 1.9)
        self.assertEqual(feature["last"]["odds"], 1.8)
        self.assertAlmostEqual(feature["h24_to_latest"]["odds_delta"], -0.7)
        self.assertAlmostEqual(feature["m15_to_latest"]["amount_delta"], 10.0)

    def test_future_only_moves_start_to_now_for_today(self):
        source = FakeSXFSource()
        context = source.build_stage1_context(
            {"date":"2026-10-07","window_tr":["18:00","24:00"],"timezone":"Europe/Istanbul","future_only":True},
            now=datetime(2026,10,7,19,40,tzinfo=timezone.utc),
        )
        self.assertEqual(context["window"]["start"], "2026-10-07T22:40:00+03:00")

    def test_history_requests_are_bounded_to_eight_fixture_ids(self):
        source = BatchProbeSource()
        rows = source._history_rows("moneyway_ou25_history", "match_id_hash,scraped_at", [f"m{i}" for i in range(17)])
        self.assertEqual(source.request_batch_sizes, [8, 8, 1])
        self.assertEqual(len(rows), 17)

    def test_statement_timeout_splits_batch_without_duplicate_rows(self):
        source = BatchProbeSource(timeout_above=2)
        rows = source._history_rows("moneyway_ou25_history", "match_id_hash,scraped_at", [f"m{i}" for i in range(5)])
        self.assertEqual(sorted(row["match_id_hash"] for row in rows), ["m0", "m1", "m2", "m3", "m4"])
        self.assertIn(5, source.request_batch_sizes)
        self.assertTrue(all(size <= 2 for size in source.request_batch_sizes if size != 5 and size != 3))
        self.assertIn(3, source.request_batch_sizes)


if __name__ == "__main__":
    unittest.main()
