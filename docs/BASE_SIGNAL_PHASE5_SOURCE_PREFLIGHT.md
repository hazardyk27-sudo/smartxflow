# SmartXFlow — Phase 5A/5B Source Change & Performance Preflight

**Status:** GitHub `preview` source proposal only. No live SQL, Replit, Hetzner, `main`, production sampler or frontend change. The original Base signal rules/checkpoints remain frozen.

## What Phase 5A adds

Proposed migration `migrations/2026_10_19_sxf_base_phase5a_source_capture_PROPOSED.sql` defines two **new** isolated tables: immutable `sxf_base_source_changes` (the event ledger) and mutable `sxf_base_source_deliveries` (the pending/retry/leased/done work queue). Narrow triggers on `public.fixtures` and `public.moneyway_snapshots` capture insert, update and delete as part of the exact same source transaction.

Important distinction: `captured_at = clock_timestamp()` is **the trigger execution time**, not guaranteed COMMIT/ingestion visibility time and not `scraped_at_utc`. The outbox is not a commit-time CDC system. PostgreSQL sequences can commit out of order; the queue tracks every pending row individually rather than using a naïve `max(change_id)` high-water cursor.

Trigger functions are deliberately **SECURITY DEFINER**, since existing source writers must not be granted rights to the service-only outbox. Trigger bindings require strict source table/schema identity and a fixed `search_path`; their owner and operation must be audited as a separate security gate. Other RPCs remain `SECURITY INVOKER`. The trigger writes themselves add work to *every* affected source transaction. Merely passing synthetic tests does not establish production throughput.

The opt-in Python consumer `source_change_runtime.process_source_change_once` claims one event with `FOR UPDATE SKIP LOCKED`, resolves the *current* fixture UID state through a service-only RPC, idempotently enqueues the canonical 11 jobs, quarantines obsolete/deleted UIDs, or wakes an existing missing-T6 reconciliation when a snapshot INSERT appears in a relevant window. The checkpoint queue and source delivery ACK are separate transactions; retry after a crash is deliberately safe and deduplicated. Snapshot UPDATE/DELETE events are put into a manual-review retry state, **not silently acknowledged**, because immutable historical decisions might need a correction policy.

The source event feed begins only **when the source triggers are actually installed**. It cannot retroactively capture old changes. First activation therefore requires separately approved historical bootstrap and overlap reconciliation.

## Part 5B — Health and plan evidence

`sxf_base_source_health()` reports outbox backlog, due and leased events, expired leases, review-required events, event kinds, oldest source capture delay and explicit `source_commit_watermark: null`. The snapshot index-plan parser takes only DBA-supplied PostgreSQL `EXPLAIN (FORMAT JSON)` evidence; it never reports an actual production index as verified. Existing separately gated composite-index proposal:

`CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_sxf_base_mw_snapshot_uid_time ON public.moneyway_snapshots(fixture_uid,scraped_at_utc,id);`

This is **not run** by these migrations. A development test creates the same B-tree in disposable PostgreSQL to check schema and planner compatibility. Real latency, size, write-amplification and production query-plan assessment require an explicit DBA/operator preflight under load.

### Safe, read-only production preflight (only after authorization)

A DBA should confirm actual source schemas, privileges, existing indexes, ingestion writer volume, 95th/99th percentile write latency, source retention and the intended fixture UID semantics. Benchmark bounded `EXPLAIN (FORMAT JSON)` on a read-only transaction with `statement_timeout`, representative fixture/time windows and peak/off-peak source volumes. Count trigger-induced writes per snapshot row, assess outbox disk growth/backpressure, and review any source transaction failures caused by sidecar writes. Avoid running `EXPLAIN ANALYZE` in production without explicit permission because it executes the query.

### Non-destructive rollback plan (NOT EXECUTED)

If triggers harm the source ingestion pipeline, first stop the *new* source consumer, then—under approved DBA control—remove only `sxf_base_fixture_source_capture` and `sxf_base_snapshot_source_capture` from the two original source tables. Keep `sxf_base_source_changes` and `sxf_base_source_deliveries` intact for forensic replay and audit; do **not** delete ledger records or automatically drop tables. Re-enable source-ingest processing only when its independent health is verified. Changes that happened while capture was disabled form a known data-coverage gap requiring explicit bootstrap/backfill.

### Production blockers after 5B

- Preexisting historical source changes and snapshot archive before trigger installation have **no captured event feed**; bootstrap must preserve actual fixture identity and source evidence.
- Reliable source COMMIT times, large transaction caveats and producer-side cancellation/remap semantics remain unverified.
- A snapshot UPDATE/DELETE event is **review-required**, not an automated signal retraction.
- Source-trigger write amplification and index size under real ingest load need measurement and approval.
- 24-hour continuous shadow **has not run**. Synthetic 24h clock advancement, if later added, would not substitute for it.
- Migration/deploy promotion and background workers remain blocked until user approval and an explicit rollback/downtime plan.
