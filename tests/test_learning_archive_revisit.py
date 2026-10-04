import unittest

from learning_archive.revisit import RevisitCaptureError, prepare_revisit_snapshots


class LearningArchiveRevisitTests(unittest.TestCase):
    def setUp(self):
        self.case = {
            "prediction": {"prediction_at": "2026-10-04T14:18:36Z"},
            "match": {"kickoff_at": "2026-10-04T16:00:00Z"},
        }

    def test_filters_rows_after_requested_observed_at(self):
        snapshots = [
            {"match_id_hash": "x", "scraped_at_utc": "2026-10-04T15:20:00Z", "odds": 1.9},
            {"match_id_hash": "x", "scraped_at": "2026-10-04T18:25:00+03:00", "odds": 1.8},
            {"match_id_hash": "x", "scraped_at_utc": "2026-10-04T15:40:00Z", "odds": 1.7},
        ]
        result = prepare_revisit_snapshots(
            self.case,
            snapshots,
            "2026-10-04T15:35:00Z",
        )
        self.assertEqual([row["odds"] for row in result], [1.9, 1.8])

    def test_rejects_post_kickoff_capture(self):
        with self.assertRaisesRegex(RevisitCaptureError, "strictly before kickoff_at"):
            prepare_revisit_snapshots(
                self.case,
                [{"scraped_at_utc": "2026-10-04T15:30:00Z"}],
                "2026-10-04T16:00:00Z",
            )

    def test_rejects_cutoff_not_later_than_prediction(self):
        with self.assertRaisesRegex(RevisitCaptureError, "later than prediction_at"):
            prepare_revisit_snapshots(
                self.case,
                [{"scraped_at_utc": "2026-10-04T14:10:00Z"}],
                "2026-10-04T14:18:36Z",
            )

    def test_rejects_snapshot_without_timestamp(self):
        with self.assertRaisesRegex(RevisitCaptureError, "missing an observed timestamp"):
            prepare_revisit_snapshots(
                self.case,
                [{"odds": 2.0}],
                "2026-10-04T15:35:00Z",
            )

    def test_rejects_when_no_history_exists_by_cutoff(self):
        with self.assertRaisesRegex(RevisitCaptureError, "no stored SXF history"):
            prepare_revisit_snapshots(
                self.case,
                [{"scraped_at_utc": "2026-10-04T15:40:00Z"}],
                "2026-10-04T15:35:00Z",
            )


if __name__ == "__main__":
    unittest.main()
