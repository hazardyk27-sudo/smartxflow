"""Provider-backed fixture identity primitives for SmartXFlow Identity V2.

This module is intentionally additive and side-effect free.  It is NOT wired into
scrapers, database writes, API reads, Alarm, Sinyal, or Learning Archive yet.
The existing ``match_id_hash`` contract remains untouched during the shadow
migration.

Identity V2 separates two concepts:

* ``match_id_hash``: legacy matchup fingerprint / compatibility key.
* provider identity: stable identity for one physical event at one provider.

A provider identity must never depend on mutable display fields such as team
spelling, league spelling, or kickoff time.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Mapping, Optional, Tuple

BETWATCH_SOURCE = "betwatch"


def normalize_provider_source(value: Any) -> Optional[str]:
    """Return a canonical provider name, failing closed for empty values."""
    if value is None:
        return None
    source = str(value).strip().lower()
    return source or None


def normalize_provider_event_id(value: Any) -> Optional[str]:
    """Return an opaque provider event id as text.

    Provider IDs are identifiers, not numbers for arithmetic.  Integers are
    therefore converted to their exact decimal text form.  ``bool`` is rejected
    explicitly because Python treats it as an ``int`` subclass and accepting it
    could silently create bogus identities such as ``"True"``.
    """
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value)
    text = str(value).strip()
    return text or None


@dataclass(frozen=True)
class ProviderIdentity:
    """Immutable provider-scoped identity for one physical event."""

    source: str
    event_id: str

    @property
    def key(self) -> Tuple[str, str]:
        return self.source, self.event_id


def make_provider_identity(source: Any, event_id: Any) -> Optional[ProviderIdentity]:
    """Build a provider identity or return ``None`` when identity is incomplete."""
    source_norm = normalize_provider_source(source)
    event_id_norm = normalize_provider_event_id(event_id)
    if not source_norm or not event_id_norm:
        return None
    return ProviderIdentity(source=source_norm, event_id=event_id_norm)


def extract_betwatch_identity(match: Mapping[str, Any]) -> Optional[ProviderIdentity]:
    """Extract the audited Betwatch event identity from a prematch payload row.

    The 2026-10-05 live payload audit established ``match_id`` as the Betwatch
    match-level identifier.  We intentionally do not guess/fallback to similarly
    named fields: if ``match_id`` is absent, the resolver must treat provider
    identity as unavailable and use a later, explicitly-reviewed fallback path.
    """
    if not isinstance(match, Mapping):
        return None
    return make_provider_identity(BETWATCH_SOURCE, match.get("match_id"))
