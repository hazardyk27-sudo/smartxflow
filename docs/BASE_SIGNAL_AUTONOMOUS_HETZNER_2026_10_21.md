# Autonomous 24/7 Base signal engine — Hetzner

## Objective

The 2026-10-20 temporary priority shadow stopped in approximately ten
minutes after a safe `PAUSED_CAPACITY` outcome. The follow-up one-day
transient worker similarly does not survive the scheduled 24h boundary.
The Base source remains in PostgreSQL; no UI-only change can produce missing
signals. A permanent systemd service is needed to discover, enqueue,
evaluate and append immutable Base events without an assistant or agent.

## Activation invariants

1. Only the exact GitHub `main` release SHA gets deployed to Hetzner.
2. Service_ROLE API and source are in the existing private `.env` file;
   activation gates belong to a separate root-controlled, non-secret
   `/etc/smartxflow/base-worker.env`.
3. `deploy/sync_runtime_units.sh` installs the tracked service but deliberately
   does **not** start or enable it. The guarded GitHub activation action
   checks production SHA, required SQL indexes/RPC, existing services, and
   any old worker. It then enables and starts the permanent unit.
4. Service is `WantedBy=multi-user.target`, no RuntimeMaxSec, and
   `Restart=on-failure` after two minutes. Ambiguous claim/commit
   result (exit 3) and missing cursor (exit 4) **never** restart.
5. Every loop rotates through near-term UTC kickoff buckets, enqueues
   via fenced/idempotent Supabase RPC, then processes priority LIVE and
   BACKLOG jobs with bounded quotas (12 per loop), including 1
   reconciliation job. Memory 320M, tasks 48; no tracked runtime edits.
6. The near-term source budget increases from 1,200 to the already validated
   upper bound of 2,500 due jobs when explicitly priority-gated. The
   conservative global cursor discovery remains paused under high backlog;
   the live rotating discovery stays independent. When projected work
   would exceed the bound, worker continues and announces
   PAUSED_CAPACITY/DEGRADED rather than fabricating complete coverage.
7. Confirm `systemctl is-enabled` and `is-active` and multiple log
   cycles, then check Supabase events, due jobs, and physical fixture
   coverage. A green systemd state is not proof of 100% fixture capture.

## Known limitations

- The SQL health snapshot currently has no source ingestion watermark;
  `source_capture_verified=false` is expected.
- Historical contiguous discovery is paused when due queue >=250,
  and near-term rotation can hit a >50-fixture UTC bucket. Both are
  explicit coverage gaps, **not** an opportunity to invent signals.
- `WAITING_DATA` means missing complete source snapshots and remains
  in the due/retention audit; older matches cannot be advertised as
  timely pre-match betting alerts.
- Do not silently reset the queue, rewrite recorded_at, invalidate
  previously finalized bets, or backfill into apparent real-time hits.
