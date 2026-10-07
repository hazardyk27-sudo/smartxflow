from __future__ import annotations

import unittest

from learning_archive.postmatch_diary import PostmatchDiaryWriter, build_postmatch_diary_entry
from scripts.settle_due_learning_cases_with_diary import _enqueue_finalized, _pending_map


class PostmatchDiaryTests(unittest.TestCase):
    @staticmethod
    def case():
        return {
            "archive_schema_version": 1,
            "case_id": "20261008-abc123def456-test",
            "match": {
                "match_id_hash": "abc123def456",
                "league": "Test League",
                "home": "Home",
                "away": "Away",
                "kickoff_at": "2026-10-08T18:00:00+00:00",
            },
            "prediction": {
                "prediction_at": "2026-10-08T17:00:00+00:00",
                "decision": "WATCH",
                "market": "Double Chance",
                "selection": "Home 1X",
                "entry_odds": 1.55,
                "confidence": 63,
                "rationale": "Protection preserves the home-side thesis.",
                "counterargument": "Straight home win still carries draw risk.",
                "stage1_baseline": {"market": "1X2", "selection": "Home", "price": 1.91},
                "change_driver": "EXECUTION_OPTIMIZATION",
            },
            "provenance": {
                "archive_created_at": "2026-10-08T17:00:00+00:00",
                "source_repo": "hazardyk27-sudo/smartxflow",
                "source_commit": "a" * 40,
            },
        }

    @staticmethod
    def snapshots():
        return [
            {
                "match_id_hash": "abc123def456",
                "_archive_source_table": "moneyway_1x2_history",
                "scraped_at": "2026-10-08T17:45:00+00:00",
                "odds1": 2.0,
                "pct1": 61.0,
                "amt1": 610.0,
                "volume": 1000.0,
            }
        ]

    def test_postmatch_entry_records_stage1_vs_stage3_transition(self):
        settlement = {
            "status": "NO_BET",
            "final_score": "1-1",
            "hypothetical_result": "WIN",
        }
        entry = build_postmatch_diary_entry(
            case=self.case(),
            evidence=[
                {
                    "source": "official.example",
                    "note": "Support",
                    "observed_at": "2026-10-08T16:30:00+00:00",
                    "relationship": "SUPPORTS",
                },
                {
                    "source": "official.example",
                    "note": "Counter",
                    "observed_at": "2026-10-08T16:40:00+00:00",
                    "relationship": "CONTRADICTS",
                },
            ],
            settlement=settlement,
            snapshots=self.snapshots(),
            observed_at="2026-10-08T20:00:00+00:00",
        )
        comparison = entry["stage_comparison"]
        self.assertEqual(comparison["status"], "RESOLVED")
        self.assertEqual(comparison["stage1"]["result"], "LOSS")
        self.assertEqual(comparison["stage3"]["result"], "WIN")
        self.assertEqual(comparison["transition"], "IMPROVED")
        self.assertIn("Stage 2 archived evidence", entry["why_it_won_lost"])

    def test_diary_content_is_case_idempotent_and_contains_comparison_snapshot(self):
        settlement = {"status": "NO_BET", "final_score": "1-1", "hypothetical_result": "WIN"}
        entry = build_postmatch_diary_entry(
            case=self.case(),
            evidence=[],
            settlement=settlement,
            snapshots=self.snapshots(),
            observed_at="2026-10-08T20:00:00+00:00",
        )
        first, case_ids = PostmatchDiaryWriter._content("", [entry])
        self.assertEqual(case_ids, [self.case()["case_id"]])
        self.assertIn("Why it won/lost", first)
        self.assertIn("Stage 1 vs Stage 3 matched comparison snapshot", first)
        second, repeated_ids = PostmatchDiaryWriter._content(first, [entry])
        self.assertEqual(repeated_ids, [self.case()["case_id"]])
        self.assertEqual(second, first)

    def test_finalized_cases_enter_durable_diary_outbox_before_write(self):
        queue = {"version": 1, "settlements": {}}
        result = {
            "cases": [
                {"case_id": "case-done", "status": "DONE"},
                {"case_id": "case-not-done", "status": "PENDING"},
            ]
        }
        added = _enqueue_finalized(queue, result, "2026-10-08T20:00:00Z")
        self.assertEqual(added, 1)
        pending = _pending_map(queue)
        self.assertEqual(sorted(pending), ["case-done"])
        self.assertEqual(pending["case-done"]["observed_at"], "2026-10-08T20:00:00Z")
        self.assertEqual(_enqueue_finalized(queue, result, "2026-10-08T20:05:00Z"), 0)
        self.assertEqual(pending["case-done"]["observed_at"], "2026-10-08T20:00:00Z")


if __name__ == "__main__":
    unittest.main()
