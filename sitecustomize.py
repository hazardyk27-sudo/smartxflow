"""Process-placement safety hook for SmartXFlow.

Python imports ``sitecustomize`` automatically during interpreter startup when
this repository is on ``sys.path``.  Replit is preview/UI only; production
workers belong to Hetzner systemd.  This hook makes stale Replit workflows
fail closed even when they invoke worker scripts directly instead of using
``run_services.sh``.

Important: ``REPL_DEPLOYMENT`` is intentionally NOT used as a Replit marker.
Legacy Hetzner environments historically carried that stale variable.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Mapping, Optional

_REPLIT_MARKERS = (
    "REPL_ID",
    "REPL_SLUG",
    "REPL_OWNER",
    "REPLIT_DEV_DOMAIN",
    "REPLIT_DOMAINS",
)

_PRODUCTION_WORKER_ENTRYPOINTS = frozenset(
    {
        "scheduled_scraper.py",
        "scheduled_scraper_legacy.py",
        "prematch_authoritative_runtime.py",
        "alarm_engine.py",
        "live_scraper.py",
        "sinyal_engine.py",
        "sinyal_engine_runtime.py",
        "polymarket_scraper.py",
    }
)


def is_replit_runtime(env: Optional[Mapping[str, str]] = None) -> bool:
    values = os.environ if env is None else env
    return any(str(values.get(name, "")).strip() for name in _REPLIT_MARKERS)


def should_refuse_replit_backend(
    argv0: Optional[str] = None,
    env: Optional[Mapping[str, str]] = None,
) -> bool:
    executable = Path(sys.argv[0] if argv0 is None else argv0).name
    return is_replit_runtime(env) and executable in _PRODUCTION_WORKER_ENTRYPOINTS


def _enforce_runtime_placement() -> None:
    if not should_refuse_replit_backend():
        return

    worker = Path(sys.argv[0]).name
    message = (
        f"[runtime-placement] REFUSED: {worker} cannot run on Replit. "
        "Replit is preview/UI only; production workers run on Hetzner."
    )
    print(message, file=sys.stderr, flush=True)
    # Exit before the requested worker module executes or imports production
    # clients.  os._exit avoids running partially initialized interpreter
    # shutdown hooks from a stale supervisor/workflow.
    os._exit(0)


_enforce_runtime_placement()
