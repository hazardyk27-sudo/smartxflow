from __future__ import annotations

import os
from typing import Any, Dict


def identity_lookup_headers(writer: Any) -> Dict[str, str]:
    """Return headers for privileged Fixture Identity V2 registry reads.

    Production prematch writers normally use the anon credential for ordinary
    current/history/snapshot table writes. The provider-authoritative identity
    registry is intentionally not exposed to anon, so UID resolution must use
    the service-role credential when it is available. Tests and legacy/shadow
    callers without a service-role environment retain the writer headers.
    """
    service_role_key = str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if service_role_key:
        return {
            "apikey": service_role_key,
            "Authorization": f"Bearer {service_role_key}",
            "Content-Type": "application/json",
        }
    return dict(writer._headers())
