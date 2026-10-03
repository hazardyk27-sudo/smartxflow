"""Shared retention-cleanup safety guard.

Preview/Replit can share the same Supabase project as production.  When
SMARTXFLOW_DISABLE_RETENTION_CLEANUP is enabled, retention cleanup must become
a no-op while normal reads, scraping and writes continue.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

_TRUE_VALUES = {"1", "true", "yes", "on"}


def retention_cleanup_disabled(env: Optional[Mapping[str, str]] = None) -> bool:
    source = os.environ if env is None else env
    value = str(source.get("SMARTXFLOW_DISABLE_RETENTION_CLEANUP", ""))
    return value.strip().lower() in _TRUE_VALUES


def install_supabase_cleanup_guard() -> bool:
    """Guard the web Supabase retention delete path when preview flag is on."""
    if not retention_cleanup_disabled():
        return False

    try:
        from services.supabase_client import SupabaseClient
    except Exception as exc:
        print(f"[Retention Guard] Supabase guard import failed: {exc}")
        return False

    current = getattr(SupabaseClient, "cleanup_old_matches", None)
    if current is None:
        print("[Retention Guard] cleanup_old_matches method not found")
        return False
    if getattr(current, "_smartxflow_retention_guarded", False):
        return True

    original = current

    def guarded_cleanup(self, *args, **kwargs):
        if retention_cleanup_disabled():
            print("[Retention Guard] Web retention cleanup blocked by SMARTXFLOW_DISABLE_RETENTION_CLEANUP")
            return {}
        return original(self, *args, **kwargs)

    guarded_cleanup._smartxflow_retention_guarded = True
    guarded_cleanup._smartxflow_original = original
    SupabaseClient.cleanup_old_matches = guarded_cleanup
    print("[Retention Guard] Web retention cleanup guard installed")
    return True
