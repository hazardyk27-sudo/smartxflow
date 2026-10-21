# SmartXFlow raw archive recovery / safety audit v3 — 2026-10-21

**Status: PARTIAL. Do not represent all days as source-equivalent, deduplicated, cold-backed-up and FINAL.** This append-only report updates the earlier `2026-10-21_raw_archive_recovery_progress_v2.md` and does not rewrite earlier historical findings.

## 20 October — retained main raw sources

Local date `2026-10-20`: 139 physical fixture identities and 135 source-available live result rows (four Argentinian U20 results still unverified in the source). Three principal histories and three dropping histories were copied in fixture-scoped transactions. `research_archive.raw_backfill_receipts` has **139/139 fixture receipts** for each of these eight datasets:

| Dataset | Receipt-count source rows | Status |
|---|---:|---|
| `moneyway_1x2_history` | 75,111 | Receipt and source copy count matched |
| `moneyway_ou25_history` | 66,734 | Receipt and source copy count matched |
| `moneyway_btts_history` | 54,138 | Receipt and source copy count matched |
| `dropping_1x2_history` | **71,928** | **UNSAFE: actual archive table contains duplicates; receipt total is not actual row total** |
| `dropping_ou25_history` | 66,596 | Receipt and source copy count matched |
| `dropping_btts_history` | 54,022 | Receipt and source copy count matched |
| `moneyway_snapshots` | 202,308 | Available source matched, four fixtures no source |
| `live_snapshots` | 315,349 | Source by hash + fixture kickoff time window; four fixtures no source |

20 Oct alarm families were verified by source-vs-archive event IDs, **already present**, no additional insertion: Sharp 10, Insider 0, Bigmoney 20, Volumeshock 33, Dropping 0, Publicmove 0, Volume Leader 29, MIM 74; sum **166**. An old fixture hash collision exists between Sporting San Miguelito vs Tauro on 13 and 20 Oct; time-window + UID context must be preserved for source matching.

### Critical duplicate fault — 20 Oct Dropping 1X2

As measured after more than one writer had been active on the database:
- `research_archive.dropping_1x2_history WHERE local_date='2026-10-20'`: **143,866 physical rows**.
- **71,934 unique raw JSON payloads** after removing only archive metadata (`local_date`, `source_fingerprint`, `archived_at`).
- Therefore **71,932 repeated payload rows** (143,866−71,934).
- Original directly UID/hash-matched source had **71,928 rows** in the completed daily receipt set. There are **six extra distinct archive payloads versus the source count**; their provenance must be checked, NOT automatically deleted or invented.
- `research_archive.archive_runs` for 20 Oct currently remains `PARTIAL` and earlier note `PARTIAL_DUPLICATE_DROPPING_1X2` is correct, but stored `rows_dropping_1x2_history=109047` had already become stale as another batch appeared; refresh only after all writers quiesce and an audited repair is performed.
- No destructive deduplication, deletion, mutation or provenance rewrite was executed in this audit.

**Safety blocker:** An additional active database writer was observed copying 18 Oct dropping history (pg_stat_activity showed separate active management-API requests while earlier transaction results were being checked); receipts for 18 Oct increased between independent calls. No additional bulk writer was started in parallel from this audit once concurrent activity was confirmed. A deduplication job must not race with ingestion.

## 18 October — recent recovery progress

`research_archive.fixtures`: 400/400 UIDs. `research_archive.archive_runs` still `PARTIAL`; source retention cleanup remains disallowed.

Source-direct (fixture_uid + match_id_hash) and archived raw counts:
- Moneyway 1X2 **338,582** source; **338,582** archived.
- Moneyway O/U2.5 **313,092** source; **313,092** archived after restoring the original 188 missing UIDs (400/400).
- Moneyway BTTS **189,989** source but previously **201,353** archived — extra archive rows require an identity/alias/provenance audit. Do not assume these are legitimate or duplicates without verification.
- Dropping 1X2 **292,013** direct source vs **324,926** archived — extra archive rows require identity/alias/provenance audit.
- Dropping O/U2.5 **269,636** archived and **400/400** UIDs (source also 269,636). This table was originally empty for the day; it was subsequently populated during this repair sequence. The corresponding `raw_backfill_receipts` show 400 fixture claims and 269,636 rows.
- Dropping BTTS **192,362** archived and **400/400** UIDs, after restoring 296 previously missing fixtures. Source full direct-row count query hit a 120-second timeout, so **count equivalence to source is NOT certified**.
- Moneyway snapshots **707,877** archived for **396 UIDs with source** (source-direct = **687,277** rows from 396 fixtures; 20,600 extra archived rows need identity/provenance check). A source-ID audit before final copy found 184,341 missing source IDs that were subsequently backfilled; don't count the 20,600 extras as proven legitimate without identity audit.
- Live snapshots **920,675** archived for **398 UIDs with source**; 2 UIDs lacked available source. Source-vs-target row identity matching not fully audited.
- Alarm family counts, result versions, fixture_aliases, cold backup, archived fingerprints and strict all-dataset completeness remain to be independently validated.

## Operational status and remaining work

- Hetzner Commander device `smartxflow`: OFFLINE during this work; no access to user's personal computer.
- Replit, GitHub `preview`/`main`, application deployment and production signal engine were not changed. Archive data changes are confined to research_archive and append-only `learning-archive` notes.
- Cold export to durable object storage is still not verified; a prior `pg_net` request stalled and synchronous export failed with HTTP cancellation.
- 21 October was still in progress at this audit, so do not call current-day full-history and settled scores complete.

**Safe next steps:**
1. Quiesce other writers; identify and preserve complete source-backed 20 Oct Dropping 1X2 payloads, determine the six additional identities, and plan a **backed-up, reversible, explicitly approved** removal of genuine duplicate physical rows. Do not issue blind DELETE/TRUNCATE.
2. Verify 18 Oct excess BTTS history, dropping1X2 and snapshot rows against source-ID/UID/hash/kickoff provenance. Restore truly missing source rows, but never merge different physical matches sharing legacy hashes.
3. Finish 18 Oct alarms/results/source fingerprint and source counts; only then update daily run status and row totals.
4. Repair the verified cold backup exporter and preserve raw ticks before any retention cleanup.
5. Finalize 21 Oct only after the local match day closes, postmatch results exist and raw source completeness is verified.

All numerical statements above were based on direct Supabase results or prior receipt verification; production source tables were treated as read-only. Any inconsistent archived table totals are explicitly flagged rather than normalized away.
