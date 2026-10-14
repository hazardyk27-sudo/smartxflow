#!/usr/bin/env python3
"""Hetzner Polymarket runtime guards.

Runs the canonical ``polymarket_scraper.py`` after installing narrow production
runtime guards:

* Hetzner production aliases the process-local Supabase PostgREST credential to
  ``SUPABASE_SERVICE_ROLE_KEY``.  Preview/desktop runtimes keep their existing
  anon credential behavior.
* Sport-registry persistence is deduplicated by conflict key so PostgreSQL does
  not raise cardinality violation 21000 for duplicate identities in one bulk
  upsert.

The registry guard preserves the classifier's monotonic state semantics:
verified > non_football > uncertain.  Equal-strength duplicates use the last
observation while retaining useful metadata that the winner omitted.
"""

from __future__ import annotations

import os
import runpy
import sys
from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple

from services import polymarket_client as _client


_CLASS_RANK = {
    _client.FOOTBALL_CLASS_UNCERTAIN: 0,
    _client.FOOTBALL_CLASS_NON_FOOTBALL: 1,
    _client.FOOTBALL_CLASS_VERIFIED: 2,
}


def install_hetzner_service_role_credentials() -> bool:
    """Use service_role for the dedicated Hetzner Poly worker only.

    ``polymarket_scraper.py`` and ``services.polymarket_client`` historically
    read ``SUPABASE_ANON_KEY``.  Rather than changing shared desktop/preview
    code, the canonical Hetzner wrapper replaces that process-local alias before
    the scraper is executed.  No key material is logged.

    Returns True when the production override was installed.  A Hetzner
    production runtime without a service-role secret fails closed instead of
    silently falling back to public mutation privileges.
    """
    runtime_id = os.environ.get("SMARTXFLOW_RUNTIME_ID", "").strip()
    if runtime_id != "hetzner-prod":
        return False

    service_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not service_key:
        raise RuntimeError(
            "Hetzner Poly runtime requires SUPABASE_SERVICE_ROLE_KEY"
        )

    # Both names are consumed by legacy/shared PostgREST helpers.  This change
    # is local to the Poly process and does not alter the host .env file.
    os.environ["SUPABASE_ANON_KEY"] = service_key
    os.environ["SUPABASE_KEY"] = service_key
    return True


def _registry_identity_key(record: Mapping[str, Any]) -> Optional[Tuple[str, str]]:
    identity_type = record.get("identity_type")
    if identity_type not in ("event", "condition"):
        return None
    identity_id = _client._registry_id(record.get("identity_id"))
    if not identity_id:
        return None
    return str(identity_type), str(identity_id)


def _prefer_registry_record(
    current: Mapping[str, Any],
    incoming: Mapping[str, Any],
) -> Dict[str, Any]:
    """Choose the strongest duplicate while preserving useful metadata."""
    current_rank = _CLASS_RANK.get(current.get("classification"), -1)
    incoming_rank = _CLASS_RANK.get(incoming.get("classification"), -1)

    # On equal rank, the later observation wins.  This matches the existing
    # upsert's "last checked" semantics while remaining deterministic.
    if incoming_rank >= current_rank:
        winner = dict(incoming)
        other = current
    else:
        winner = dict(current)
        other = incoming

    for field in ("event_id", "source", "evidence"):
        if not winner.get(field) and other.get(field):
            winner[field] = other.get(field)
    return winner


def dedupe_sport_registry_records(
    records: Optional[Iterable[Dict[str, Any]]],
) -> List[Dict[str, Any]]:
    """Collapse duplicate normalized registry conflict keys in one batch.

    First-occurrence ordering is retained so batching remains stable.  Invalid
    rows are left in place for the canonical persistence function to validate
    exactly as before.
    """
    result: List[Dict[str, Any]] = []
    positions: Dict[Tuple[str, str], int] = {}

    for record in records or []:
        if not isinstance(record, dict):
            # The canonical function expects dicts and will retain its previous
            # validation/error behavior for malformed inputs.
            result.append(record)  # type: ignore[arg-type]
            continue

        key = _registry_identity_key(record)
        if key is None:
            result.append(record)
            continue

        position = positions.get(key)
        if position is None:
            positions[key] = len(result)
            result.append(dict(record))
            continue

        result[position] = _prefer_registry_record(result[position], record)

    return result


def install_registry_dedupe_guard() -> None:
    current = _client._persist_sport_registry_records
    if getattr(current, "_sxf_registry_dedupe_guard", False):
        return

    original = current

    def guarded(records):
        deduped = dedupe_sport_registry_records(records)
        if records is not None:
            try:
                removed = len(records) - len(deduped)
            except TypeError:
                removed = 0
            if removed > 0:
                print(
                    f"[PolyRuntime] collapsed {removed} duplicate sport-registry "
                    "row(s) before PostgREST upsert",
                    flush=True,
                )
        return original(deduped)

    guarded._sxf_registry_dedupe_guard = True  # type: ignore[attr-defined]
    guarded._sxf_registry_dedupe_original = original  # type: ignore[attr-defined]
    _client._persist_sport_registry_records = guarded


def main() -> None:
    install_hetzner_service_role_credentials()
    install_registry_dedupe_guard()

    default_scraper = os.path.join(os.path.dirname(__file__), "polymarket_scraper.py")
    if len(sys.argv) > 1 and not sys.argv[1].startswith("-"):
        scraper = os.path.abspath(sys.argv[1])
        scraper_args = sys.argv[2:]
    else:
        scraper = default_scraper
        scraper_args = sys.argv[1:]

    sys.argv = [scraper, *scraper_args]
    runpy.run_path(scraper, run_name="__main__")


if __name__ == "__main__":
    main()
