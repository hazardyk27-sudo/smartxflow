"""Password-mode admin security tests; no real user credentials and no network."""
import os
import time
import unittest
from unittest.mock import patch

from werkzeug.security import generate_password_hash
from sxf_admin_password_auth import (
    AUTH_MODE, configured_password_hash, is_secure_admin_session,
    password_login_enabled, verify_admin_password,
)


class AdminPasswordTests(unittest.TestCase):
    def test_no_password_configured_denies_privileged_operations(self):
        with patch.dict(os.environ, {"SXF_ADMIN_PASSWORD_HASH": ""}):
            self.assertFalse(password_login_enabled())
            self.assertFalse(is_secure_admin_session({
                "admin_authenticated": True, "sxf_admin_auth_mode": AUTH_MODE,
                "sxf_admin_login_at": time.time()
            }))

    def test_hash_verification_and_legacy_hash_denied(self):
        good = generate_password_hash("strong-local-test", method="pbkdf2:sha256:260000")
        with patch.dict(os.environ, {"SXF_ADMIN_PASSWORD_HASH": good}):
            self.assertTrue(password_login_enabled())
            self.assertTrue(verify_admin_password("strong-local-test"))
            self.assertFalse(verify_admin_password("incorrect"))
        with patch.dict(os.environ, {"SXF_ADMIN_PASSWORD_HASH": "plain-text-secret"}):
            self.assertFalse(password_login_enabled())
            self.assertFalse(verify_admin_password("plain-text-secret"))

    def test_legacy_cookie_and_expired_password_session_denied(self):
        value = generate_password_hash("strong-local-test", method="pbkdf2:sha256:260000")
        with patch.dict(os.environ, {"SXF_ADMIN_PASSWORD_HASH": value}):
            good = {"admin_authenticated": True, "sxf_admin_auth_mode": AUTH_MODE,
                    "sxf_admin_login_at": int(time.time())}
            self.assertTrue(is_secure_admin_session(good))
            self.assertFalse(is_secure_admin_session({**good, "sxf_admin_auth_mode": "LEGACY_ANON"}))
            self.assertFalse(is_secure_admin_session({**good, "sxf_admin_login_at": int(time.time())-40000}))
            self.assertFalse(is_secure_admin_session({**good, "admin_authenticated": False}))


if __name__ == "__main__":
    unittest.main()
