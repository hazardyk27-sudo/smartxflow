# SmartXFlow Base Signals — production database preparation record (2026-10-19)

## Scope

User requested sequential completion of the Base motor. This report
records **actual changes made to production Supabase** and intentionally
separates them from source-only changes. Only the `preview` branch was
modified; `main` was not promoted and no existing Hetzner production
service was edited or restarted.

### Completed 1 — snapshot index

- Applied via standalone `CREATE INDEX CONCURRENTLY IF NOT EXISTS`:
  `idx_sxf_base_mw_snapshot_uid_time` on
  `public.moneyway_snapshots(fixture_uid,scraped_at_utc,id)`.
- Verified with `pg_index.indisvalid=true` and `indisready=true`.
- Reported index size 278–279 MB.
- A real physical UID and T-6/T-8 timestamp-range read-only `EXPLAIN
  (FORMAT JSON)` used this index with an actual UID-and-time
  `Index Cond`. Explain cost is a planner estimate, not runtime latency.
- No deletion/rewrite of existing snapshot rows.

### Completed 2 — isolated durable Base schema and RPCs

Applied through Supabase migration history in this dependency order:

1. `sxf_base_checkpoint_durable_queue_20261019`.
2. `sxf_base_waiting_data_hardening_20261019`.
3. `sxf_base_reconciliation_rpc_20261019`.
4. `sxf_base_reconcile_queue_20261019`.
5. `sxf_base_discovery_cursor_20261019`.
6. `sxf_base_kickoff_drift_20261019`.
7. `sxf_base_discovery_heartbeat_20261019`.
8. `sxf_base_health_snapshot_20261019`.
9. `sxf_base_market_projection_20261019`.

These create seven separate RLS-enabled `sxf_base_*` tables.
Actual `public.sxf_base_health_snapshot()` returned:
`checkpoint_queue.total=0`, `reconciliation_queue.total=0`,
`discovery_cursor.initialized=false`, with no expired leases.
There is **no automatic running Base durable worker** yet.
The ordinary SmartXFlow fixtures/Moneyway source data and existing
legacy signal records were not rewritten.

### Explicitly NOT applied — source-capture triggers

`migrations/2026_10_19_sxf_base_phase5a_source_capture_PROPOSED.sql`
and dependent `2026_10_19_sxf_base_phase5b_source_health.sql` were
**not applied**. The live snapshot schema has nullable `fixture_uid`
and large historic DELETE volume. Initially proposed source trigger
would have attempted an outbox INSERT with NULL physical identity,
causing the source write itself to fail; the `preview` proposal was
corrected and disposable-PG tests extended. Even with that fix, the
transactional source trigger adds outbox writes to every source row
insert/update/delete and may create an unbounded delivery backlog
during retention cleanup. Do not enable until measured at representative
ingest/purge volume with consumer capacity and documented rollback.

No fake zero source-outbox health metric is used to claim capture coverage.

### Completed 3 — worker source prepared (not activated)

- Added `base_signal_engine/hetzner_worker.py`: Hetzner-only
  bounded durable checkpoint + late T-6 reconciliation worker,
  token-fenced RPCs, no legacy signal writes. Rolling fixture discovery
  can operate without Phase 5A capture triggers.
- Added `deploy/systemd/smartxflow-base-worker.service` with
  `User=smartxflow`, memory limit, kernel/system protections and
  no credentials committed.
- It is NOT included in the production `sync_runtime_units.sh`.
  Starting requires `SXF_BASE_DURABLE_WORKER_APPROVED=yes` and
  `SXF_BASE_COMPOSITE_INDEX_VERIFIED=yes` in server-only settings.
- Added supervised `--once --no-discovery` mode to check a *single*
  existing durable job without accidentally enqueuing the entire
  fixture history.
- All associated 162 Python and 31 disposable PostgreSQL tests passed
  in GitHub Actions on `preview` (run 39266335316).
- In current session the Remote Desktop Commander link stopped
  answering commands, so the new worker has **not** been copied
  into `/opt/smartxflow`, installed, enabled or run.

## What remains before declaring complete

A single controlled, physically identified end-to-end Base job must
prove claim -> native source read -> coverage -> atomic SQL completion
-> immutable events on the actual Supabase schema. Next: inspect
source-mutating capture trigger throughput safely; after the
user-approved exact SHA goes through release flow, install Hetzner
durable worker in isolation and run 24h genuine shadow with independent
logs, lease/queue health and source-mutation review. A 24h shadow
cannot be declared passed ahead of elapsed real time.

**Production release status: NOT YET APPROVED / NOT ACTIVATED.**
