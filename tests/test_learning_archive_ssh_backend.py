from __future__ import annotations

import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.github_backend import GitSshArchiveBackend
from learning_archive.ssh_batch_backend import GitSshBatchArchiveBackend
from scripts.drain_due_learning_revisit_queue import _archive_credentials_available


class LearningArchiveSshBackendTests(unittest.TestCase):
    def _key(self, root: str, mode: int = 0o600) -> Path:
        path = Path(root) / "archive_ed25519"
        path.write_text("test-private-key-placeholder\n", encoding="utf-8")
        path.chmod(mode)
        return path

    def test_exporter_uses_ssh_backend_without_token(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._key(tmp)
            with patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "",
                    "GH_TOKEN": "",
                    "LEARNING_ARCHIVE_GIT_SSH_KEY": str(key),
                },
                clear=False,
            ):
                exporter = LearningArchiveExporter.from_env()
            self.assertIsInstance(exporter.backend, GitSshArchiveBackend)
            self.assertEqual(exporter.backend.ssh_key, key.resolve())

    def test_dedicated_ssh_batch_backend_is_preferred_when_actions_token_exists(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._key(tmp)
            with patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "token-for-test",
                    "GH_TOKEN": "",
                    "LEARNING_ARCHIVE_GIT_SSH_KEY": str(key),
                },
                clear=False,
            ):
                exporter = LearningArchiveExporter.from_env()
            self.assertIsInstance(exporter.backend, GitSshBatchArchiveBackend)
            self.assertEqual(exporter.backend.ssh_key, key.resolve())

    def test_permissive_private_key_permissions_fail_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._key(tmp, 0o644)
            with self.assertRaisesRegex(ValueError, "group/world-readable"):
                GitSshArchiveBackend(key)

    def test_missing_private_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            missing = Path(tmp) / "missing"
            with patch.dict(
                os.environ,
                {
                    "GITHUB_TOKEN": "",
                    "GH_TOKEN": "",
                    "LEARNING_ARCHIVE_GIT_SSH_KEY": str(missing),
                },
                clear=False,
            ):
                with self.assertRaisesRegex(ArchiveFinalizationError, "SSH backend is invalid"):
                    LearningArchiveExporter.from_env()

    def test_drain_treats_deploy_key_as_canonical_credential(self):
        with patch.dict(
            os.environ,
            {
                "GITHUB_TOKEN": "",
                "GH_TOKEN": "",
                "LEARNING_ARCHIVE_GIT_SSH_KEY": "/secure/archive-key",
            },
            clear=False,
        ):
            self.assertTrue(_archive_credentials_available())

    def test_git_ssh_command_is_pinned_to_dedicated_key(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._key(tmp)
            backend = GitSshArchiveBackend(key)
            command = backend._env()["GIT_SSH_COMMAND"]
            self.assertIn(str(key.resolve()), command)
            self.assertIn("IdentitiesOnly=yes", command)
            self.assertIn("BatchMode=yes", command)


if __name__ == "__main__":
    unittest.main()
