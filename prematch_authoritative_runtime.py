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
_HISTORY_TO_CURRENT = {
    "moneyway_1x2_history": "moneyway_1x2",
    "moneyway_ou25_history": "moneyway_ou25",
    "moneyway_btts_history": "moneyway_btts",
    "dropping_1x2_history": "dropping_1x2",
    "dropping_ou25_history": "dropping_ou25",
    "dropping_btts_history": "dropping_btts",
}


def _install_service_role_credentials() -> str:
    """Bind all canonical prematch DB access to the server-only credential.

    The legacy scheduled scraper still reads its database credential from
    ``SUPABASE_ANON_KEY``. The authoritative Hetzner entrypoint already requires
    the service-role secret for its fixture-identity RPC, so expose that same
    server credential through the legacy slot *before* importing scraper code.
    This removes production prematch writes/heartbeats from the public anon role
    without changing preview/local entrypoints that run the legacy module
    directly.
    """
    service_key = str(os.environ.get("SUPABASE_SERVICE_ROLE_KEY") or "").strip()
    if not service_key:
        raise SystemExit(
            "SUPABASE_SERVICE_ROLE_KEY is required for provider-authoritative prematch runtime"
        )
    os.environ["SUPABASE_ANON_KEY"] = service_key
    os.environ["SMARTXFLOW_PREMATCH_CREDENTIAL_MODE"] = "service_role"
    return service_key


def _install_authoritative_history_guard() -> None:
    """Keep authoritative current/history writes fail-closed as one unit.

    ``betwatch_prematch`` writes current first and history second. In the
    provider-authoritative runtime, history must not receive the same batch when
    current-table sync fails (for UID proof, PostgREST, or any other write
    reason). The guard is installed only by this canonical authoritative
    entrypoint, so legacy/preview compatibility paths remain unchanged.
    """
    import betwatch_prematch as prematch

    if getattr(prematch, "_SXF_AUTHORITATIVE_HISTORY_GUARD", False):
        return

    original_sync = prematch.sync_current_table
    original_append_history = prematch.SupabaseWriter.append_history

    def guarded_sync(writer, table, rows, logger=None):
        ok = bool(original_sync(writer, table, rows, logger=logger))
        failed = getattr(writer, "_sxf_authoritative_current_failures", None)
        if not isinstance(failed, set):
            failed = set()
        if ok:
            failed.discard(table)
        else:
            failed.add(table)
        writer._sxf_authoritative_current_failures = failed
        return ok

    def guarded_append_history(writer, table, rows, scraped_at):
        current_table = _HISTORY_TO_CURRENT.get(table)
        failed = getattr(writer, "_sxf_authoritative_current_failures", set())
        if current_table and current_table in failed:
            errors = getattr(writer, "last_write_errors", None)
            marker = f"fixture_uid_current_write:{current_table}"
            if isinstance(errors, list) and marker not in errors:
                errors.append(marker)
            return False
        return original_append_history(writer, table, rows, scraped_at)

    prematch.sync_current_table = guarded_sync
    prematch.SupabaseWriter.append_history = guarded_append_history
    prematch._SXF_AUTHORITATIVE_HISTORY_GUARD = True


def run() -> None:
    # Override stale/false environment values deliberately. Once this entrypoint
    # is selected, provider identity is the only allowed fixture authority.
    os.environ[_CANONICAL_FLAG] = "true"

    # Fail closed and install the server-only database credential before any
    # scraper module is imported.
    _install_service_role_credentials()
    _install_authoritative_history_guard()

    from scheduled_scraper import run_loop

    print(
        "[IdentityV2] Prematch runtime: provider-authoritative fixture writer "
        "and service-role DB credential enforced",
        flush=True,
    )
    run_loop()


if __name__ == "__main__":
    run()
