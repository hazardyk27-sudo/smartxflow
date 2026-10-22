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
- **2026-10-22 correction (PREVIEW, not yet deployed):** each signal
  family/checkpoint is independent. A missing Early T-72 does NOT skip
  Base T-8/T-6, Early T-12, or other Early checkpoints. Only that due
  job is marked `SKIPPED_DATA/SOURCE_INCOMPLETE`. Base 1X2, OU25 and
  BTTS are independently evaluated: one missing market does not hide
  another market's real valid signal. When all markets are missing,
  that individual Base checkpoint is skipped without generating fake hits.
- Early Core T-72/60/40/24 uses its own historical checkpoints, not as
  entry requirements for non-Early engines. An Early T-60 candidate
  computed from real source despite missing earlier T-72 is visibly marked
  `HISTORY_INCOMPLETE` rather than claiming the *first-ever* hit
  was proven. Retention still requires its genuine source chronology.
- Authentically COMPLETED signals stay visible even when a different
  signal family for the same fixture had a source gap.
- Production V2 already contains wrongly propagated sibling
  `FIXTURE_SKIPPED_UPSTREAM_GAP` rows from the earlier policy.
  Reactivate these *unfinished* jobs in a distinct operator-gated
  transaction; do not delete any original source-gap jobs or immutable
  audit records.

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
missing genuine source skips only the corresponding checkpoint, and
completed historical V1 events remain excluded from the new V2-only feed.

## Safety / no fabrication

`SKIPPED_DATA` is distinct from `COMPLETED` and `NO_SIGNAL`.
The **new corrective** `sxf_base_skip_missing_source` PostgreSQL
function requires a live valid row lease token, a due checkpoint and
a future kickoff. It only transitions that one job and never mutates a
sibling family, historical completed signals or original Moneyway data.

The corrective claim RPC retains `FOR UPDATE SKIP LOCKED`, date-first
priority, per-job fencing and service-role-only execution. It removes
the old fixture-wide exclusion predicate. A missing market may produce
an `INSUFFICIENT_DATA` market decision but cannot veto another real,
independently complete market.

## Corrective rollout order (2026-10-22, NOT yet production-approved)

1. Pass targeted preview tests and review the exact SHA.
2. Obtain explicit promotion approval (per repository release contract).
3. Stop/disable Base worker and recovery timer; verify no checkpoint,
   reconciliation or discovery leases, and preserve Alarm and Moneyway.
4. Apply `migrations/2026_10_22_signal_motor_independent_checkpoints.sql`
   to replace the single-job skip and date-first claim RPCs.
5. In a separately authorized transaction with
   `sxf.independent_restore_gate=VERIFIED_STOPPED_AND_LEASE_FREE`,
   apply `deploy/signal_motor_v2_restore_sibling_jobs_20261022.sql`.
   It revives unfinished jobs wrongly mass-skipped by the previous
   fixture-level policy, retaining true source gaps and immutable audits.
6. Fast-forward the **exact approved preview SHA** to main, deploy that
   main SHA to Hetzner and restart the Base worker/recovery timer.
7. Verify today's fixture priority, independently completed Base/early jobs,
   correctly marked unverified Early first-history, missing-data-only
   per-job skips, visible completed signals, and 24/7 process health.

**Important:** a release cannot recover real prices a provider never sent;
`SKIPPED_DATA` documents that source gap. The 59-minute policy is a source
selection change versus prior 30-minute frozen snapshots, not a claim of
improved statistical performance. Do not compare these replay runs with
older 30-minute results as if their input policy were identical.

No Replit changes or user-PC access.
