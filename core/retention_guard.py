"""Shared retention-cleanup safety guard.

Two independent protections are supported:
1. SMARTXFLOW_DISABLE_RETENTION_CLEANUP disables cleanup entirely (preview safety).
2. Learning Archive retention holds pause cleanup while selected cases still need source history.

Learning Archive retention is mandatory-by-default after the production hold
migration. Cleanup therefore fails closed when hold state cannot be verified.
"""

from __future__ import annotations

import os
from typing import Mapping, Optional

_TRUE_VALUES = {"1", "true", "yes", "on"}


def _explicit_cleanup_disable(env: Optional[Mapping[str, str]] = None) -> bool:
    source = os.environ if env is None else env
    value = str(source.get("SMARTXFLOW_DISABLE_RETENTION_CLEANUP", ""))
    return value.strip().lower() in _TRUE_VALUES


def _learning_archive_guard_enabled() -> bool:
    try:
        from learning_archive.retention import retention_holds_enabled
        return retention_holds_enabled()
    except Exception:
        # Archive retention is mandatory; inability to import/verify must not
        # silently re-enable destructive cleanup.
        return True


def retention_cleanup_disabled(env: Optional[Mapping[str, str]] = None) -> bool:
    """Return whether cleanup must be blocked right now.

    This function is also used by the scheduled scraper, so pending archive
    holds are checked here instead of only in the web-client monkey patch.
    """
    if _explicit_cleanup_disable(env):
        return True
    if not _learning_archive_guard_enabled():
        return False
    try:
        from learning_archive.retention import has_pending_retention_holds
        return has_pending_retention_holds()
    except Exception:
        # Fail closed: never delete source history when hold state is unknown.
        return True


def install_supabase_cleanup_guard() -> bool:
    """Guard the web Supabase retention delete path before app startup."""
    if not _explicit_cleanup_disable() and not _learning_archive_guard_enabled():
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
        if _explicit_cleanup_disable():
            print("[Retention Guard] Cleanup blocked by SMARTXFLOW_DISABLE_RETENTION_CLEANUP")
            return {}

        if _learning_archive_guard_enabled():
            try:
                from learning_archive.retention import has_pending_retention_holds
                if has_pending_retention_holds():
                    print("[Retention Guard] Cleanup blocked: Learning Archive case(s) still pending")
                    return {}
            except Exception:
                # Fail closed: if hold state cannot be verified, never risk deleting source history.
                print("[Retention Guard] Cleanup blocked: Learning Archive hold state unavailable")
                return {}

        return original(self, *args, **kwargs)

    guarded_cleanup._smartxflow_retention_guarded = True
    guarded_cleanup._smartxflow_original = original
    SupabaseClient.cleanup_old_matches = guarded_cleanup
    print("[Retention Guard] Web retention cleanup guard installed")
    return True
