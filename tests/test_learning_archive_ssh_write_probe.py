import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from scripts.verify_learning_archive_ssh_write import (
    ARCHIVE_REF,
    PROBE_REF,
    REMOTE,
    ArchiveSshWriteProbeError,
    verify_archive_ssh_write,
)


class FakeResult:
    def __init__(self, stdout="", stderr="", returncode=0):
        self.stdout = stdout
        self.stderr = stderr
        self.returncode = returncode


class LearningArchiveSshWriteProbeTests(unittest.TestCase):
    def _key(self, root: str, mode: int = 0o600) -> Path:
        key = Path(root) / "archive_ed25519"
        key.write_text("private-key-placeholder\n", encoding="utf-8")
        key.chmod(mode)
        return key

    def test_missing_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            with self.assertRaisesRegex(ArchiveSshWriteProbeError, "missing"):
                verify_archive_ssh_write(Path(tmp) / "missing")

    def test_permissive_key_fails_closed(self):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._key(tmp, 0o644)
            with self.assertRaisesRegex(ArchiveSshWriteProbeError, "group/world-readable"):
                verify_archive_ssh_write(key)

    @patch("scripts.verify_learning_archive_ssh_write.subprocess.run")
    def test_probe_checks_archive_visibility_and_write_dry_run(self, run):
        with tempfile.TemporaryDirectory() as tmp:
            key = self._key(tmp)
            run.side_effect = [
                FakeResult(stdout="0123456789abcdef0123456789abcdef01234567\trefs/heads/learning-archive\n"),
                FakeResult(stdout="To github.com:hazardyk27-sudo/smartxflow.git\n"),
            ]
            head = verify_archive_ssh_write(key)

        self.assertEqual(head, "0123456789abcdef0123456789abcdef01234567")
        first = run.call_args_list[0].args[0]
        second = run.call_args_list[1].args[0]
        self.assertEqual(first, ["git", "ls-remote", REMOTE, ARCHIVE_REF])
        self.assertEqual(second[:4], ["git", "push", "--dry-run", "--porcelain"])
        self.assertEqual(second[4], REMOTE)
        self.assertEqual(second[5], f"HEAD:{PROBE_REF}")
        env = run.call_args_list[1].kwargs["env"]
        self.assertIn("IdentitiesOnly=yes", env["GIT_SSH_COMMAND"])
        self.assertIn("BatchMode=yes", env["GIT_SSH_COMMAND"])


if __name__ == "__main__":
    unittest.main()
