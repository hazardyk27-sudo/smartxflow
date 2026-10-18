# SmartXFlow Base Signals — Part 4 (GitHub `preview`, **not deployed**)

## Deliverables

- Proposed standalone migration `migrations/2026_10_18_sxf_base_durable_queue.sql` (three separate namespaced tables plus service-role-only RPCs). **Not applied** to Supabase.
- Proposed snapshot performance index `migrations/2026_10_18_sxf_base_snapshot_index_APPROVAL_REQUIRED.sql`. **Not applied**. Must use separate nontransactional `CREATE INDEX CONCURRENTLY`, benchmark first.
- `base_signal_engine/storage.py`: narrowly scoped PostgREST RPC adapter (DB job enqueue, atomic claim, renew, complete, retry; no direct writes to existing tables).
- `base_signal_engine/durable_runtime.py`: opt-in orchestration; existing Part 3 shadow runner remains unchanged. No executable service hook, systemd service, Replit or Hetzner configuration was added.
- `tests/test_base_signal_storage.py`: simulated transport identity/lease/error tests. SQL integration and two-host concurrency are **NOT yet exercised** against real Postgres.

## Data model / write contract

1. `sxf_base_checkpoint_jobs`: immutable identity `(ruleset_version, fixture_uid, kickoff_utc, family, checkpoint_hours)` and job_key; mutable scheduling/lease state only. Client enumerates all 11 checkpoint-family tasks for every discovered physical fixture; no Base T-5/T-4/T-3 job exists (only Early retention).
2. `sxf_base_checkpoint_evaluations`: exactly one immutable evaluation payload per completed job, even when no signal; source snapshot quality and missing-data states preserved.
3. `sxf_base_signal_events`: append-only per-signal events; T-8 is `PRELIMINARY_SIGNAL`, T-6 is `FINAL_SIGNAL` (may use T-8 fallback if a *market* lacks T-6), Early records are `EARLY_SIGNAL`. For all T-6 Base market outcomes—including none—the RPC adds a `MARKET_DECISION` event. Early retention has `RETENTION_CHECK` events. Frontend must not show preliminary T-8 as final after a T-6 market decision is recorded.
4. The DB `sxf_base_complete_job` RPC validates lease ownership and inserts evaluation + events + job completion **in one SQL transaction**. A failure rolls the entire operation back. Source snapshots and legacy Sinyal tables are not modified.
5. `claim_due_jobs` uses `FOR UPDATE SKIP LOCKED` and per-claim UUID fencing tokens. Expired leases may be reclaimed; a prior worker's completion cannot succeed after its token changes. `fail_job` returns to bounded retry, not silent terminal deletion.
6. Database append-only triggers reject UPDATE/DELETE on evaluations and events. New tables have RLS, no anon/authenticated permissions; RPC execution is granted only to `service_role`. Service credentials stay server-side.

## Availability and limitations

- Queue survives worker restarts **after the queue has been populated**. The first discovery/backfill must enumerate matches; unseen fixtures cannot be recovered if the source fixture record has already disappeared. Phase 5 must establish a verified bootstrap/backfill and discovery completeness watermark.
- The Part 3 scheduler currently resolves each checkpoint using `checkpoint+10min` as an ingestion grace. Late snapshots beyond grace do not retroactively override the result: an explicit append-only correction process is required before treating the system as fully resilient.
- `durable_runtime.cycle` still uses bounded catalog pagination and a default seven-day discovery window. Already queued jobs are evaluated even when a catalog read fails. The worker claims **one job at a time** to avoid unstarted leases expiring; a 900s TTL is provisional and long reads need heartbeat management.
- Running SQL and modifying Supabase security/index layout are **release actions** requiring explicit approval. No production schema/infra changes authorized or made here.
- Not yet 7/24: there is no systemd install, migration apply, production job, checked health SLO or 24h shadow run.

## Required gates before deployment

1. Validate migration against test Postgres and exercise **real** two-worker concurrent claims, conflicting enqueue, lost lease, partial insert rollback, permissions and replay after restart. Static checks cannot prove transactional behavior.
2. Benchmark SQL `EXPLAIN (ANALYZE, BUFFERS)` and RPC load using a safe replica/test database. Approve and install combined snapshot index separately if appropriate.
3. Implement durable fixture discovery + scan watermark and backfill (including old missed fixtures); test retention and reschedules.
4. Implement late-data reconciliation, bounded renewal/heartbeats and visibility projection from immutable events. Prefer small safe batches, verified health alarms.
5. Shadow test 24h+, inspect errors and checkpoint coverage; request Preview approval before any `main` or Hetzner promotion.