"""Optional strong administrator login, independent from public Supabase anon key.

Until SXF_ADMIN_PASSWORD_HASH is configured, existing admin login stays operational
for non-archive pages. GitHub archival is fail-closed without strong login.
"""
from __future__ import annotations

import hmac
import os
import time

from werkzeug.security import check_password_hash

AUTH_MODE = "PASSWORD_V2"
MAX_AGE_SECONDS = 8 * 60 * 60


def configured_password_hash() -> str:
    supplied = os.environ.get("SXF_ADMIN_PASSWORD_HASH", "").strip()
    # Refuse plaintext and legacy SHA1/MD5. Werkzeug supports these KDF formats.
    if supplied.startswith("scrypt:") or supplied.startswith("pbkdf2:sha256:"):
        return supplied
    return ""


def password_login_enabled() -> bool:
    return bool(configured_password_hash())


def verify_admin_password(candidate: str) -> bool:
    stored = configured_password_hash()
    if not stored or not isinstance(candidate, str) or not candidate:
        return False
    try:
        return check_password_hash(stored, candidate)
    except (ValueError, TypeError):
        return False


def is_secure_admin_session(state) -> bool:
    if not password_login_enabled():
        return False
    if state.get("admin_authenticated") is not True or state.get("sxf_admin_auth_mode") != AUTH_MODE:
        return False
    try:
        age = time.time() - float(state.get("sxf_admin_login_at"))
    except (ValueError, TypeError):
        return False
    return 0 <= age <= MAX_AGE_SECONDS
