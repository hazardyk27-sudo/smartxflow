# SmartXFlow Base — Step 2: independent fixture discovery (2026-10-21)

## Observed production failure

At 2026-10-21T00:59Z, the source had 163 matches beginning 24–72 hours
later but **0** were present in the Base checkpoint queue. The previous
per-minute near-term discovery scanned only a single kickoff hour per loop,
and could be blocked by slow checkpoint processing. A rotating one-hour
bucket is not an end-to-end fixture coverage guarantee.

## Fix

A separately gated Hetzner systemd unit
`smartxflow-base-fixture-discovery.service` reads the complete canonical
`public.fixtures` catalog from T-2 hours to T+80 hours **every 180 seconds**,
independent of checkpoint evaluation and its backlog.

- Source catalog GET and active checkpoint-key GET both fail closed on
  incomplete pagination, duplicates or transport errors.
- Every source fixture receives all 11 frozen immutable checkpoint identities
  (T-72, -60, -40, -24, -12, -8, -6 Base, -6/-5/-4/-3 retention).
- Only fixtures missing at least one job are re-enqueued, using the existing
  idempotent `sxf_base_enqueue_jobs` RPC.
- Same UID with a new kickoff generates new physical fixture checkpoint
  identities. Old jobs are marked `SUPERSEDED` with auditable drift events;
  never deleted. A currently active leased job is not superseded until its
  lease ceases to be live (migration
  `2026_10_21_sxf_base_quarantine_preserve_live_leases.sql`).
- Existing Base checkpoint worker keeps its current safety gates and is
  not required for the new scanner to advance.
- No scraper, quote history, legacy signal rules, Predictor or bet market data
  are modified.

## Release and independent verification

Use GitHub production fast-forward and the matching Hetzner deploy,
followed by the exact-SHA gated workflow
`base-fixture-discovery-hetzner-enable.yml`.

Acceptance requires the independent unit to be enabled and active, at
least one `mode=BASE_FIXTURE_DISCOVERY,status=SCANNED` with
`coverage_verified_for_snapshot=true`, and a full live SQL anti-join
confirming that **each current source fixture in the requested 80-hour
horizon** has 11 matching checkpoint jobs.

A one-off green service state is insufficient. Historical missing Moneyway
snapshots and signal-engine result correctness belong to later steps.

## Verified live outcome

GitHub focused test suite: **90 passed**. Production service's first full scan
observed 320 fixtures; 233 required jobs and 2,563 new immutable checkpoint
rows were enqueued. Two fixtures created during that scan were automatically
picked up by the next periodic scan.

Read-only Supabase coverage check at 2026-10-21 01:18:21 UTC:
- T+0–8h: 10/10 fixtures have all 11 checkpoint jobs.
- T+8–24h: 136/136.
- T+24–72h: 164/164.
- T+72–80h: 4/4.
- **Total: 314/314, missing jobs = 0.**

This is a time-bounded source snapshot validation, not a promise that every
future data ingestion run is complete. In particular, incomplete Moneyway
markets/quote snapshots are a separate later repair step.

A final hardening adds post-enqueue re-reading of active checkpoint keys so
a source fixture whose previous kickoff identity was SUPERSEDED cannot
be mistakenly declared fully scheduled.
