# SmartXFlow Base — live Hetzner shadow start (19 October 2026)

## Actual state (not a production release)

A 24-hour **temporary, isolated** Base durable worker shadow was started
on Hetzner host `smartxflow` using the canonical repository's GitHub
Actions SSH link. Start: **2026-10-19 approx 20:01:32 UTC**.
The worker writes **only** new `public.sxf_base_*` checkpoint,
evaluation and event records in Supabase project
`pswdvnmqjjnjodwzkmkp`; it does **not** write legacy signals,
scraper data, alerts or live customer output.

- Transient `systemd` unit: `sxf-base-durable-shadow-20261019.service`
- Exact isolated preview source SHA:
  `4e4b1ef681e275c44f4c4d36b4fcaefaec8cb5f1`
- Working dir: `/var/tmp/smartxflow-base-probe-83413ac04f4d3470b5f8c14fed682c54cf694191`
- Production `/opt/smartxflow` remains `main` SHA:
  `6f25b926ffc1b3507893cd7e3cb5c6d0911896f7` (clean tracked tree)
- Service owner: `smartxflow`, existing protected server-side Supabase
  environment only; no secrets committed or emitted to logs
- `--max-jobs 8 --max-reconcile 1 --interval-seconds 60`
- `RuntimeMaxSec=86400`, `Restart=no`, `MemoryMax=256M`,
  `TasksMax=32`, `ProtectSystem=strict`, `ProtectHome=yes`,
  `NoNewPrivileges=yes`.
- **Not installed or enabled** as permanent production unit.
  Existing scraper, sinyal, web, alarm, live, Poly, Predictor services
  all checked active after shadow start.
- GitHub Actions launch evidence:
  `https://github.com/hazardyk27-sudo/smartxflow/actions/runs/39315775336`

## DB startup evidence

- Live production Base composite snapshot index existed and valid.
- Fixed `sxf_base_claim_due_jobs` to prioritize **recent due Base T-8/T-6**
  checkpoints over historic bootstrap debt while retaining
  `WAITING_DATA` reclaims and 300-second lease fencing.
  Applied migration
  `sxf_base_checkpoint_live_priority_20261019` after disposable
  PostgreSQL tests; independently verified both function clauses
  and zero expired leases. The initial migration attempt **was
  not applied** when tests revealed a WAITING_DATA regression;
  the corrected file subsequently passed and alone was applied.
- Immutable cursor initialized once, explicitly, at
  `2026-10-19T19:00:00Z` using
  `public.sxf_base_init_discovery`. No retroactive history before
  this bootstrap time is claimed.
- First supervised one-shot discovered 10 fixtures in a one-hour window
  and enqueued 110 new checkpoint rows. It claimed 2, completed 1,
  WAITING_DATA 1, with no lease/commit uncertainty.
  `https://github.com/hazardyk27-sudo/smartxflow/actions/runs/39314835914`
- Continuous shadow first observed cycle: discovered 2 more fixtures,
  enqueued 22 jobs, claimed 8, completed 6,
  WAITING_DATA 2, `healthy_cycle=true`,
  no lease/commit uncertainties. Unit active, approx 26 MB RAM.
- Independent DB health at 2026-10-19 20:03 UTC:
  total jobs **177**, completed **10**, pending due **159**,
  WAITING_DATA **9**, expired leases **0**, discovery
  `completed_through=2026-10-19T22:00:00Z`.
  Counts represent one live moment and should not be treated as the
  outcome of the full 24h window.

## Critical limitations (not solved by the shadow start)

1. The per-row Phase 5A source-capture triggers have intentionally
   **not** been installed: cumulative production DELETE count on
   `public.moneyway_snapshots` was ~83.5 million at audit time,
   and NULL `fixture_uid` occurs historically. Enabling the
   unbenchmarked per-row outbox could impair the current scraper.
2. No verified PostgreSQL **commit-time source mutation watermark**,
   complete insert/update/delete outbox or source-health RPC exists.
   A source-tail overlap sampler can notice some changes but
   **does not certify complete mutation capture**.
3. Cursor discovery scans 1-hour kickoff windows with 50-fixture max
   and pauses when >=250 jobs are due; it does not, by itself,
   detect fixtures inserted into already-scanned historical windows.
4. A continuous 24h observation requires **24 hours of real elapsed
   runtime** and independent review of health/logs/evidence. Current
   source-capture deficits remain an explicit blocker to claiming
   the strict Phase 5C release gate has passed.
5. No `main` promotion, Replit deployment, production Base service
   enablement or legacy signal publication has occurred.

## Checks / stop procedure

Read only:

```bash
systemctl is-active sxf-base-durable-shadow-20261019.service
systemctl show sxf-base-durable-shadow-20261019.service -p ActiveState -p SubState -p MemoryCurrent -p NRestarts -p RuntimeMaxUSec
journalctl -u sxf-base-durable-shadow-20261019.service --no-pager -n 40
```

Run `SELECT public.sxf_base_health_snapshot()` in Supabase and
inspect grouped job states and expired leases separately.

To stop the **temporary shadow only** if health degrades:

```bash
systemctl stop sxf-base-durable-shadow-20261019.service
```

Never restart a worker automatically after lease or commit uncertainty
(exit 3). Do not replay the bootstrap cursor or delete checkpoint history.
Keep the production `main` and all existing units unchanged until the
canonical `.agents/contracts/RELEASE_FLOW.md` exact-SHA
review/Preview approval flow is satisfied.

A one-time follow-up audit is scheduled after the 24h window; it must
not approve production on time elapsed alone.
