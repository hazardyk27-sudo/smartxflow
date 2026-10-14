#!/usr/bin/env python3
"""Hetzner production entrypoint for the live scraper.

The historical live scraper expects its Supabase credential in
``SUPABASE_ANON_KEY``. Production writes must not use the public anon role, so
this wrapper requires the service-role secret and exposes that credential to
the legacy live process before executing it. Preview/local callers that invoke
``live_scraper.py`` directly keep their existing behavior.
"""

from __future__ import annotations

import os
import runpy
import sys
from pathlib import Path
from typing import MutableMapping


def install_live_service_role_guard(
    environ: MutableMapping[str, str] | None = None,
) -> str:
    env = os.environ if environ is None else environ
    service_key = str(env.get("SUPABASE_SERVICE_ROLE_KEY", "")).strip()
    if not service_key:
        raise RuntimeError(
            "Hetzner live runtime requires SUPABASE_SERVICE_ROLE_KEY; "
            "refusing anon-key production writes"
        )

    # live_scraper.py has one credential parameter for both reads and writes.
    # A service-role credential is valid for both and prevents production
    # mutations/heartbeats from depending on public anon table grants.
    env["SUPABASE_ANON_KEY"] = service_key
    env["SMARTXFLOW_LIVE_CREDENTIAL_MODE"] = "service_role"
    return service_key


def _resolve_live_target(argv: list[str] | None = None) -> Path:
    args = sys.argv if argv is None else argv
    if len(args) >= 2:
        target = Path(args[1]).resolve()
    else:
        target = Path(__file__).resolve().with_name("live_scraper.py")
    if target.name != "live_scraper.py":
        raise RuntimeError(f"refusing unexpected live runtime target: {target}")
    if not target.is_file():
        raise RuntimeError(f"live scraper target missing: {target}")
    return target


def main() -> int:
    install_live_service_role_guard()
    live_path = _resolve_live_target()
    runpy.run_path(str(live_path), run_name="__main__")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
