from __future__ import annotations

import tempfile
import unittest

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.github_backend import RepositoryFolderArchiveBackend
from learning_archive.package import build_archive_package, build_record_package
from tests.test_learning_archive import sample_case, sample_snapshots


class LearningArchiveLifecycleGuardTests(unittest.TestCase):
    def test_archive_finalized_at_does_not_rewrite_immutable_case(self):
        with tempfile.TemporaryDirectory() as tmp:
            backend = RepositoryFolderArchiveBackend(tmp)
            pending = sample_case("PENDING")
            backend.write_case(
                build_record_package(pending, sample_snapshots(), "2026-10-03T15:31:00Z"),
                pending,
            )

            final = sample_case("WIN")
            final["provenance"]["archive_finalized_at"] = "2026-10-03T20:00:00Z"
            result = backend.write_case(build_archive_package(final, sample_snapshots()), final)
            self.assertFalse(result.idempotent)

    def test_record_and_revisit_require_pending_settlement(self):
        with tempfile.TemporaryDirectory() as tmp:
            exporter = LearningArchiveExporter(RepositoryFolderArchiveBackend(tmp))
            settled = sample_case("WIN")
            with self.assertRaisesRegex(ArchiveFinalizationError, "requires PENDING settlement"):
                exporter.record_case(
                    settled,
                    sample_snapshots(),
                    observed_at="2026-10-03T15:31:00Z",
                )
            with self.assertRaisesRegex(ArchiveFinalizationError, "requires PENDING settlement"):
                exporter.record_case(
                    settled,
                    sample_snapshots(),
                    observed_at="2026-10-03T16:00:00Z",
                    revisit=True,
                )


if __name__ == "__main__":
    unittest.main()
