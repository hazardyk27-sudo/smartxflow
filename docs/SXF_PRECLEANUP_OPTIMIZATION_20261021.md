# SmartXFlow / pre-deletion optimization gate (2026-10-21)

Scope: `hazardyk27-sudo/smartxflow` only. **Preview-only preparation. No production migration, release, cleanup, or deployment.** The 7-day definition keeps the CURRENT Istanbul date and the previous six full calendar dates. On 2026-10-21 the cut is **2026-10-15 00:00 +03 = 2026-10-14 21:00Z**.

## Live read-only evidence (21 Oct 2026, ~19:40 TSİ)
- Database ~17 GB. `research_archive` ~6,602 MB. Do not modify ANY object in `research_archive`.
- `public.moneyway_snapshots` ~1,981 MB; its indexes ~1,353 MB.
- `public.polymarket_trades` ~1,689 MB; indexes ~1,392 MB.
- `public.live_snapshots` ~1,420 MB; ~384K dead tuples estimated.
- `public.moneyway_snapshots` ~308K dead tuples estimated.
- `pg_stat_statements`: historical `moneyway_1x2_history` REST requests dominate total execution time; inspect request callers / pagination before adding speculative indexes.
- **Two functionally duplicated nonunique B-tree index pairs** (do NOT drop before exact checks):
  1. `public.idx_mw_snap_scraped` on `moneyway_snapshots(scraped_at_utc)` ~195 MB / index scans 0; retain `idx_mw_snap_scraped_utc` ~130 MB / scans 287,787.
  2. `public.idx_live_snapshots_hash` on `live_snapshots(match_id_hash)` ~74 MB / index scans 0; retain `idx_live_snap_hash` ~74 MB / scans 3,689.
  ~269 MB *candidate* space saving, NOT yet saved. Index scan counters are lifetime since stats reset; validate dependencies, constraints, current plans and write throughput.
- `research_archive.archive_runs` marks 2026-10-14 `source_retention_cleanup_allowed=false` and `cold_backup=COLD_BACKUP_PENDING`; earlier 9-13 Oct days have no affirmative allowed/backup flag. Earliest source `moneyway_snapshots` previously observed 2026-10-06. Gate MUST block even if status `COMPLETE`.
- `public.learning_archive_retention_holds` and `public.learning_archive_capture_outbox` are separate guards. Check both.
- Some `scraped_at` values are ISO8601 **text** with +03 offset, not timestamptz. Source observation date is not identical to fixture kickoff date; full parity needs independent verification.
- Polymarket activity and ledger histories have additional active-position and wallet semantics. **NOT in the eligible source-delete allowlist.** Preserve accounts, licensing, settings, queue state, open positions, historical signals lacking durable archive evidence, and all of `research_archive`.

## New fail-closed preflight
Run from a checked-out preview tree with Postgres client env connection (PGHOST, PGUSER, PGDATABASE, PGPASSWORD or PGSERVICE):

```bash
python3 scripts/maintenance/sxf_precleanup_preflight.py
python3 -m pytest -q tests/test_sxf_precleanup_preflight.py
```

The Python command runs `psql` with read-only `BEGIN`, short SQL/lock timeouts, date-bound indexed first-row queries, archive metadata, and pending holds. It emits machine-readable `BLOCKED` reasons and returns non-zero. It contains **no apply/delete mode**. The SQL deliberately sets independent cold-backup/parity confirmations to false: they must be validated in a separately reviewed source-to-target manifest/checksum workflow, never inferred from an archive status. No script or task should interpret `GATES_PASSED_MANUAL_REVIEW_REQUIRED` as authority to delete. This design is conservative by intent.

## Recommended order before any deletion (not executed)
1. Verify a recoverable independent backup with restore test and match-day/observation-day lineage. Reconcile archive source-row fingerprints, keys and counts; explicitly unlock each older day only after success.
2. Identify and stop the repetitive `moneyway_*_history` REST scans; use page/keyset parameters, narrower selects, appropriate ordering and bounded batches. Compare request volumes/latency before/after.
3. In a low-I/O period, review duplicate index dependencies and EXPLAIN plans. Stage and test any `DROP INDEX CONCURRENTLY` individually (NOT via transactional migration/automatic deploy). PostgreSQL cannot execute it inside a transaction.
4. Run the read-only preflight; review every failing reason. Keep `research_archive` untouched.
5. Only after explicit production permission: guarded micro-batch cleanup with timeouts, rate limits, telemetry, archive parity and retry-safe resume. Validate no active/live records changed. Prefer nonblocking ordinary VACUUM/ANALYZE during a safe I/O period; do NOT run VACUUM FULL on production.
6. Commit/test in preview; release to main/Hetzner ONLY with the user-approved exact SHA and release gates. Never use Replit or the user's personal computer.

No cron/timer is enabled by this change. No rows or indexes are removed.

## Additional safety optimization / verified after initial report
- Updated `core/retention_guard.py` on preview: `SMARTXFLOW_RETENTION_CLEANUP_APPROVED` must be explicitly truthy; otherwise BOTH the scheduled scraper guard and the web Supabase cleanup wrapper deny legacy cleanup by default. The older global emergency-disable and pending-hold checks remain in place.
- This is **not** the authorization for a historical purge. Even when the operator eventually approves the legacy switch, independent backup, date-by-date source parity, active-position scope and safe batching are separate production gates. Keep the legacy switch unset until the old unbounded path is retired.
- Live SQL validation of `scripts/maintenance/sxf_precleanup_evidence.sql` succeeded. It found earliest source 2026-10-06, missing archive_runs dates Oct 6-8, unverified cold backup for Oct 9-14, source_retention_cleanup_allowed=false, and both retention-hold/outbox pending counts zero. Combined result: **BLOCKED**.
- Live catalog dependency check confirmed the two proposed redundant index candidates have zero `pg_constraint` index references and zero external `pg_depend` references. This supports *review*, not a production DROP. Only the exact duplicate index pairs listed above qualify for consideration.
- GitHub Actions gate `39642548896` succeeded; expanded guard+preflight CI `39643141804` also succeeded.
