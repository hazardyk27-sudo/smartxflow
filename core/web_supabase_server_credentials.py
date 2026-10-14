"""Web-only Supabase credential hardening.

The shared ``services.supabase_client`` is also used by desktop/client builds,
where the public anon credential is intentional.  Hetzner's Flask/Gunicorn web
runtime is different: all PostgREST access originates on the trusted server and
should use the service-role credential so sensitive tables can be removed from
public anon/authenticated access.

This module installs a narrow runtime guard before ``app.py`` is imported.  It
never changes Supabase Auth's anon client in ``services.auth_helpers``.
"""

from __future__ import annotations

import os
from typing import Optional, Tuple


def _server_service_role_credentials() -> Optional[Tuple[str, str]]:
    """Return server-only REST credentials, or None outside that contract."""
    if os.environ.get("SMARTXFLOW_MODE", "").strip().lower() != "server":
        return None
    url = os.environ.get("SUPABASE_URL", "").strip().rstrip("/")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        return None
    return url, key


def install_web_server_service_role_guard() -> bool:
    """Make the shared REST client prefer service_role in Hetzner web mode.

    Returns True when the guard is installed or already present.  Returns False
    only when the shared client cannot be imported.  If the runtime is not
    server mode, or the service-role secret is absent, the original credential
    loader remains the fallback so preview/desktop compatibility is preserved.
    """
    try:
        from services import supabase_client as shared
    except Exception as exc:
        print(f"[WebRuntime] Supabase credential guard unavailable: {exc}")
        return False

    current = shared.SupabaseClient._load_credentials
    if getattr(current, "_sxf_web_service_role_guard", False):
        return True

    original = current

    def guarded_load_credentials(self):
        credentials = _server_service_role_credentials()
        if credentials is None:
            return original(self)

        self.url, self.key = credentials
        # Keep URL validation, but deliberately do not call the shared helper:
        # it logs credential prefixes/suffixes and must not expose service-role
        # key material in production logs.
        if "dashboard" in self.url.lower():
            print("[WebRuntime] Invalid Supabase API URL: dashboard URL rejected")
            self.url = None
            self.key = None
            return
        if not self.url.endswith(".supabase.co"):
            print("[WebRuntime] Supabase URL does not end with .supabase.co")
        print("[WebRuntime] Generic server PostgREST client uses service_role")

    guarded_load_credentials._sxf_web_service_role_guard = True  # type: ignore[attr-defined]
    guarded_load_credentials._sxf_web_service_role_original = original  # type: ignore[attr-defined]
    shared.SupabaseClient._load_credentials = guarded_load_credentials
    return True
