#!/usr/bin/env python3
"""Guarded Replit scraper entrypoint.

Runs the normal scheduled scraper loop while hard-blocking retention cleanup in
preview. Normal scraping, heartbeat and alarm signalling continue unchanged.
"""

import os

os.environ["SMARTXFLOW_DISABLE_RETENTION_CLEANUP"] = "1"

from core.retention_guard import retention_cleanup_disabled
import scheduled_scraper


def _blocked_cleanup(*_args, **_kwargs):
    print("[Retention Guard] Scraper retention cleanup blocked in Replit preview")
    return 0


def _blocked_try_cleanup(*_args, **_kwargs):
    print("[Retention Guard] Scheduled scraper cleanup skipped in preview")
    return None


def main():
    if not retention_cleanup_disabled():
        raise RuntimeError("Retention cleanup guard must be enabled in preview")

    # Defense in depth: block both the imported cleanup function and the loop hook.
    scheduled_scraper.cleanup_old_matches = _blocked_cleanup
    scheduled_scraper._try_run_cleanup = _blocked_try_cleanup
    scheduled_scraper.run_loop()


if __name__ == "__main__":
    main()
