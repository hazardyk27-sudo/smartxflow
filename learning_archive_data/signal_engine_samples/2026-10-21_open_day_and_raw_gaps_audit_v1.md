# SXF research archive — open-day staging and remaining raw gaps
As-of: 2026-10-21 03:40:17 Europe/Istanbul. Append-only audit. No production schema or data has been altered.

## October 21 (current day: not settled)

21 October at approximately 03:24:52 local: 139 fixture rows in primary public database, 9 kicked off, 130 future, 3 recorded FT statuses. No final daily performance sample can be certified yet.

PRE-only snapshot staging saved in `2026-10-21_0340_prematch_checkpoint_staging.json` (commit `27a7a3016c6c91c4f3424fc0e318c4ff0f0746e7`).
- Fixed observation freeze: `2026-10-21T03:40:17+03:00`.
- Only checkpoint cutoffs which had elapsed by the freeze were eligible: T-6 22; T-5 22; T-4 22; T-3 18 = 84 fixture/checkpoint opportunities.
- Indexed primary history supplied valid pre-cutoff snapshots at 71 1X2, 63 O/U2.5, 49 BTTS checkpoints.
- Sources: `public.moneyway_1x2_history`, `public.moneyway_ou25_history`, `public.moneyway_btts_history`; fixed 8–3 hour pre-kickoff window and no snapshot after its checkpoint.
- This file contains **no scores, postmatch win/loss labels, or not-yet-elapsed checkpoints**. It is not the daily final CSV. Later full-day extraction must be in a **different** append-only file.

## October 18 (raw archive marked PARTIAL)

`research_archive.archive_runs` reports `status=PARTIAL`, 400/400 archived fixtures, missing `rows_1x2/rows_ou25/rows_btts` run totals and `notes.validation=IN_PROGRESS`, `notes.cold_backup=COLD_BACKUP_PENDING`, `notes.full_archive_complete=false`. These are real raw-archive integrity blockers; do not flip `status` to COMPLETE without resolving them.

Archived market history fixtures with non-null UID as checked:
- 1X2: 338,582 rows, 400 distinct fixture UIDs.
- O/U2.5: 157,278 rows, **212 distinct fixture UIDs**. Therefore 188 of the 400 archived fixture UIDs do not have direct UID coverage in this archived O/U table. This may include UID mapping issues; it is **not proof** that these matches never had source O/U data.
- BTTS: 201,353 rows, 400 distinct fixture UIDs.

The checkpoint performance CSV for 18 October has 409 selected observations / 95 distinct signal fixtures; it does NOT imply raw O/U data is complete. No research_archive remediation performed.

## October 20 (raw archive missing but primary source survives)

No `research_archive.archive_runs` record or archived day snapshot was confirmed for October 20. The 20 October **derived** checkpoint performance CSV is saved (197 observations, 36 unique signal matches) but is NOT a replacement for a full raw archive.

Public data has 139 fixture rows; 135 FT labels joined by match hash. Four unmatched fixture identities:
| Local kickoff | League | Home | Away | match_id_hash |
|---|---|---|---|---|
| 15:00 | Argentinian U20 | Sportivo Dock Sud U20 | CA Ituzaingo U20 | `ec2109923f3c` |
| 16:00 | Argentinian U20 | Villa San Carlos U20 | CA Claypole U20 | `089b66317e89` |
| 15:00 | Argentinian U20 | Argentino de Merlo U20 | Argentino de Quilmes U20 | `efec0ebb5705` |
| 15:00 | Argentinian U20 | Deportivo Espanol U20 | San Martin Burzaco U20 | `6f4f34b340e2` |

The four missing FT matches were not silently filled with scores. Previously archived *signal candidate rows* for 20 October happened to all match results; this is not proof that all 139 fixtures have results.

## Next safe actions

1. Finish 21 October final daily checkpoint export only after the local fixture day closes and real result labels can be verified.
2. Repair and validate the 18 October O/U2.5 missing/misaligned archive identities and cold backup status.
3. Copy 20 October raw archive with documented source retention, idempotent dedupe and verified counts; avoid pretending derived checkpoint CSV replaces raw history.
4. Reconstruct frozen Early Money (T-72/T-60/T-40/T-24/T-12) and Retention 55 families, which are NOT covered by new daily checkpoint CSVs. Audit V2 3h anchor definition vs provisional min/max windows before publishing merged engine performance rates.
5. Commander `smartxflow` has been offline during this investigation. Do not run repeated unindexed long-running SQL scans against the production archive.

Original pre-existing daily CSV files remain untouched. No production app deployment, Replit sync, or Supabase ACL changes occurred.
