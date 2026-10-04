import os
import unittest
from unittest.mock import patch

from learning_archive.retention import RetentionHoldError, _config


class LearningArchiveRetentionConfigTests(unittest.TestCase):
    def test_service_role_key_has_precedence_over_application_key(self):
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co/",
            "SUPABASE_SERVICE_ROLE_KEY": "service-role-key",
            "SUPABASE_SERVICE_KEY": "legacy-service-key",
            "SUPABASE_KEY": "application-key",
        }, clear=True):
            url, key = _config()
        self.assertEqual(url, "https://example.supabase.co")
        self.assertEqual(key, "service-role-key")

    def test_legacy_service_alias_precedes_generic_key(self):
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_SERVICE_KEY": "legacy-service-key",
            "SUPABASE_KEY": "application-key",
        }, clear=True):
            _, key = _config()
        self.assertEqual(key, "legacy-service-key")

    def test_generic_key_remains_backwards_compatible_when_it_is_the_service_key(self):
        with patch.dict(os.environ, {
            "SUPABASE_URL": "https://example.supabase.co",
            "SUPABASE_KEY": "legacy-direct-service-role-key",
        }, clear=True):
            _, key = _config()
        self.assertEqual(key, "legacy-direct-service-role-key")

    def test_missing_key_fails_closed(self):
        with patch.dict(os.environ, {"SUPABASE_URL": "https://example.supabase.co"}, clear=True):
            with self.assertRaisesRegex(RetentionHoldError, "service-role"):
                _config()


if __name__ == "__main__":
    unittest.main()
