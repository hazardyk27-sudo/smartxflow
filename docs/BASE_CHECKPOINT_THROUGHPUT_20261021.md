# SmartXFlow Base: live-checkpoint throughput + backlog recency (2026-10-21)

## Problem observed before correction
Production database at approximately 12:29 UTC:
- 8,779 total jobs; 289 completed; 3,484 pending due; 1,062 WAITING_DATA.
- Recent worker progress resumed, but 72 prematch BASE T-8 jobs for approaching
  fixtures were still unattempted; 354 Early T-72 and 314 Early T-60
  checkpoint jobs were due and unattempted.
- A fixed 12-job / 60-second worker loop spent about one third of its quota
  on historical backlog and could not catch up quickly after the outage.
- BACKLOG previously sorted earliest checkpoint first, even when a match
  started long ago and its upstream source price history may no longer be
  available. This risked crowding out recent evidence-backed repairs.
- Source completeness remains low; NEVER replace a missing side with
  assumed odds, volume or shares.

## Applied SQL migration
`migrations/2026_10_21_sxf_base_backlog_recent_first.sql`
retains original postgresql lease-based, token-fenced, FOR UPDATE SKIP LOCKED
job claim and 2:1 LIVE/BACKLOG quotas.
Within BACKLOG only, matches kicked off within the preceding 24 hours (or
not yet kicked off) are considered before older immutable debt. Old jobs
are not deleted or marked successful.
Read-only DB inspection confirmed:
- recent_backlog_priority = true
- fenced_claims = true
- service_role_access = true

## Code
- Service runtime maximum per cycle from 12 to 24 checkpoint claims.
- Intercycle wait from 60 seconds to 30 seconds.
- Each full cycle reserves 16 LIVE slots and 8 BACKLOG slots, provided
  queues have work; an exhausted lane does not starve the other.
- Reconciliation remains at max 1 job/cycle; protected exit 3/4 remains.
- Include live/backlog completed and WAITING_DATA counts separately in
  the existing structured journal so real throughput can be measured.

## Tests and live acceptance
- GitHub Actions 132 passed, no motor selection thresholds modified.
- Both current and historical checkpoint work uses the existing original
  immutable source snapshots; no backfill or hypothetical source fields.
- Confirm deployed SHA and new systemd ExecStart are actually effective,
  verify checkpoint attempts, T-8/T-6 completions and no new uncertain
  transactions after deployment. Any total-cover or all-engines claim
  requires separate read-only event validation.
