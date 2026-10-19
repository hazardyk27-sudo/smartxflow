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

## Actual Hetzner isolated read-only smoke — 2026-10-19

**Verified host:** `smartxflow`, `91.99.6.245`, Linux; actual production root
`/opt/smartxflow`. Production remained on `main` SHA
`6f25b926ffc1b3507893cd7e3cb5c6d0911896f7` with a clean
tracked diff. The separate scraper tree `/root/smartxflow` had existing
uncommitted changes and was not touched.

**Read-only staging:** a sparse, depth-limited GitHub `preview` checkout
under `/var/tmp/smartxflow-base-probe-83413ac04f4d3470b5f8c14fed682c54cf694191`;
the code was fast-forwarded to exact SHA
`1974ff3584ab4fcaec0bf3d5e4bb17384c351ef6`. No tracked
production file was modified, no production service restarted, and no
new persistent service file installed.

**Initial safety discovery:** a too-tight, 2-page × 50-row cap safely
returned `SnapshotReadError` (pagination cap). The source-only CLI
was corrected to bound each merged window at 4 pages × 200 rows
and its GitHub CI passed. Nothing was committed to the source database.

**Executed one-shot checks:** temporary `systemd-run --wait --collect`
units used the existing server-side restricted `.env` without
logging its values and ran as the `smartxflow` service user.
The first transient attempt exited `200/CHDIR` because
`PrivateTmp=yes` hid the `/var/tmp` staging directory; a new transient
unit omitted that isolation solely for the staging-directory smoke.
The tracked production-target unit remains non-enabled.

For physical fixture `74acc8bd-665e-488c-b1e7-32f95674ccdd`
(Degerfors – Kalmar FF, kickoff 2026-10-19T17:00:00Z):

| Probe | Source rows | Market outcomes | Result | Time / memory |
|---|---:|---|---|---|
| T-6 | 413 | 1X2, OU25, BTTS each `AUTHORITATIVE_T6` | COMPLETE, 0 signals | 597 ms, 24.2 MB peak |
| T-8 | 273 | 1X2, OU25, BTTS each `PRELIMINARY_T8` | COMPLETE, 0 signals | 548 ms, 24.1 MB peak |

The CLI output explicitly reported `writes_performed=false`,
`production_approved=false` and `shadow_24h_verified=false`. Neither
sample proved a historical betting signal, and no live signal storage
was written. After both checks the temporary units were gone, seven
existing production services checked `active`, and the production
HEAD/tracked files were unchanged.

**Still blocked:** no Base durable queue/source outbox migration is
authorized or installed; composite source index is still absent, so
do not launch full-universe or 24-hour fan-out; exact SHA promotion
from `preview` to `main` and permanent Hetzner installation remain
a separate release approval. Replit was not used.

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
