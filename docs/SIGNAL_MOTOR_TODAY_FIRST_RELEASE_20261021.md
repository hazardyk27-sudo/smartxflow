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
- Missing original source data at any due T checkpoint means the **whole
  fixture is skipped**, not just the failing checkpoint. The triggering job
  receives `SOURCE_INCOMPLETE`; its unfinished sibling jobs receive
  `FIXTURE_SKIPPED_UPSTREAM_GAP` (they are not falsely labeled as missing
  observations at checkpoints that have not happened). The claim RPC
  excludes already-skipped fixtures, including after a discovery replay.
  Previously COMPLETED jobs and immutable source/signal events are preserved;
  finished signal records belonging to skipped fixtures are hidden only
  from the live signal feed. No missing odds are fabricated or re-tried forever.
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

## 22 October fresh-start decision (explicit user instruction)

Do **not** reuse the existing V1 PENDING/RETRY/WAITING_DATA/expired LEASED
backlog. Version 2 of the autonomous Signal Motor uses
`SXF_SIGNAL_MOTOR_V2_2026_10_22`, so a legacy pending checkpoint can never
be accidentally claimed by the new worker. The live feed reads only V2 events.

**Run the operator-gated fresh-start transaction**
`deploy/signal_motor_fresh_start_cutover_20261022.sql` **only after**
confirming both the worker and recovery timer are stopped/disabled, there
are no active leases, and the exact approved production SHA is prepared.
The transaction admits V2 enqueues, physically deletes *never-attempted*
V1 PENDING jobs, terminally retires V1 WAITING_DATA/RETRY/expired LEASED
jobs as SUPERSEDED, drops old outstanding reconciliation work, and resets
the discovery cursor to midnight at the current Europe/Istanbul date.

Important data-integrity detail: V1 WAITING_DATA/RETRY jobs already have
immutable attempt journals (32,500+ as of the initial audit). The database
deliberately forbids their physical deletion through an append-only trigger
and a RESTRICT foreign key. Never bypass either protection. SUPERSEDED is
the permanent nonclaimable equivalent; the fresh V2 queue starts empty
and gets new work only from source discovery. Historical COMPLETED
signals, evaluations, and Moneyway snapshots are preserved.

**Never run this script during a live worker cycle** or treat an instantaneous
zero-active-lease sample as proof the worker was stopped. The operator must
set the session-level guard `sxf.signal_fresh_start_gate` to
`VERIFIED_WORKER_AND_TIMER_STOPPED` only after independently verifying
those services are stopped. The SQL locks and checks all relevant tables
and aborts if a conflicting lease or previous V2 start is found.

Release verification must confirm V1 has no claimable jobs, V2 enqueue
RPC accepts the new ruleset, the discovery cursor starts on the Istanbul
current day, the first V2 LIVE claims prioritize today's upcoming matches,
missing genuine source skips whole fixtures once, and completed historical
V1 events are absent from the new live signal feed.

## Safety / no fabrication

`SKIPPED_DATA` is a distinct terminal state; it is NOT `COMPLETED` or
`NO_SIGNAL`. The new `sxf_base_skip_missing_source` PostgreSQL function
requires a live valid row lease token, a due checkpoint, and a kickoff in
the future. One terminal operation also marks that fixture's other unfinished
jobs as skipped; it refuses to invalidate another active leased job. It never
inserts signal events, modifies COMPLETED jobs or edits original moneyway rows.
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
4. After **verified worker and recovery-timer stop** and zero active leases,
   apply the additive migration `2026_10_21_signal_motor_skip_future_only_guard.sql`
   to require `kickoff_utc > now()` at terminal skip time; migration 1 was
   already installed in production and must **not** be replayed or edited.
5. Controlled date-first claim migration
   `2026_10_21_signal_motor_today_first.sql`: prioritize current/future
   Istanbul-local matchdays while preserving token-fenced leases.
6. Release approved exact SHA from preview to main and deploy Hetzner.
   Old legacy writer is disabled, Alarm Engine continues running.
7. Verify `SKIPPED_DATA` increments only for genuinely incomplete
   checkpoint windows, no new `WAITING_DATA` churn from Base worker,
   `sxf_base_signal_events` still includes real priced choices only, and
   today's fixtures are processed before later kickoff dates.
8. Re-check 1X2/OU25/BTTS source timestamps and actual 24/7 worker health.

**Important:** a release cannot recover real prices a provider never sent;
`SKIPPED_DATA` documents that source gap. The 59-minute policy is a source
selection change versus prior 30-minute frozen snapshots, not a claim of
improved statistical performance. Do not compare these replay runs with
older 30-minute results as if their input policy were identical.

No Replit changes or user-PC access.
