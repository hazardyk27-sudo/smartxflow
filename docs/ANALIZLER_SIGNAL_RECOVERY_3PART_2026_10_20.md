# SmartXFlow Analizler — 3-Part Signal Recovery Plan (20 October 2026)

**Only GitHub \`preview\` changes.** No Replit, personal computer, Hetzner
deployment, SQL migration, Supabase writes, changes to frozen engine rules, or
automatic promotion. Production release needs separate user approval.

## Observed incident (read-only evidence; not a production-fix claim)

At approximately 17:30 Europe/Istanbul on 20 October:

- Existing \`sxf_base_health_snapshot()\` returned \`checkpoint_queue.pending_due=467\`,
  while the contiguous discovery gate is \`250\`. \`sxf_base_discovery_cursors\`
  reported \`last_scanned_at=2026-10-20T03:58:02Z\`.
- Current-day Base signal events were nine records on three physical fixtures.
  The distinct match count must never be confused with event count.
- The existing legacy engine tables had 14 rows across Early Money Lock and
  Underdog, not all physical fixtures with canonical \`fixture_uid\`.
- The last Base durable job completion was fresh; execution was not
  entirely stopped, but discovery and timely upcoming coverage were lagging.
- The user's 21-match total is not yet independently reconciled to a
  canonical fixture-by-fixture, source-by-source 21-row manifest.

### Part 1 / 3 — Near-term discovery isolation (THIS COMMIT)

1. Create an explicitly opt-in, **one UTC kickoff-hour at a time**, durable,
   idempotent upcoming fixture discovery path independent of the historical
   \`pending_due>=250\` pause.
2. Preserve the frozen 11 checkpoint tasks per fixture, canonical physical
   fixture identity, full catalog pagination and capacity upper bounds.
   Never truncate a busy window, advance a false watermark, fabricate signals
   or silently bypass lease/ACK uncertainty.
3. Add unit and regression tests, including the existing worker's default-off
   policy, backlog/capacity pauses and the no-migration/no-deployment boundary.

**Part 1 boundary:** \`--near-term-discovery --near-term-hour-offset=N\`
selects exactly one bounded window (\`-1<=N<=12\`) only on an **already
separately authorized** durable worker. Default is OFF. It is not automatic
12-hour coverage, live claim priority or an active production fix.
Do not interpret \`IDEMPOTENT\` as an observed scan of every future hour.

### Part 2 / 3 — Timely checkpoint execution and backlog control (PREVIEW CODE READY; LIVE NOT ENABLED)

1. Introduce a deterministic bounded hour-bucket rotation with restart-safe
   scan diagnostics, never claiming future-hour coverage prematurely.
2. Separate urgent *due* T-8/T-6 work capacity from historical
   \`WAITING_DATA\`/reconciliation debt; explicitly test fair scheduling,
   lease fencing and failed/unknown ACK handling. Preserve retrospective
   timing labels instead of presenting late results as prematch real-time.
3. Add diagnostic metrics/alerts for discovery staleness, due checkpoint
   age and missing fixture coverage; run disposable and GitHub CI tests.

### Part 3 / 3 — Complete Analizler visibility and end-to-end acceptance (NOT STARTED)

1. Reconcile **each claimed 21-match signal** by canonical physical identity,
   origin table, motor, kickoff time, stage and API visibility; preserve
   legacy and Base engines as separately named provenance groups.
2. Implement authorized, bounded server-side adapter(s) for legacy
   historical signals and show complete verified Base motor cards.
   No private table exposed to browser and no user-defined fake signals.
3. Test date/identity dedupe, PRO auth, API paging, desktop/mobile 7-locale
   render and no-score-fabrication cases. Prepare an exact-SHA approval
   package; do **not** deploy without user approval.

## Acceptance for whole project

- Every real engine's expected due scan has a diagnostic audit trail;
  no stale discovery cursor is reported green.
- Daily unique fixture counts distinguish raw rows, stage events,
  source duplicates, source-incomplete records and truly final signals.
- The app can show each authorized genuine signal in its proper engine
  while keeping late/unconfirmed data explicit.
- Database writes, worker activation and Hetzner release remain blocked
  unless separately authorized and verified.

## Part 2 implementation notes

- `rotation.py`: deterministic UTC-minute rotation across 14 relative one-hour kickoff buckets (-1 through +12); no persistent watermark, each missed minute is UNVERIFIED and scans are idempotent on restart. Enabled only with `--near-term-discovery --near-term-rotation` on an already approved worker.
- New proposed `sxf_base_claim_due_jobs_lane` service-role-only SQL RPC separates recent due BASE T-8/T-6 (<3h old) from the backlog, preserves original token fencing, and rejects multi-row claims. This proposal has **not** been migrated on live Supabase.
- `--priority-lanes` additionally requires `SXF_BASE_PRIORITY_LANES_APPROVED=yes`, 3+ max jobs per cycle, and an already deployed authorized lane RPC; old claim behavior remains default. Quotas: 2/3 LIVE, 1/3 BACKLOG, with independent empty-lane handling.
- `queue_diagnostics` assesses actual latest discovery scan timestamp, pending due count, oldest due age and reconciliation backlog; the known old `lag_seconds=0` metric is never interpreted as freshness when `last_scanned_at` is stale.
- These changes only prepare for future supervised activation; CI checks a disposable PostgreSQL schema and synthetic time, not a verified real 24-hour operation or a fixed live app.

- Telemetry now distinguishes `healthy_cycle` (safe lease execution) from `coverage_state=DEGRADED|UNVERIFIED`, with `discovery_fresh` independently computed from actual last-scanned time; a stale discovery cursor is never falsely marked coverage-healthy.
- The proposed lane RPC is also tested under a two-worker PostgreSQL contention race; stale tokens cannot renew the resulting lease. No live DB migration was applied.

## Part 3 verified identity join and feed wiring (preview only)

- Existing PRO-only `/api/base-signals/feed` now combines Base shadow with five **explicitly legacy-prefixed** old motor sources, preserving their original selection. Distinct provenance prevents treating an early-money historical alert as a Base checkpoint hit.
- The legacy server-side adapter uses capped pagination, 21-day bounded history, exact team/league/TR date, authentic unique physical fixture matching and exact ISO kickoff where supplied; ambiguous/missing identity records are reported as excluded, not fabricated. Duplicate records of the same engine/fixture/selection are collapsed with an explicit dedupe counter.
- Legacy price at detection and verified final score are not present in enough source evidence, so their cards intentionally say price unavailable and score unverified. Base existing independent verified scoreboard logic remains unchanged.
- Last observed 20 October: 9 Base raw signal events across 3 physical fixtures, 14 legacy rows across 12 team pairings; Napoli–Bodø/Glimt had two Underdog records for the same team/selection, making 13 legacy displayed records across 12 fixtures and 22 total displayed signal records across 15 fixtures assuming continued consistency. This is **not verification of the user's 21 distinct fixtures**.

## Part 3 regression gates

- Added isolated tests for all five legacy source engines, canonical one-fixture matching, duplicate same-engine signal consolidation, identity ambiguity rejection, source pagination fail-closed, server-only secret access and no guessed odds/results.
- Added two-viewport × seven-language Chromium regressions for separate Base/legacy card drill-down and provenance/warning labels; no extra HTTP requests on language switch.
