#!/usr/bin/env python3
"""Canonical prematch runtime entrypoint for Fixture Identity V2.

The prematch scraper must enter provider-authoritative mode before importing
``scheduled_scraper`` / ``betwatch_prematch``. This keeps the shared Betwatch
live client untouched while making the scheduled prematch runtime incapable of
silently falling back to the legacy ``match_id_hash`` fixture writer.
"""

from __future__ import annotations

import os

_CANONICAL_FLAG = "SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE"


def run() -> None:
    # Override stale/false environment values deliberately. Once this entrypoint
    # is selected, provider identity is the only allowed fixture authority.
    os.environ[_CANONICAL_FLAG] = "true"

    # The authoritative RPC is service-role only. Fail before importing/starting
    # the scraper loop rather than entering a retry loop that can never write.
    if not str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip():
        raise SystemExit(
            "SUPABASE_SERVICE_ROLE_KEY is required for provider-authoritative prematch runtime"
        )

    from scheduled_scraper import run_loop

    print("[IdentityV2] Prematch runtime: provider-authoritative fixture writer enforced", flush=True)
    run_loop()


if __name__ == "__main__":
    run()
