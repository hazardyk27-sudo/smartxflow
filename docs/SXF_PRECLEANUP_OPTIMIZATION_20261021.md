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

## Query-load root cause and safe fix (follow-up, 2026-10-21)

**Before (live read-only evidence):**
- `extensions.pg_stat_statements` captured ~85,968 executions of the 1X2 first-valid-history lookup at ~464 ms mean / ~39,900 seconds cumulative (counters are historical, **not** current per-minute rates).
- This request had `home,away,date,odds1/oddsx/odds2 != ''` conditions and `ORDER BY scraped_at ASC LIMIT 1`.
- Literal-predicate `EXPLAIN` used `moneyway_1x2_history_match_earliest_valid_idx`, but `plan_cache_mode=force_generic_plan` with parameterized odds predicates used `idx_moneyway_1x2_history_home_away` plus `Sort`. Generic parameters cannot prove the partial-index filter matches.
- `public.moneyway_1x2.fixture_uid` and `public.moneyway_1x2_history.fixture_uid` both exist, are UUIDs, and history source had **0 NULL UID rows** at live check.
- The generic prepared query filtering **only** `fixture_uid=$1`, odds and timestamp uses existing `moneyway_1x2_history_fixture_uid_scraped_at_idx` with no new DDL. Including `home/away/date` in SQL gave the planner the opportunity to choose the slower home/away index, hence query filters by UID first and validates the strict `home|away|date` composite in Python after receiving the single row.

**Preview changes:**
- `sinyal_first_snapshot_fetch.py` now requests the current `fixture_uid` and uses it as the primary indexed lookup. Exact composite/UUID mismatches fail closed; no UID or an empty UID lookup falls back to composite identity query for backward compatibility. No signal threshold, betting rule, or source timestamps have been altered.
- An unscoped `active_keys=None` call now **fails closed** instead of reviving an expensive full-table history loader.
- Standalone `cleanup_old_matches()` is retired, network-free, and returns zero. Its obsolete orphan scan repeatedly queried `SELECT match_id_hash LIMIT/OFFSET` over entire history and could delete unrelated physical fixtures sharing hashes. This does NOT alter the scrape and alarm flow.
- Both new tests and the repository's original `tests/test_signal_first_snapshot_fetch.py` are included in the preview-only safety CI. Individual old tests expecting unscoped full-table scans were intentionally updated to the safety contract.

**Not yet done:**
- Production rollout and actual before/after latency measurement remain pending exact SHA release approval.
- Redundant index drops have not been executed. At the previous live check, `idx_mw_snap_scraped` and `idx_live_snapshots_hash` were duplicate-function index candidates, both without constraint or external dependency references; always revalidate indexes, stats and real execution plans before any change.
- Cleanup of any old source data remains blocked by missing independently restored backup and archive-per-day parity/allow states.

**Suggested safe index operation after independent approval, one at a time** (illustrative only, **DO NOT run automatically**):

```sql
-- Outside any BEGIN/COMMIT block, on a quiet database.
-- Confirm equivalent survivor, no dependent objects, and direct index scan usage FIRST.
DROP INDEX CONCURRENTLY IF EXISTS public.idx_mw_snap_scraped;
-- Rerun EXPLAIN for live time-range reads, compare write latency, inspect index usage.
DROP INDEX CONCURRENTLY IF EXISTS public.idx_live_snapshots_hash;
-- Recheck pg_indexes, pg_stat_user_indexes and critical queries.
```

Never do `DROP ... CASCADE`, `VACUUM FULL`, `TRUNCATE`, or historical DELETE as part of these index optimizations. Postgres CREATE/DROP INDEX CONCURRENTLY cannot execute inside a transaction block.

## 21 October — fixture-day/observation-day reconciliation (supersedes earlier date interpretation)

**Critical correction:** `research_archive.*.local_date` is the **Europe/Istanbul kickoff day**, whereas `public.fixtures.fixture_date` is UTC-based and history `scraped_at`/`scraped_at_utc` is the **observation timestamp**. For example, one `research_archive.moneyway_snapshots` row archived against a 2026-10-09 fixture has `scraped_at_utc=2026-10-05 23:08:18+00`. Thus a lack of `archive_runs` for Oct 5-8 is not *by itself* evidence that snapshots observed on Oct 5-8 are lost.

When raw `public.fixtures.fixture_date` was naively grouped against archived `local_date`, the 2026-10-14 comparison reported 164 versus 152 with 18/6 unmatched. **That is an invalid axis comparison**, not verified loss: the 12-row difference comes from UTC-to-Istanbul day boundary movement. Join by `fixture_uid` across all days and compare the archive date to `(kickoff_utc AT TIME ZONE 'Europe/Istanbul')::date` instead.

**Verified live read-only fixture-day totals (Oct 21):**
| TR fixture day | Source fixtures | Archive matches | Unmatched fixtures |
|---|---:|---:|---:|
| Oct 5 | 73 | 0 | 73 |
| Oct 6 | 156 | 0 | 156 |
| Oct 7 | 118 | 0 | 118 |
| Oct 8 | 155 | 0 | 155 |
| Oct 9 | 260 | 260 | 0 |
| Oct 10 | 455 | 455 | 0 |
| Oct 11 | 334 | 334 | 0 |
| Oct 12 | 177 | 177 | 0 |
| Oct 13 | 192 | 192 | 0 |
| Oct 14 | 152 | 152 | 0 |

Only fixture IDs are verified for Oct 9–14. **Snapshot/history full parity is NOT verified.** Oct 5–8 have 502 source fixtures without archive fixture counterparts, and must never be erased. Some raw `moneyway_snapshots.fixture_uid` are NULL, so an independent row/fingerprint and exact-fixture reconstruction procedure will be necessary before any source-row deletion.

Reproducible non-destructive SQL checked successfully against production:
- `scripts/maintenance/sxf_archive_fixture_parity_readonly.sql` — 10-day comparison with Istanbul kickoff date
- `scripts/maintenance/sxf_duplicate_index_audit_readonly.sql` — four index definitions, usage and dependencies; returns `production_drop_authorized=false` for both proposed removals
- `scripts/maintenance/sxf_precleanup_evidence.sql` — current 7-day cutoff metadata, correct Istanbul fixture-day probe; **always false** for independent restore/backup, complete row parity, future fixture preservation, and source-observation lineage without separate independent evidence

Index audit still finds both functional duplicate pairs structurally equivalent, with zero constraint/dependency references and ~269 MB potential gain, but **no index was dropped**. As of this note, changes are only on `preview`; no production release, cleanup, index DROP, cron enablement or Hetzner deployment was performed.

**Release blockade:** Separate source-row counts/checksums, future fixture T-72 observations, and tested independent cold backup are mandatory. A `COMPLETE` archive status or an equivalent index is not sufficient authorization.

## Future-fixture history preservation — 21 Oct 2026 (final safety lock)

Read-only indexed query over `public.fixtures` joined by `fixture_uid` to
`public.moneyway_1x2_history` found **922** future fixtures and **106** of those
with valid-source historical records already captured before the seven-day
observation cutoff (`2026-10-15T00:00:00+03:00`). This is direct evidence that
the legacy timestamp-only cleanup is capable of removing history for fixtures
which have **not started**. The number 106 is limited to this one history
table; it is NOT a full count of all endangered snapshot tables.

In response, `core/retention_guard.py` now permanently returns disabled for
the legacy cleanup; the old `SMARTXFLOW_RETENTION_CLEANUP_APPROVED` environment
switch **no longer enables** time-only deletion. The earlier section describing
this switch as an available approval path is superseded by this restriction.
Standalone legacy cleanup was already retired and performs no network I/O.

Use the newly added
`scripts/maintenance/sxf_future_fixture_history_risk_readonly.sql`
to reproduce the future-fixture risk report. This is a diagnostic only. No
automated SQL DDL or DML is run by the report.

**Before a new cleanup design is considered:** match every source row to its
physical fixture and Turkey-local kickoff date, explicitly preserve every
future fixture's T-72/early baseline and all signal input history, reconcile
missing `fixture_uid` values through verified identity (never a reused hash
alone), and verify independently restorable archive storage. After this,
review microbatch cleanup and production release independently.

As of these changes: no live index removal, no data deletion, no
`research_archive` mutation, and no Hetzner/main deployment.

## 21 October continuation — cold backup blocker and actionable backfill order

Scope remains development on `preview`, read-only production auditing, NO cleanup or release.

### Confirmed live state
- Private Storage bucket `sxf-research-archive` **exists** but `storage.objects` reports **0 objects / 0 bytes / 0 manifests**. The running Supabase edge function `sxf-research-archive-export` is **ACTIVE v3**, but an active function is not proof that it exported anything. A separate, recoverable cold backup has **not** been demonstrated by this bucket.
- `research_archive.raw_backfill_receipts` contains only recent (Oct 18–20) dated entries; this does not establish backfill of Oct 5–8.
- Source fixtures for **Oct 5–8 by Turkey-local kickoff date: 73 + 156 + 118 + 155 = 502**. Matching `research_archive.fixtures` rows: **zero**. Oct 9–14: 1,570/1,570 fixture UIDs matched.
- `public.fixtures` has **16** hashes reused across **32** physical fixture UIDs. Hash-only selection is not safe.
- PostgreSQL `pg_stats` (ESTIMATES, not full counts) show NULL `fixture_uid` fraction in `public.live_snapshots` around 1.0 and `public.moneyway_snapshots` around 0.045; exact linkage for non-UID rows still needs a verified physical fixture resolver. No unsafe cross-fixture fallback.
- `research_archive.archive_supplemental_raw_day(date)` is an existing privileged database function. Source review confirms it: writes only supplemental dropping history, moneyway/live snapshots (not missing archive fixture entries or all primary 1X2 histories); disables statement timeout inside the function; uses hash fallback on source rows with no UID; and updates archive_runs counters. **Do not invoke against the missing days** until separately reviewed/reworked. Note: `research_archive` tables reject UPDATE/DELETE under append-only triggers; this function's archive_runs metadata updates do not prove safe history parity.
- Edge function source review of `sxf-research-archive-export` v3 shows **5,000-row LIMIT/OFFSET pages with ctid-based ordering** for some datasets, and `match_id_hash OR fixture_uid` target selection. Live source mutation while paging, reused hashes, partial upload failures and response timeouts make blind bulk export inappropriate. Existing Storage contains zero files.
- A small positive spot check for 2026-10-14 (8 fixtures, earliest 3 moneyway snapshots each) found **24/24** source IDs in archived `moneyway_snapshots`. This is intentionally not called full raw parity.

### Reproducible audits — executed successfully against live Supabase
1. `scripts/maintenance/sxf_archive_backfill_readiness_readonly.sql`: reports Turkey-local day-specific missing archive fixtures, private bucket file/manifests count, hash collision count and hardcoded **false** for backup restore and full parity.
2. `scripts/maintenance/sxf_archive_snapshot_sample_readonly.sql`: bounded 8-fixture / 3-snapshot-per-fixture source-ID sample with indexed archive lookup; always marks `complete_row_parity_verified=false`.
3. Existing `sxf_precleanup_evidence.sql`, `sxf_archive_fixture_parity_readonly.sql`, `sxf_duplicate_index_audit_readonly.sql` and `sxf_future_fixture_history_risk_readonly.sql` remain mandatory. All are READ ONLY and have CI static contract coverage.

### Safe staged recovery sequence (not executed)
1. Build a **separate append-only historic fixture backfill** for Oct 5–8, keyed by source `internal_id` and `fixture_uid`, computing local date from timezone-converted `kickoff_utc`. Never use only `match_id_hash`. Batch small and record independent insert verification. Protect `research_archive` immutability; no rewrites.
2. Reconcile 1X2, O/U2.5, BTTS, dropping, Moneyway and Live raw datasets **source row by source row** via verifiable source IDs/fingerprints and exact fixture UID. For legacy NULL fixture UIDs, require additional credible team/league/kickoff identity data, chronology and ambiguity checks. Mark an ambiguous row **unmatched/protected**, never guess.
3. Replace the Edge export pager with a **bounded, resumable, snapshot-consistent, physically scoped** implementation; restrict hash fallback to independently unambiguous IDs, add checksums, idempotent parts and final manifests. Export to private Storage; verify Storage object totals and restore a representative dataset into a separate isolated environment.
4. Require independent cold-backup proof, fixture and source-row parity on all eligible dates, future-fixture T-72 preservation, archive status and case hold checks before any source retention deletion.
5. Index optimization (~269 MB candidate) is a **separate release**: compare catalog constraints and usage, take production baseline, obtain exact SHA approval, drop at low load one at a time with CONCURRENTLY outside transaction, verify read/write performance. Do not tie to any unsafe old DELETE routine.

No bucket writes, Edge deployments, functions called, database DDL, index drops, source/archived row mutations or Hetzner deployments occurred in this continuation.
