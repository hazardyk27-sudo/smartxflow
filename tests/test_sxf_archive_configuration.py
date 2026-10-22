"""Offline tests for private .env provisioning; no real credentials."""
import os
import pathlib
import tempfile
import unittest

from scripts.configure_sxf_archive_access import save_secret_lines, check_file


class ArchiveConfigTests(unittest.TestCase):
    def test_atomic_update_preserves_unrelated_keys_and_permissions(self):
        with tempfile.TemporaryDirectory() as temp:
            target = pathlib.Path(temp) / ".env"
            target.write_text("EXISTING_KEY=keep\n", "utf-8")
            target.chmod(0o600)
            save_secret_lines(target, {"SXF_ADMIN_PASSWORD_HASH": "mockhash",
                                       "CAPITALE_GITHUB_ACTIONS_TOKEN": "test-not-secret"})
            content = target.read_text("utf-8")
            self.assertIn("EXISTING_KEY=keep", content)
            self.assertIn("SXF_ADMIN_PASSWORD_HASH=mockhash", content)
            self.assertIn("CAPITALE_GITHUB_ACTIONS_TOKEN=test-not-secret", content)
            self.assertEqual(target.stat().st_mode & 0o777, 0o600)

    def test_reject_world_readable_env(self):
        with tempfile.TemporaryDirectory() as temp:
            target = pathlib.Path(temp) / ".env"
            target.write_text("EXISTING_KEY=keep\n", "utf-8")
            target.chmod(0o644)
            with self.assertRaises(RuntimeError):
                check_file(target)


if __name__ == "__main__":
    unittest.main()
