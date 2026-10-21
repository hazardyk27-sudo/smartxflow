# Base Early Money — source and WAITING_DATA audit (21 October 2026)

## Live Supabase evidence

At about 13:08 UTC, `EARLY_CORE T-72` jobs in `WAITING_DATA`:
413 total; 317 fixtures had `fixtures.created_at > checkpoint_at`,
and 96 fixture rows existed by checkpoint time. For T-60: 345 total,
196 late-created; T-40: 175 total, 97 late-created; T-24: 118
total, 23 late-created.

This shows that a substantial portion of historical Early missingness
coincides with a **canonical fixture identity that was unavailable at
checkpoint time**. It does not establish exactly when the upstream provider
first offered the match, nor authorize manufactured old source snapshots.

A separate bounded read-only sample of 45 currently relevant T-72 jobs
(due within 18h before 13:12 UTC) found:
- 32 with zero 1X2 snapshot rows in the actual T-72 [-30m,0m] source window;
- 5 with rows present but fewer than three distinct 1X2 outcomes;
- 8 with all three selections represented somewhere in the window;
- only 8 completed jobs, 37 still `WAITING_DATA`.
Having three distinct selections across *different* timestamps is not
proof of any **single complete 1X2 snapshot**. The actual validator retains
that stricter per-timestamp rule.

All Base decisions must derive solely from actually observed Moneyway
snapshots within each frozen checkpoint freshness window. Later live quotes,
a changed kickoff, or postmatch outcomes may never fill missing historical
observations.

## Released remedy — age-aware missing-source retries only

The durable Base worker previously kept polling immutable old checkpoint
windows at most an hour apart, competing with new T-8/T-6 and Early work.

`source_wait_delay_seconds()` chooses:
- source window <=2h old: retry in 180s to catch ingestion lag quickly;
- window 2–24h old: retry in 3600s;
- source window >24h old: retry in 21600s (6 hours).

All jobs stay `WAITING_DATA`, **never** `COMPLETED`. The existing
lease-token + live lease-expiry fences remain mandatory. Failed reads use
their previous short exponential-error retry and unknown write ACKs
still cause the protected service stop. The data source is not modified.

Migration `2026_10_21_sxf_base_waiting_data_age_retry.sql`
widens **only** `sxf_base_wait_for_data`'s validated retry cap from
3600 to 21600 seconds; checkpoint error retries, ordinary RPCs, and
reconciliation limits are unchanged. Supabase verified the new cap,
both lease fences and service_role permission after applying the migration.

A genuine historical backfill may still make a previously missing
checkpoint evaluable at its next retry; it can never be declared timely
for a kickoff whose checkpoint has already passed.

## Acceptance

- Full Base test suite must remain green (now at least 136 tests).
- Production GitHub `main` and actual Hetzner SHA must match the
  approved tested commit.
- `WAITING_DATA` jobs older than 24h should progressively gain
  `next_attempt_at` approximately 6h in the future as their current
  retry becomes due. Do not bulk-update old jobs or invent success.
- Health monitor still reports missing source, old backlog and source
  coverage degradation; no unwarranted '10/10 complete' announcement.
- The upstream fixture catalog / prematch horizon limitation remains
  a separate source-availability issue, NOT magically solved here.

Replit and the user's PC are excluded throughout.
