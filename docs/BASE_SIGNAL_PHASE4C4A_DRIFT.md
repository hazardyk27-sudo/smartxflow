# SmartXFlow Phase 4C4A — reschedule safety and recurring overlap (NOT DEPLOYED)

This proposed migration adds a `SUPERSEDED` job state, an append-only
`sxf_base_fixture_drift_events` audit, and UID/kickoff authority triggers
on new evaluation and signal-event inserts. A completed historical evaluation
is retained unchanged. Any new event for an old kickoff is rejected once the
current `fixtures.fixture_uid` record points to a different kickoff.

`sxf_base_quarantine_fixture_drift` marks obsolete job rows as SUPERSEDED
without deleting them, using a bounded, concurrency-safe batch. The optional
`rolling_rescan_once` scans a 1–30 day overlapping UTC kickoff interval and
re-enqueues the *same 11 frozen checkpoint tasks* through the existing
idempotent enqueue RPC; then invokes drift quarantine. The function is not a
service scheduler and is NOT automatically activated.

Limitations: A rolling kickoff window cannot prove complete discovery after
fixtures were created/rescheduled outside that window; a native change-log or
ingestion timestamp is still required. Drift quarantine is scoped to fixtures
still present in the `fixtures` table. The historical events remain
queryable and MUST be excluded from current signal projections after a
SUPERSEDED job. Before production, evaluate physical fixture UID remaps,
deletions, cancellation, fixtures provider latency, and source-read index cost.

No modification to frozen motor rules, threshold constants, user predictions,
`main`, Replit, Hetzner, or live Supabase. Run schema only against disposable
CI PostgreSQL until explicit approval.
