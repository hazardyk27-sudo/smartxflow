# 2026-10-14 / 2026-10-15 SXF checkpoint backfill provenance (v1)

Status: **RESEARCH CHECKPOINT SUBSET / NOT FULL-ENGINE FINALIZATION**. Append-only, do not overwrite original daily samples.

- Source: production Supabase `research_archive.fixtures`, `research_archive.results`, and archived `research_archive.moneyway_{1x2,ou25,btts}_history`.
- Date basis: `research_archive.fixtures.local_date` (Europe/Istanbul).
- Scope: every archived fixture for each date; per-market latest **usable** stored snapshot observed at or before T-6/T-5/T-4/T-3. No post-checkpoint price or money data is used as a feature.
- Engine sample thresholds from `BACKFILL_METHOD_v1.md`: 1X2 Concentration V1 / Heavy, V2 challenger, Surprise Team, Over Stable / Premium, BTTS Yes.
- V2 research calculation in these files: minimum chosen-side money share observed within the *immediately preceding three hours* and maximum-versus-minimum chosen-side odds within that window. Needs equivalence audit against earlier archived V2's frozen *anchor* calculation **before** combining V2 performance across dates. `anchor_age_min` remains blank when no canonical checkpoint anchor can be verified.
- `FRESH_LE_30M` means snapshot age at checkpoint <= 30 minutes; stale snapshots are retained and flagged rather than silently excluded.
- Final score and postmatch win/non-loss labels are appended strictly as POST outcomes; no result was used to qualify a prematch signal.
- Early Money T-72/T-60/T-40/T-24/T-12 and retention-55 observations are **not** yet included; do not claim these daily files measure all signal families.
- Confirmed daily files: 2026-10-14 (120 observations, 28 distinct fixtures, 12 stale); 2026-10-15 (222 observations, 35 distinct fixtures, 0 stale). Verified byte-for-byte after GitHub commit.
- 2026-10-16 onward: pending. Archive history tables have no local_date / fixture_uid index and heavy checkpoint requests timed out; avoid loading production with repeated unindexed historical scans. Research Commander was offline on 2026-10-21.
- The existing 2026-10-17 sample must remain unchanged. 2026-10-18 Supabase raw archive status is PARTIAL. 2026-10-20/21 have no `research_archive.archive_runs` entry as of this check.

Do not present these two files as a complete reconstruction of all SXF signal families or a validation-ready all-day comparison until Early Money coverage, V2 anchor equivalence, and cross-day matching are audited.
