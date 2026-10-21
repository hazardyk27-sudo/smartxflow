# Base Worker — bounded checkpoint and native watchdog fix (2026-10-21)

Scope: **Step 1 only** — autonomous Hetzner Base worker stalls and safe recovery.
This change deliberately does not adjust frozen Base signal selection criteria,
scraper ingestion, old predictor, Replit, or other production applications.

## Root cause addressed

A single historical Early retention checkpoint can fetch many paginated
Moneyway snapshots without a *whole-job* timeout while periodically renewing
its database lease. As a result the process may stay `active` and leased for
multiple minutes without completing any new checkpoint or discovering the
next fixture hour.

## Implementation

- `durable_runtime.execute_claims`: 150-second monotonic read budget for
  each claimed checkpoint; on budget exhaustion use existing fenced
  `sxf_base_fail_job` with bounded retry. No partial signal is committed.
- A lease renewal error is explicitly an uncertain ownership outcome and
  **cannot** be followed by `fail`, `wait` or `complete`.
- `systemd_watchdog.SystemdNotifier`: local systemd `READY=1` and
  `WATCHDOG=1` messages, tied to durable progress and completed healthy
  worker cycles — no unconditional background heartbeat.
- `smartxflow-base-worker.service`: `Type=notify`,
  `NotifyAccess=main`, `WatchdogSec=420`; hang recovery uses existing
  `Restart=on-failure`. Operator gates and
  `RestartPreventExitStatus=3 4` remain unchanged.
- Expired, atomically reclaimable checkpoint/reconciliation leases remain a\n  `DEGRADED` recovery alert but do not force a healthy worker into endless\n  `exit 2`/systemd restart loops. Unknown *current* lease/commit ACKs still\n  stop with fenced exit 3.\n- No database schema migration is necessary for step 1.

## Evidence

GitHub Actions focused suite: **78 passed** (2026-10-21).
Includes real local UNIX datagram notification, read-budget exception,
unknown renewal-ack fencing, safe watchdog success path, unsafe exit3,
and existing checkpoint storage/reconciliation tests.

## Operational acceptance

After exact-SHA release, verify systemd `active` and `enabled`,
`Type=notify`, nonzero `WatchdogUSec`, multiple fresh cycles,
a progressing source checkpoint attempt/cursor high-water,
and no unexplained multiple producers.
An active systemd unit is not proof of complete signal coverage.
Stale ingestion and previously missing Early data remain separate tasks.
