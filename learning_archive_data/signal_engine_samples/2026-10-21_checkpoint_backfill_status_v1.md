# SXF signal engine performance — checkpoint backfill status as of 2026-10-21 03:25 Europe/Istanbul

**Append-only research observations, not a production signal deployment and not a complete all-engine performance evaluation.**

## Daily CSV inventory

| Local fixture day | Observations | Source / status |
|---|---:|---|
| 2026-10-09 | 244 | Existing |
| 2026-10-10 | 409 | Existing |
| 2026-10-11 | 320 | Existing |
| 2026-10-12 | 136 | Existing |
| 2026-10-13 | 102 | Existing |
| 2026-10-14 | 120 | Backfilled research_archive |
| 2026-10-15 | 222 | Backfilled research_archive |
| 2026-10-16 | 154 | Backfilled bounded research_archive |
| 2026-10-17 | 286 | Existing; untouched |
| 2026-10-18 | 409 | Backfilled bounded research_archive; **underlying research_archive archive_runs still PARTIAL** |
| 2026-10-19 | 120 | Backfilled using indexed public Moneyway history + archived fixture/result identities |
| 2026-10-20 | 197 | Backfilled using indexed public Moneyway history + public fixtures/live_fixtures results; **no research_archive raw daily run** |
| 2026-10-21 | — | **IN PROGRESS, not settled / no final day CSV** |

**Total 2026-10-09 through 2026-10-20:** 12 daily files; **2,719 signal/checkpoint observations**. These are not 2,719 distinct fixtures. Six added dates (14/15/16/18/19/20) total 1,222 observations.

## Readback and integrity checks

All six new daily files were successfully fetched from `learning-archive` after GitHub commit. Each new CSV has the required 24 fields, 0 malformed widths, 0 duplicate (fixture_uid,horizon,engine,side) keys, 0 missing settled labels for its signal rows, and 0 wrong local_date rows. Distinct fixtures with observations: 14th 28; 15th 35; 16th 41; 18th 95; 19th 36; 20th 36. Stale rows (>30 min at checkpoint): 14th 12; 18th 2; other four new days 0.

## Derivation boundary

- Checkpoints are T-6, T-5, T-4, T-3 hours before kickoff (not independent engine variants).
- Signal families included in added CSVs: 1X2 concentration V1 / Heavy, provisional V2, Surprise Team, Over Stable/Premium, BTTS Yes.
- 14 and 15 October queried the latest stored *valid* snapshot at or before the checkpoint (could be older than eight hours). 16 and 18 October used a bounded 8-to-3-hour pre-kickoff window. 19 and 20 October used indexed primary history and the same bounded window. Therefore, **do not pool all raw sample rows without first harmonizing date coverage and snapshot freshness**.
- 19 and 20 October `public` source timestamps have fixed Europe/Istanbul `+03:00` offset and were matched to per-fixture checkpoint cutoffs. The public histories were read via indexed source IDs/hashes rather than exhausting the old unindexed research_archive history tables. Source files named `*_checkpoint_source_*.json` preserve the inputs separately from derived CSVs.
- The approximate V2 research three-hour min-share + max/min odds metric is **not proven equivalent** to the original frozen V2 anchor-based adverse-price threshold. These V2 labels are provisional.
- Early Money T-72/T-60/T-40/T-24/T-12 and Retention-55 are **NOT backfilled** by these new daily CSVs. Until they are reconstructed, the archives are not complete across all engine families.
- Original 2026-10-13 and 2026-10-17 files have 17-column formats and slightly different labels; standardize only in a derived comparison, never overwrite historical originals.
- The 18 October raw daily archive is marked `PARTIAL`; 20 October has no `research_archive.archive_runs` day record. Preserving derived performance samples does not repair the raw research_archive day.

## 21 October status

At approximately **03:24 local time**: public fixtures for 21 October = 139, of which 9 already started, 130 in the future, and 3 had a final-score status. A final daily win/loss comparison would be premature. Preserve as current-day partial only if needed; create the final 21 October day CSV after the day's matches finish, using prematch-frozen observations and postmatch settlement.

## Next remaining work

1. Finish 21 October only after the fixture day closes and scores can be joined; never fabricate result labels.
2. Repair 18 October raw day completeness and make a controlled 20 October raw-data archive if source retention permits.
3. Reconstruct Early Money / Retention-55 separately and audit V2 anchor-equivalent thresholds; compare only matched and fresh checkpoint cohorts before ranking engines.

This inventory records what was observed and saved, not a certification of 100% data coverage.
