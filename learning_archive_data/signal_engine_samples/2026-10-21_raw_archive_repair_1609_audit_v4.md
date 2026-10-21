# SmartXFlow raw fixture archive — 2026-10-21 16:09 Europe/Istanbul audit (v4)

**Scope:** production Supabase project `pswdvnmqjjnjodwzkmkp`, read from existing `public` source, preserved under `research_archive`. This file records actions and limitations, not a production app deployment. Existing source data was not altered, historical append-only data was not deleted, and Replit/user PC were not touched.

## 9–21 October fixture identity verification

All 13 local kickoff dates have the same fixture count in `public.fixtures` and `research_archive.fixtures`. The 21 October source can gain more fixtures while the date is open.

| Date | Fixture source / archive | Run state |
|---|---:|---|
| 09 Oct | 260 / 260 | COMPLETE |
| 10 Oct | 455 / 455 | COMPLETE |
| 11 Oct | 334 / 334 | COMPLETE |
| 12 Oct | 177 / 177 | COMPLETE |
| 13 Oct | 192 / 192 | COMPLETE |
| 14 Oct | 152 / 152 | COMPLETE |
| 15 Oct | 160 / 160 | COMPLETE |
| 16 Oct | 201 / 201 | COMPLETE |
| 17 Oct | 436 / 436 | COMPLETE |
| 18 Oct | 400 / 400 | PARTIAL |
| 19 Oct | 173 / 173 | COMPLETE |
| 20 Oct | 139 / 139 | PARTIAL |
| 21 Oct | 141 / 141 | PARTIAL, open date |

## 18 October repair

- All **400/400** archived fixtures now have archived historical 1X2, O/U2.5 and BTTS source rows. Counts at metadata finalization: **338,582**, **313,092**, **201,353**.
- Previously only 212 fixture UIDs had archived Moneyway O/U2.5. The missing 188 fixtures were source-backed, added in idempotent bounded batches.
- Dropping histories now cover **400/400 fixtures** each: dropping 1X2 **324,926** archived rows, dropping O/U2.5 **269,636**, dropping BTTS **192,362**. Source rows were copied by exact UID+hash, without rewriting archived historical rows. Dropping BTTS archive retains historical-only rows not currently in the primary source.
- Moneyway snapshots: **396/400 fixtures** contain existing source data; **707,877** rows in archived dataset. Four fixtures lacked corresponding primary snapshot records; no snapshots were fabricated.
- Live snapshots archived for **398/400 fixtures**, **920,675** rows at last repair accounting.
- Appended **21 missing source-backed Sharp alarm records** from matches with verified 18 October physical fixture hashes. No other matched alarm source IDs were missing.
- Results: 398 of 400 fixture identities have source-derived result records; do not invent the other two FT scores.
- `archive_runs` remains **PARTIAL**, `cold_backup=COLD_BACKUP_PENDING`, retention cleanup disabled. Other cross-system and backup checks are not certified.

## 20 October repair / append-only duplicate resolution

- All **139/139** fixtures and all three historical market sources archived: 1X2 **75,111** rows, O/U2.5 **66,734**, BTTS **54,138**.
- Moneyway snapshots **202,308** source rows; live snapshots **315,349** source rows; 4 fixtures have no verified source FT and not all have snapshots.
- Three dropping datasets contain market records for **139/139** fixture UIDs. Their physical append-only archive contains unintended duplication in 1X2 and O/U2.5.
- Physical 20 October dropping: 1X2 **143,866**, O/U2.5 **133,192**, BTTS **54,022**. Primary source has **71,928**, **66,596**, **54,022** respective rows.
- The append-only trigger `research_archive.reject_mutation` correctly rejected the attempted direct DELETE; **do not bypass or disable this trigger**.
- Created **research-only logical read views**, without deletion:
  - `research_archive.dropping_1x2_history_logical_20261020` = **71,938** rows. It preserves 10 distinct archived historical-only payloads not found in today's source snapshot, as well as the true multiplicity of source rows.
  - `research_archive.dropping_ou25_history_logical_20261020` = **66,596** rows, exactly the current primary source row multiplicity.
- Archive metadata indicates logical views and that physical duplicates remain stored. Callers must use these research logical views for 20 October analyses rather than raw physical dropping history.
- `archive_runs` stays **PARTIAL**, cold backup not verified, four source FT scores missing.

## 21 October current-day partial ingest

- Source/archived fixture identities currently **141/141**, and live source data can increase before the local date closes.
- Created `research_archive.raw_stream_cursors` to record per-fixture progress for eight source datasets. Cursor counts and rows (16:09 Europe/Istanbul):

| Source dataset | Covered fixture cursors | Archived source rows so far | Source-missing fixtures at last check |
|---|---:|---:|---:|
| moneyway_1x2_history | 141 | 62,079 | 0 |
| moneyway_ou25_history | 141 | 61,095 | 0 |
| moneyway_btts_history | 141 | 52,181 | 0 |
| dropping_1x2_history | 141 | 61,615 | 0 |
| dropping_ou25_history | 141 | 60,547 | 0 |
| dropping_btts_history | 141 | 52,002 | 0 |
| moneyway_snapshots | 141 | 178,826 | 3 |
| live_snapshots | 141 | 160,275 | 51 |

- 58 FT result observations saved from currently settled matches, with score from `public.live_fixtures`; others not labeled FT until the source confirms it.
- Alarm source rows for this day were also captured, by matched physical fixture hash.
- New market/snapshot rows created during the initial transfer were copied by incremental cursor passes, with source/copy counts matching; a newly appearing 141st fixture was also copied across all eight datasets.
- Live-snapshot source hash matching was restricted to UID-or-null and the fixture's `kickoff-6 days` to `kickoff+12 hours` window; no overlapping repeated hash was found within six days for the 21 October fixtures at the time of preflight.
- `archive_runs` is **PARTIAL**, pending all future snapshots, new fixtures, final results, end-of-day source-to-archive full reconciliation and cold backup.
- The cursor uses strictly newer observation timestamps for catchup. **Late-arriving source rows at a prior timestamp require a final fixture-level raw count/content reconciliation** before certifying COMPLETE.

## Remaining requirements for a claim of 100% archival completeness

1. After the 21 October local fixture date and matches finish, rerun incremental capture for all eight datasets, copy any new fixture identities/alarms, and add verified FT results. Then perform complete source-versus-archive multiset comparisons (not merely totals).
2. Source is missing FT for 2 fixtures on 18 October and 4 fixtures on 20 October. Preserve missing state until authoritative evidence is available.
3. Verify durable Supabase cold backups for 18/20/21 and any preceding COMPLETE days still marked `COLD_BACKUP_PENDING`. The prior pg_net exporter queue/synchronous run had failed; no success has been verified. No source-retention cleanup is authorized.
4. For 20 October use the logical views for dropping performance research; physically duplicate historical rows intentionally remain because append-only safety forbids mutation.
5. Re-audit all existing COMPLETE days at per-fixture/per-market fidelity if strict external-independent 100% certification is required; a `COMPLETE` run status alone is not such a certification.

## Database schema changes made for safe research ingestion

- `research_archive_ou25_identity_lookup_20261021`: lookup index for research archive O/U2.5.
- `archive_repair_idempotent_daily_raw_receipts_20261021`: idempotent per-fixture copy receipts.
- `research_archive_20261020_append_only_logical_dropping_dedup_views`: read-only logical views for 20 Oct duplicate dropping.
- `research_archive_partial_day_stream_cursors_20261021` and `research_archive_stream_cursor_more_datasets_20261021`: per-fixture cursors for current-day streaming capture.

The Hetzner Remote Desktop Commander device `smartxflow` remained **offline** during this work; no Hetzner deploy or Replit sync was performed.
