from __future__ import annotations

from copy import deepcopy
import unittest

from predictor_orchestrator.archive_wrapper import EnrichedStage3ArchivePublisher


class CapturePublisher:
    def __init__(self):
        self.kwargs = None

    def publish(self, **kwargs):
        self.kwargs = deepcopy(kwargs)
        return {"status": "RECORDED", "cases": [], "diary_status": "RECORDED"}


class PredictorArchiveWrapperTests(unittest.TestCase):
    def test_full_accepted_stage1_preference_including_price_is_preserved(self):
        inner = CapturePublisher()
        wrapper = EnrichedStage3ArchivePublisher(inner)
        wrapper.publish(
            stage1_payload={
                "matches": [
                    {
                        "fixture_id": "abc123def456",
                        "preference": {"market": "1X2", "selection": "Home", "price": 1.91},
                    }
                ]
            },
            stage3_payload={
                "matches": [
                    {
                        "fixture_id": "abc123def456",
                        "stage1_baseline": {"market": "1X2", "selection": "Home"},
                    }
                ]
            },
        )
        baseline = inner.kwargs["stage3_payload"]["matches"][0]["stage1_baseline"]
        self.assertEqual(baseline, {"market": "1X2", "selection": "Home", "price": 1.91})


if __name__ == "__main__":
    unittest.main()
