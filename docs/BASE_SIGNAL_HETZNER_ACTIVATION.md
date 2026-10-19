# SmartXFlow Base signal motor — Hetzner-only activation checklist

**State:** GitHub preview source prepared and tested. **Not installed or running on Hetzner.**
Replit is not a Base signal worker. Existing Hetzner scraper, alarm, web, sinyal and
Poly services MUST be preserved.

## Preflight evidence (2026-10-19)

- Preview source includes `base_signal_engine/hetzner_probe.py`, a bounded
  read-only **single-fixture** Base T-6/T-8 smoke. It reads only two source
  resources via `SupabaseMoneywayReader` and does not write snapshots,
  Supabase event tables, local checkpoint journals, alerts or bets.
- `deploy/systemd/smartxflow-base-probe@.service` is a hardened,
  non-enabled one-shot template. It is deliberately **absent** from
  `deploy/sync_runtime_units.sh`; normal production deployment cannot
  activate it.
- A command requires an explicit `SXF_BASE_SINGLE_PROBE_APPROVED=yes`
  server-only environment setting. The approval flag is NOT committed.
- GitHub Actions passed **156 Python + 29 disposable PostgreSQL tests**,
  with the new probe contract and genuine source sample regression.
- A Remote Desktop Commander connector called `smartxflow` was discovered
  but failed command/ping and later appeared **offline**. Its endpoint
  hostname/OS/service inventory was not verified. **No remote changes
  were performed.**
- Production Supabase `moneyway_snapshots` still lacks an approved
  `(fixture_uid,scraped_at_utc,id)` composite index and the new Base
  outbox/queue tables have not been verified as live. Do not enable
  mass read polling, trigger hooks, or the durable worker.

## Safe sequence after remote access returns

1. Confirm the agent's host is really the explicitly authorized Hetzner
   server, NOT a personal workstation. Read-only: `hostname`,
   `systemctl list-units 'smartxflow*' --no-pager`, `git -C
   /opt/smartxflow status --porcelain=v1`, `git -C /opt/smartxflow
   rev-parse HEAD`, `df -h`, `free -h`. Never reveal environment
   variable values. Stop on dirty tree, wrong branch or divergence.
2. Apply the canonical `.agents/contracts/RELEASE_FLOW.md` exact-SHA
   approval and promotion rules before editing production. The existing
   `deploy/hetzner_preflight.sh` remains required for production changes.
   Never copy preview directly into production, modify `main` without
   authorization, or reset/rebase/force-push any branch.
3. After an approved exact-`main` release reaches Hetzner and source
   prerequisites are reviewed, install the tracked probe template into
   `/etc/systemd/system/smartxflow-base-probe@.service`, run
   `systemctl daemon-reload`. Do **not** enable at boot. Operator must
   explicitly set `SXF_BASE_SINGLE_PROBE_APPROVED=yes` inside restricted
   `/etc/smartxflow/base-probe.env`, with no secrets added to GitHub.
4. Run exactly one controlled instance against a known physical fixture:
   `systemctl start smartxflow-base-probe@74acc8bd-665e-488c-b1e7-32f95674ccdd.service`
   followed by `journalctl -u
   smartxflow-base-probe@74acc8bd-665e-488c-b1e7-32f95674ccdd.service
   --no-pager -n 30`. A nonzero one-shot exit may mean missing
   checkpoint evidence; do not treat it as a signal.
5. Approve/performance-test the separately gated composite source
   index before any broad 24-hour polling. Keep the new Base
   source-capture trigger proposal *deferred* until DBA transaction
   overhead and source mutation review policy are explicitly approved.
6. Do a genuine time-continuous Hetzner shadow with remote logging and
   independent 24-hour attestation; only then review safe durable
   persistence migration and user-facing signal activation.

## What is still not delivered

This probe is not the automatic 24/7 checkpoint, retry, reconciliation and
alerts service. It validates only the read-only, single-UID data-to-motor
path, which is the smallest safe milestone with the database as currently
indexed. Existing `smartxflow-sinyal.service` is not replaced.
No successful Hetzner execution can be claimed until the actual unit
and logs are independently observed on the authorized server.
