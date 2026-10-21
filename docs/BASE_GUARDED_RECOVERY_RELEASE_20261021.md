# SmartXFlow Base durable worker recovery, 21 Oct 2026

User-approved: Hetzner and Supabase only, no Replit or personal PC.

## Observations
- At 12:15 UTC, 8757 jobs, 264 completed, 3513 pending due, 1028 WAITING_DATA.
- Last checkpoint attempt 01:34:21 UTC, >10 hours ago.
- Two expired checkpoint leases and zero active leases; source and fixture discovery alive.
- Hetzner read-only journal: code-3 UNCERTAIN DURABLESTOREERROR stop.

## Safeguards
- 5-minute timer calls a one-shot recovery guard. It only recovers exit-3
  units after a 1800-second cooldown, no other running unit, and fresh read-only
  proofs of no active lease across checkpoint, reconciliation and discovery.
- Any REST failure, ambiguous state, live lease, unsafe exit status or
  unapproved gate blocks restart.
- No unknown RPC replay, no deleting history, no modifying selection criteria.
- Sanitized RPC name and HTTP status reported on the next unknown ACK.
- Exact SHA activation workflow replaces blind enable --now with the guard.

## Tests and acceptance
128 focused tests passed on GitHub preview.
Production acceptance additionally requires successful exact-SHA deploy,
timer enabled, Base worker active, repeated actual checkpoint processing,
and continuing fresh source ingestion.