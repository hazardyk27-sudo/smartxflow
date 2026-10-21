#!/usr/bin/env python3
"""Guarded, read-only-fenced automatic recovery of the ONE Hetzner Base worker.

A lost RPC acknowledgement can follow a committed write. Never restart
immediately. Wait >=1800s after explicit uncertain exit 3, verify no *live*
lease in any of the three sxf_base_* families, then restart ONLY the
existing production unit. Historical rows, signals, and snapshots untouched.
No retry of the unknown RPC transaction is issued by this supervisor.
"""
from __future__ import annotations

from datetime import datetime, timezone
import json
import os
import re
import subprocess
import sys
import time
from typing import Callable

import requests

UNIT = "smartxflow-base-worker.service"
MIN_COOLDOWN_SEC = 1800
WORKER_ID = "hetzner-base-" + os.environ.get("SXF_BASE_WORKER_ID", "prod-autonomous-1")
TABLES = (
    ("sxf_base_checkpoint_jobs", True),
    ("sxf_base_reconcile_jobs", True),
    ("sxf_base_discovery_cursors", False),
)


class RecoveryGuardFailed(RuntimeError):
    pass


def _run(*argv: str) -> str:
    result = subprocess.run(argv, check=True, capture_output=True, text=True,
                            timeout=15)
    return result.stdout.strip()


def _read_live_leases(base_url: str, secret: str, *,
                      now: datetime, session: requests.Session) -> int:
    if now.tzinfo is None:
        raise RecoveryGuardFailed("clock is not UTC aware")
    headers = {"apikey": secret, "Authorization": "Bearer " + secret,
               "Accept": "application/json"}
    count = 0
    for table, with_state in TABLES:
        params = {"select": "lease_owner", "lease_expires_at":
                  "gt." + now.astimezone(timezone.utc).isoformat(), "limit": "1"}
        if with_state:
            params["state"] = "eq.LEASED"
        response = session.get(base_url.rstrip("/") + "/rest/v1/" + table,
                               params=params, headers=headers, timeout=12)
        if response.status_code != 200:
            raise RecoveryGuardFailed("database lease read rejected")
        rows = response.json()
        if not isinstance(rows, list) or len(rows) > 1:
            raise RecoveryGuardFailed("database lease read malformed")
        if rows:
            count += 1
    return count


def evaluate(*, now_mono: float | None = None, utc_now: datetime | None = None,
             run: Callable[..., str] = _run,
             session: requests.Session | None = None) -> str:
    """Return stable decision; never perform an unsafe or unapproved restart."""
    get = lambda property: run("/bin/systemctl", "show", UNIT, "-p", property,
                               "--value").strip()
    enabled, state, status, result = (
        get("UnitFileState"), get("ActiveState"), get("ExecMainStatus"), get("Result"))
    if enabled != "enabled":
        return "SKIP_NOT_ENABLED"
    if state in ("active", "activating", "reloading", "deactivating"):
        return "SKIP_NOT_FAILED"
    if state != "failed" or status != "3" or result != "exit-code":
        return "SKIP_UNSAFE_EXIT"
    exit_usec = get("ExecMainExitTimestampMonotonic")
    if not re.fullmatch(r"[0-9]{1,20}", exit_usec) or int(exit_usec) <= 0:
        return "SKIP_UNKNOWN_EXIT_TIME"
    elapsed = (now_mono if now_mono is not None else time.monotonic()) - int(exit_usec) / 1_000_000
    if elapsed < MIN_COOLDOWN_SEC:
        return "SKIP_COOLDOWN"
    if elapsed > 30 * 86400:  # stale systemd metadata must not authorize recovery
        return "SKIP_STALE_EXIT"
    if (os.environ.get("SXF_BASE_DURABLE_WORKER_APPROVED") != "yes" or
            os.environ.get("SXF_BASE_COMPOSITE_INDEX_VERIFIED") != "yes" or
            os.environ.get("SXF_BASE_PRIORITY_LANES_APPROVED") != "yes"):
        return "SKIP_RELEASE_GATES"
    base = os.environ.get("SUPABASE_URL", "")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    if not base.startswith("https://") or not key:
        return "SKIP_CREDENTIALS"
    if not re.fullmatch(r"hetzner-base-[A-Za-z0-9_-]{1,90}", WORKER_ID):
        return "SKIP_WORKER_ID"
    sess = session or requests.Session()
    # Fail closed on any timeout, missing rights, non-200 response or malformed JSON.
    # Any active job/cursor lease, even another owner's, must block restart.
    try:
        leased = _read_live_leases(base, key,
                                  now=utc_now or datetime.now(timezone.utc),
                                  session=sess)
    except (requests.RequestException, ValueError, RecoveryGuardFailed):
        return "SKIP_DB_READ_UNCERTAIN"
    if leased:
        return "SKIP_ACTIVE_DB_LEASE"

    # Re-read systemd state after network IO to avoid resurrecting an
    # already-restarted worker. The new service reclaims only expired jobs
    # using PostgreSQL FOR UPDATE SKIP LOCKED + fencing tokens.
    if (get("ActiveState") != "failed" or get("ExecMainStatus") != "3" or
            get("ExecMainExitTimestampMonotonic") != exit_usec):
        return "SKIP_STATE_CHANGED"
    run("/bin/systemctl", "reset-failed", UNIT)
    run("/bin/systemctl", "start", UNIT)
    return "RECOVERY_STARTED"


def main() -> int:
    try:
        decision = evaluate()
    except (subprocess.SubprocessError, OSError, RecoveryGuardFailed):
        decision = "SKIP_SYSTEMD_READ_ERROR"
    # Do not log URLs, secrets, owner IDs, RPC response bodies, or exception text.
    print(json.dumps({"mode": "BASE_GUARDED_RECOVERY", "decision": decision},
                     sort_keys=True), flush=True)
    return 0 if decision in ("RECOVERY_STARTED", "SKIP_NOT_FAILED", "SKIP_COOLDOWN",
                             "SKIP_ACTIVE_DB_LEASE", "SKIP_STATE_CHANGED",
                             "SKIP_STALE_EXIT", "SKIP_NOT_ENABLED",
                             "SKIP_UNSAFE_EXIT", "SKIP_RELEASE_GATES",
                             "SKIP_CREDENTIALS", "SKIP_WORKER_ID",
                             "SKIP_UNKNOWN_EXIT_TIME") else 1


if __name__ == "__main__":
    sys.exit(main())
