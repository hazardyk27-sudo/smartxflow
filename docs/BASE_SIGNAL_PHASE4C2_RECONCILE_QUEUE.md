# SmartXFlow Part 4C2 — persistent T-6 reconciliation queue (source-only)

**GitHub `preview` only. NO SQL applied to live Supabase. NO worker auto-start or deployment.**

After the earlier migrations, `migrations/2026_10_19_sxf_base_phase4c_reconcile_queue.sql` proposes:
- A dedicated durable reconciliation queue with one row per *completed T-6 market decision lacking authoritative T-6 source*, keyed by origin event ID.
- Atomic creation via `AFTER INSERT` trigger on immutable `MARKET_DECISION` events; a bounded idempotent `sxf_base_backfill_reconcile` for older events.
- `SKIP LOCKED` claims, rotating lease tokens, 60–3600 second retry and persistent `last_checked_at`, `last_source_observed_at`. No terminal expiry by default.
- `sxf_base_complete_reconcile` holds a row lock, checks token/TTL, calls 4B2 source-validated append-only correction for *each* frozen Base hit, or a no-hit correction, then marks the entire reconciliation job completed **in the same SQL transaction**. A later partial failure rolls back the entire correction batch. It checks quoted odds/amount/share against the actual source IDs; engines still come from the frozen Python motor (not reimplemented in SQL).
- `base_signal_engine.reconcile_runtime.reconcile_once` processes exactly one claim; incomplete source remains WAITING_DATA, source/identity failures retry, lease uncertainty blocks writing, unknown commit response is tracked `commit_uncertain`.

**Important limitation:** current native `moneyway_snapshots` rows include `scraped_at_utc`, NOT a reliable separate ingest timestamp. `last_checked_at` is our discovery/check time, not historical ingest time. Auto correction is opt-in function code, not an activated service. Neither T-8 preliminary CONFIRMED/INVALIDATED append chains nor Early retention corrections are covered by C2; the original preliminary event remains immutable and frontend must prefer corrected T-6 market projections when present. 4C3 must add monitoring, long-outage discovery coverage and safe projection. Full deploy requires explicit user authorization, index benchmarks, load measurements, shadow runs and health checks.
