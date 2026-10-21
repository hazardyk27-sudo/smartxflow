# SmartXFlow — Sinyal Motoru: daily first, real checkpoint snapshot, skip missing

This is a user-requested **new processing policy** built on the existing single
Betwatch → Supabase → Hetzner Base source. The deployment and migrations
must be released together at the same tested GitHub main SHA; do not turn on
the new worker before the database migration, and do not turn on the database
claim policy before the new worker has the new safe skip RPC.

## User-visible policy

- First inspect **today's Istanbul-local matchday**, sorted by actual kickoff
  time; **only then tomorrow**, then following days.
- Each fixture has immutable T-72/T-60/T-40/T-24/T-12/T-8/T-6/T-5/T-4/T-3
  jobs, but only checkpoint jobs currently due may be evaluated. No future
  snapshot is ever copied backwards to an earlier checkpoint.
- The closest **real complete observed snapshot at or before T** within
  **59 minutes** is selected for that T. This window does not overlap the
  neighboring hourly anchor; V2 requires distinct 1X2 hour anchors.
- Missing 1X2/OU25/BTTS selections at Base T mean the **checkpoint is skipped
  and logged**, rather than synthesizing missing values, marking NO_SIGNAL
  or retrying the same immutable empty source window indefinitely.
- A missing Base T-6 observation **never uses T-8 as a substitute**.
  Authentic prior T-8 events remain historical, not new T-6 picks.
- Backlog of **already kicked-off** matches is no longer granted a worker
  claim quota. All 24 available bounded processing slots prioritize future
  kickoffs in local date order.
- The legacy Underdog, Confirmed Money V1/V2, Fake Sharp and Early Money Lock
  engines are retired. Their dedicated writer service is explicitly stopped
  and disabled in deployment; the independent **Alarm Engine remains active**.
  The new feed does **not** fetch legacy tables or show their old cards.
  Historical source/legacy records are **not deleted**, for audit integrity.
- Seven languages use the new UI name, **Sinyal Motoru / Signal Engine**.

## Safety / no fabrication

`SKIPPED_DATA` is a distinct terminal state; it is NOT `COMPLETED` or
`NO_SIGNAL`. The new `sxf_base_skip_missing_source` PostgreSQL function
requires a live valid row lease token and a due checkpoint. It only updates
the existing checkpoint job, with a fixed source-only reason; it never
inserts signal events or edits original moneyway rows.
The `sxf_base_claim_due_jobs_lane` migration preserves PostgreSQL
`FOR UPDATE SKIP LOCKED`, per-job lease tokens, 1-job claims, and
service_role-only execution. Existing completed events remain untouched.

## Safe rollout order

1. Focused tests PASS on preview, seven language JSON files checked and
   `static/js/base-signals.js` syntax checked.
2. Snapshot pre-deployment live state: original Moneyway scrape freshness and
   Base worker service health. Preserve old historical data.
3. Controlled migration 1: extend constrained job state vocabulary and
   install the token-fenced terminal source skip RPC.
4. Controlled migration 2: prioritize current/future Istanbul-local
   matchdays; keep original claim fencing intact.
5. Release approved exact SHA from preview to main and deploy Hetzner.
   Old legacy writer is disabled, Alarm Engine continues running.
6. Verify `SKIPPED_DATA` increments only for genuinely incomplete
   checkpoint windows, no new `WAITING_DATA` churn from Base worker,
   `sxf_base_signal_events` still includes real priced choices only, and
   today's fixtures are processed before later kickoff dates.
7. Re-check 1X2/OU25/BTTS source timestamps and actual 24/7 worker health.

**Important:** a release cannot recover real prices a provider never sent;
`SKIPPED_DATA` documents that source gap. The 59-minute policy is a source
selection change versus prior 30-minute frozen snapshots, not a claim of
improved statistical performance. Do not compare these replay runs with
older 30-minute results as if their input policy were identical.

No Replit changes or user-PC access.
