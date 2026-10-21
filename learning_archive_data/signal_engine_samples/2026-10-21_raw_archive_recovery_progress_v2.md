# SmartXFlow all-match raw-archive repair progress — 2026-10-21

**Status: PARTIAL / NOT FULLY COMPLETE.** Research-only append/repair operations were performed in **Supabase production research_archive** with existing production source tables as read-only inputs. No SXF web application, signal engine, or Replit files were changed. This report is append-only; prior reports are retained.

## Scope

Goal: all real fixture identities and all available original raw observations for every local kickoff day from 2026-10-09 forward. A signal/checkpoint sample CSV is **not** a substitute for raw archive ticks, prices, money, dropping history, snapshot events and result versions.

Existing `research_archive.archive_runs` status:
- 2026-10-09 through 2026-10-17: `COMPLETE` (per prior recorded run status; not independently re-audited source-row-by-row in this recovery).
- 2026-10-18: `PARTIAL` (other supplemental components and cold backup remain to be validated).
- 2026-10-19: `COMPLETE` per prior recorded run, cold backup still pending.
- 2026-10-20: previously **no run record**. This repair inserted primary fixture/results, main three histories and two snapshot sets, but dropping/alarms/supplemental copy is **incomplete**, so DO NOT mark day `COMPLETE`.
- 2026-10-21: current/local day in progress, not eligible for final FT completion.

## 18 October completed repair

The research archive had 400 fixture UIDs, 1X2 history for 400 and BTTS history for 400, but only 212 fixture UIDs in archived O/U2.5. Source `public.moneyway_ou25_history` contained matching UID/hash history for all 188 missing fixtures.

- Migration `research_archive_ou25_identity_lookup_20261021`: nonunique `(local_date,fixture_uid)` index on the existing O/U raw archive table.
- Inserted archived O/U history only for **the 188 missing UIDs**, in seven idempotent, presence-filtered batches (15+30+30+30+30+30+23 fixture UIDs); original 212 were untouched.
- Final verified `research_archive.moneyway_ou25_history` for 2026-10-18: **313,092 rows / 400 distinct fixture UIDs**, matching all 400 archived fixtures.
- **Do not** flip the overall 18 October `archive_runs` status to `COMPLETE` until other supplemental and cold-backup checks pass.

## 20 October successful writes

- `research_archive.fixtures`: **139** fixture identity rows, inserted with `ON CONFLICT (source_internal_id) DO NOTHING`.
- `research_archive.results`: **135** existing matching `public.live_fixtures` result versions; four Argentina U20 fixtures lacked verified FT labels and were not fabricated.
- The original source has indexed moneyway history for all 139 fixture UIDs in all three markets.
- Migration `archive_repair_idempotent_daily_raw_receipts_20261021` created `research_archive.raw_backfill_receipts` with a primary key `(local_date,dataset,fixture_uid)` to ensure restartable single-transaction claims for bulk raw copies.

Verified from the receipts table after each successful batch:

| Dataset | Claimed fixture UIDs | Exact source rows copied | Status |
|---|---:|---:|---|
| moneyway_1x2_history | 139/139 | 75,111 | Copied |
| moneyway_ou25_history | 139/139 | 66,734 | Copied |
| moneyway_btts_history | 139/139 | 54,138 | Copied |
| moneyway_snapshots | 139/139 | 202,308 | Copied available source records; 135 fixtures have data, four no source |
| live_snapshots | 139/139 | 315,349 | Copied bounded by kickoff and hash; 135 fixtures have data, four no source |
| dropping_1x2_history | **80/139** | **37,109** | **INCOMPLETE** |
| dropping_ou25_history | 0/139 | 0 | **PENDING** |
| dropping_btts_history | 0/139 | 0 | **PENDING** |
| 8 alarm families and fixture aliases | — | — | **PENDING VALIDATION/COPY** |

All completed receipt batches returned `expected_rows = copied_rows` in the same transaction. Empty-source fixture receipts were preserved with expected row count 0. Direct match ID and UID matching was used for market/primary snapshots; `live_snapshots` has source records without fixture UID, so matches were restricted to hash + `coalesce(snapshot_at,created_at)` in the per-fixture interval from kickoff-6 days to kickoff+12 hours. This prevents contamination by a known hash reused for a 2026-10-13 fixture.

**Important blockers:** the first dropping_1x2 batch of 70 source fixtures timed out and automatically rolled back. Smaller batches copied 80 distinct fixtures; a later 20-fixture batch again hit the ~120s statement timeout. No receipt/copy was committed from either timed-out statement. Repeated synchronous bulk writes on live production increased I/O latency. The last source ANALYZE was also slow (~61s), suggesting substantial I/O pressure.

### Safe resume procedure

1. Restore the authorized **Hetzner `smartxflow` Remote Desktop Commander device**, which was OFFLINE in this session (never access the user's personal PC). Perform the remaining copy as throttled, monitored server-side ETL only when database I/O is healthy.
2. Use `research_archive.raw_backfill_receipts` to **skip each already completed (date,dataset,fixture_uid)**. Never reinsert 20 October completed market/snapshot batches; do not rewrite 18 October O/U.
3. Finish the 59 missing 20 Oct dropping_1x2 fixture receipts; then dropping_ou25 and dropping_btts; copy all source alarm/alias records with strict fixture/hash/kickoff matching and deterministic idempotency checks.
4. Inspect 18 October supplemental snapshot/dropping/alarm coverage and missing/result identity conflicts. Restore any raw source-backed gaps; verify per fixture, not just total rows.
5. Audit time bounds and fixture hash collisions; compare archived source fingerprints and row counts for each dataset. Keep snapshot/source tables intact, no delete/truncate.
6. Only after **all** available source raw datasets, all archived fixture IDs, FT label availability, and cold backup have been validated, update the 18/20 `archive_runs` statuses appropriately. Missing results must remain explicit, never invented.
7. When 21 October's local fixture day closes, run a separate current-day raw archival batch. Avoid marking still-open fixtures settled or inventing future observations.

### Not attempted

- No unsafe unbounded exporter retries. The prior `pg_net` queue/export had stalled and the synchronous export failed with HTTP cancellation.
- No destructive changes, no historical rewrites, no changes to production source tables.
- The official cold backup and full long-term retention protection are **not verified**.
