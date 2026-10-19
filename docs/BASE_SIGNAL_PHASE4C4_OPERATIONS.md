# SmartXFlow Base Signals — Part 4C4 operator review (SOURCE ONLY)

**Source of truth:** `hazardyk27-sudo/smartxflow:preview`.
**Status:** proposed migration and opt-in modules; NOT APPLIED or deployed.
No permission to touch `main`, Hetzner, Replit, or live Supabase.

## Part 4C4A — late fixture discovery and kickoff drift

The periodic `rolling_rescan_once` (not activated) scans a bounded 1–30 day
overlap and invokes the existing idempotent checkpoint enqueue, then the
bounded drift quarantine. `fixture_uid` + exact kickoff remain authoritative.
Obsolete historical jobs become `SUPERSEDED`; an append-only
`sxf_base_fixture_drift_events` row records the transition without rewriting
a previously emitted signal or evaluation. New insert triggers reject obsolete
physical fixture identities even when the reconciliation scan has not run.

**Limitation:** a late-created match or reschedule outside the configured
overlap cannot be guaranteed without fixture-created/updated ingestion history
or a separate provider change feed. A missing/deleted UID may require
manual quarantine. Do not claim full historical coverage.

## Part 4C4B — cooperative lease heartbeat

`CooperativeLeaseHeartbeat` uses monotonic time and token-fenced RPC
renewals. Base and late-T6 reconciliation replay now pulse before evaluation
and on Supabase Moneyway source pagination; discovery pulses on each source
catalog page, after reading and before watermark advancement. Renewals
occur in the caller thread, never via a background thread sharing an HTTP
session. Discovery renewal uses additive service-role-only
`sxf_base_renew_discovery` SQL. Existing 20s HTTP request timeout remains
in effect: this is no guarantee against stalled, non-IO CPU work lasting past
the lease TTL, and a final renewal/commit token fence still applies.

## Part 4C4C — read-only health snapshot

`sxf_base_health_snapshot` exposes aggregate counts for pending, waiting,
leased, expired, completed and superseded checkpoint jobs, outstanding
reconciliations, discovery cursor lag, and append-only drift events. The
service-role-only adapter never infers an ingestion watermark from the
`scraped_at_utc` observation timestamp: `snapshot_ingestion_watermark`
remains **null/unknown** pending a verified ingestion timestamp source.

Health SQL and other Part4 schemas must be applied **only** in the previously
defined migration order, and only after explicit user approval. A successful
CI run on disposable PostgreSQL does not mean production migration, load
benchmark, source retention, 24-hour shadow, or operational alarm thresholds
have been completed.

## Remaining release blockers

1. Immutable-current view/projection of correction chains for frontend.
   Never show stale T-8 as a final T-6 or a `SUPERSEDED` signal as current.
2. Reliable source-ingestion change log and fixture-remap/cancellation proof,
   including modifications older than the bounded overlapping scan.
3. Composite source snapshot lookup index: performance benchmark and
   separately approved `CREATE INDEX CONCURRENTLY`; verify real pagination
   rates and impact before scanning at scale.
4. Heartbeat load and query duration under full source volume, bounded worker
   scheduling, health alert thresholds, 24h+ shadow and rollback plan.
5. Explicit user sign-off before applying any SQL, promoting to main, or
   touching Hetzner/Replit.

The Phase 1 motor formulas/checkpoints and ordinary production scraper were
not changed in 4C4.
