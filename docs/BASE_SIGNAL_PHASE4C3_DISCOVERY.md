# SmartXFlow Base Signals — Phase 4C3 durable discovery cursor

**GitHub preview SOURCE ONLY. Not executed on Supabase, not deployed.**

Why: The earlier `durable_runtime.cycle` scans a rolling seven-day kickoff
window, insufficient to guarantee replay after multi-week outages. This module
does not silently change that existing shadow behavior. Instead it offers an
**explicit operator-initialized**, lease-protected incremental bootstrap.

Proposed SQL `2026_10_19_sxf_base_phase4c_discovery_cursor.sql` creates a
single `BASE_FIXTURES` cursor, immutable `bootstrap_start`, monotonic
`completed_through`, last scanned metrics and token-fenced RPCs. A caller
must choose the first date after checking source retention; conflicting start
values are rejected. No automatic starting at `now-7 days`.

`discover_window_once` processes one UTC range of at most 24h. It uses
existing UID/fixture-kickoff-bound source catalog pagination and the 11-job
idempotent enqueue. Only after **both** succeed does the cursor advance; on
failure it releases the lease, leaving the window for replay. A lost advancement
response is `uncertain`, never proof of durable coverage. Two claimants cannot
own the cursor at the same time.

**Remaining limitations:** This kickoff-based historical cursor by itself does
not detect fixtures later added or rescheduled into an already-scanned past
window, nor does it prove fixture ingestion completeness. Periodic rolling
overlap, fixture `created_at` ingestion watermark, source retention audit and
kickoff-change schedule corrections are still required for production-grade
coverage. Backfill must remain opt-in until the snapshot composite index and
safe batch latency have been verified. No systemd service, deployment, or live
Supabase migration is authorized.
