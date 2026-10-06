#!/usr/bin/env python3
"""Authoritative SmartXFlow prematch runtime entrypoint.

The Replit Scraper Engine may still launch ``python scheduled_scraper.py``.
This bootstrap makes Fixture Identity V2 authoritative before importing any
prematch writer code, so the legacy hash-authoritative fixture path cannot be
selected by a stale/false environment flag.
"""
import os

os.environ["SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE"] = "true"

from scheduled_scraper_legacy import *  # noqa: F401,F403,E402


if __name__ == "__main__":
    if not str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip():
        raise SystemExit("FATAL: SUPABASE_SERVICE_ROLE_KEY is required for authoritative fixture identity")
    run_loop()
