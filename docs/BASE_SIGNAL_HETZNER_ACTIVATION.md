# SmartXFlow Base — Hetzner activation and next real checkpoint

## 2026-10-19 — controlled durable Hetzner T-6 smoke PASSED

Executed from the **isolated preview checkout**, exact SHA
`a40e94b7768610de5146b03f8aa961bee48d9f17`, on the
verified `smartxflow` Hetzner host `91.99.6.245`. Production
`/opt/smartxflow` remained on clean `main` SHA
`6f25b926ffc1b3507893cd7e3cb5c6d0911896f7` throughout.
The seven existing scraper/signal/web/alarm/live/poly/predictor
services remained active and untouched.

- Exactly one queued `BASE T-6` item was present before execution:
  `74acc8bd-665e-488c-b1e7-32f95674ccdd`,
  kickoff `2026-10-19T17:00:00Z`, attempts `0`, state `PENDING`.
- A temporary `systemd-run --wait --pipe --collect` one-shot, using
  the `smartxflow` service account and server-only environment, invoked
  `base_signal_engine.hetzner_worker --once --no-discovery --max-jobs 1
  --max-reconcile 0`. Explicit runtime opt-in gates were set only
  for that transient unit. No permanent service installed/enabled.
- **First run:** `claimed=1`, `completed=1`, `waiting_data=0`,
  `lease_uncertain=0`, `commit_uncertain=0`,
  `healthy_cycle=true`; exit `0/SUCCESS`, **1.005 s**,
  **25.2 MB peak**.
- **Independent live SQL verification:** same job `COMPLETED`,
  `attempt_count=1`, `completed_at=2026-10-19T18:49:00Z`;
  one immutable checkpoint evaluation; `source_coverage.state=COMPLETE`;
  `fetched_rows=413`; exactly three `MARKET_DECISION`
  events for 1X2, OU25 and BTTS, all from checkpoint **6**;
  no qualifying betting signals, i.e. legitimate NO_HIT.
- **Second isolated one-shot:** `claimed=0`, `completed=0`,
  no retries/uncertainty, exit success (**436 ms**, **24.4 MB**).
  Subsequent live SQL totals remained **1 evaluation**,
  **3 market decisions**, **0 betting signals**, **1 completed job**.
  This confirms terminal-claim idempotency in the real Supabase RPC path.
- The temporary units were collected and disappeared. Production
  `main` tracked diff remained zero; seven existing services still active.
  Neither Replit nor legacy signal tables were modified.

**Shadow gate reality:** this does **not** constitute 24-hour shadow
coverage. On the live database the `sxf_base_source_health` RPC is
**absent**, since proposed per-row `source_capture` triggers and
source outbox were explicitly deferred. Existing
`base_signal_engine.shadow_observer.record_shadow_once` calls this
RPC, so without further instrumentation its evidence recording
**cannot pass the complete shadow release gate**. Do not fabricate
`source_pending_due=0` or claim an ingested source-change watermark
from a read-only snapshot test. Continue with a separately evaluated,
performance-safe source coverage strategy and exact-SHA release
approval; no 24/7 worker or full shadow has been activated.

---


**State as of 2026-10-19:** source and durable schema prepared; **worker NOT installed/enabled**, **real 24-hour shadow NOT done**, and **no change to production `main`**. GitHub `preview` owns current development. Replit will not run Base engines.

## What is physically verified

- Hetzner host `smartxflow`, `91.99.6.245`, Linux, production root `/opt/smartxflow`. On last successful remote inspection, `main` HEAD was `6f25b926ffc1b3507893cd7e3cb5c6d0911896f7`, tracked worktree clean, and web, scraper, alarm, signal, live, Poly and Predictor services active. `/root/smartxflow` is a **separate scraper checkout** containing pre-existing uncommitted changes; do not touch it.
- Isolated read-only Hetzner smoke against real Supabase for **Degerfors – Kalmar FF**, physical `fixture_uid=74acc8bd-665e-488c-b1e7-32f95674ccdd`, kickoff `2026-10-19T17:00:00Z`: T-8 fetched **273** rows, three markets `PRELIMINARY_T8`; T-6 fetched **413** rows, three markets `AUTHORITATIVE_T6`. Both complete, zero signals (valid NO_HIT), zero DB writes. Times **548 ms / 597 ms**; peak memory around **24 MB**. These prove only one-fixture source-read + kernel evaluation, not a permanent worker.
- A sparse, isolated `preview` checkout exists at `/var/tmp/smartxflow-base-probe-83413ac04f4d3470b5f8c14fed682c54cf694191`; last verified checkout HEAD `1974ff3584ab4fcaec0bf3d5e4bb17384c351ef6`. It is **older than current preview**, must be verified clean and fast-forwarded; don't assume new worker code is present.
- Live Supabase composite snapshot index `idx_sxf_base_mw_snapshot_uid_time` on `(fixture_uid,scraped_at_utc,id)` was built with `CREATE INDEX CONCURRENTLY`, validated with `indisvalid=true`, and used in physical-UID/time query EXPLAIN. Its reported size later reached ~281 MB.
- **Nine approved additive `sxf_base_*` migrations are live:** checkpoint queue, WAITING_DATA hardening, reconciliation RPC and queue, discovery cursor, fixture drift guard, discovery heartbeat, health snapshot and market projection. Seven isolated Base tables have RLS. `public.sxf_base_health_snapshot()` works.
- **Exactly one** real T-6 checkpoint for this fixture has been queued; `job_key=SXF_BASE_V1_2026_10_18:74acc8bd-665e-488c-b1e7-32f95674ccdd:2026-10-19T17:00:00+00:00:BASE:T-6`, `checkpoint_at=2026-10-19T11:00:00Z`, `run_after=2026-10-19T11:10:00Z`, **PENDING** at last verification. Repeated SQL enqueue returned `added_again=0`; idempotency holds. No evaluations or signals were written for it.

## What is NOT live

- The proposed Phase 5A **source-capture triggers**, source delivery/outbox tables, dependent source-health RPC, and source-change consumer are **not installed**. The Moneyway source permits NULL `fixture_uid`; code fixed that edge case in `preview`, but per-row trigger write overhead and retention-delete fanout have **not** been benchmarked. Do not enable them as part of an ordinary worker smoke.
- `deploy/systemd/smartxflow-base-worker.service` and `base_signal_engine/hetzner_worker.py` are `preview` files only. They are deliberately excluded from `deploy/sync_runtime_units.sh`; existing `smartxflow-sinyal.service` is not replaced.
- The Base discovery cursor remains uninitialized; rolling fixture discovery is only a **bounded rescan**, not proof of complete source change capture. Neither source ingestion watermark nor a continuous 24h observation has been verified.
- All running Base signal services/rollouts remain unchanged pending exact-SHA approval. Do not claim production-ready results from an empty queue or mocked test.

## Fail-closed worker guarantees prepared on preview

- `--once --no-discovery --max-jobs 1 --max-reconcile 0` processes at most one existing durable job and **cannot** mass-enqueue fixtures.
- A normal cycle uses bounded claims and reads only native SXF `fixtures`/`moneyway_snapshots`, writes only isolated `sxf_base_*` RPCs; no old signals, provider writes, wagers or notifications.
- If discovery fails, the worker may drain a previously queued item but exits **nonzero** instead of claiming the cycle healthy.
- If a lease, RPC claim, completion or reconciliation ACK becomes ambiguous, no further claims proceed. Exit **3** requires manual inspection; the proposed service explicitly sets `RestartPreventExitStatus=3` to prevent automated replay. Ordinary explicit errors exit **2**.
- `SXF_BASE_DURABLE_WORKER_APPROVED=yes` and `SXF_BASE_COMPOSITE_INDEX_VERIFIED=yes` are mandatory, server-only opt-ins; no secrets or approval flags belong in GitHub.
- Last completed historical Base suite had **162 Python + 31 PostgreSQL** tests passing. Subsequent hardening changed source/tests; **new GitHub Actions runs remain queued as last checked**, so the latest SHA is not yet certified green.

## Next allowed sequence when Hetzner access returns

1. **Read-only host validation:** verify host/IP, `/opt/smartxflow` clean tracked `main` tree and SHA, `/root/smartxflow` untouched, current worker/systemd state, free memory/disk, and connection to the approved Supabase project. Never print `.env`, tokens or source odds.
2. **Verify CI** for the exact new `preview` SHA; fix any failures. Confirm there is still **one** PENDING Base T-6 job for the expected UID/kickoff/ruleset, and no unrelated queue mutations.
3. After the appropriate exact-SHA release authorization and a clean isolated GitHub `preview` test checkout, run a **single supervised durable checkpoint smoke**. Use `--once --no-discovery --max-jobs 1 --max-reconcile 0`, bounded service account, existing server-only auth; do not install/enable continuous worker yet. Confirm SQL `PENDING → COMPLETED` **exactly once**, one immutable evaluation and expected three `MARKET_DECISION` events; **zero signals is valid**. If no source evidence, expect `WAITING_DATA`, not a false completion.
4. For any ambiguous lease/commit, stop; inspect durable SQL before retrying. Do not restart/claim automatically, backfill with guesswork or fabricate results.
5. After exact SHA approval/promotion to `main` per `.agents/contracts/RELEASE_FLOW.md`, prepare separate new unit. Verify it does not affect scraper, alarm, legacy signal or web units. Progress from constrained discovery to observed checkpoint throughput; measure source DB and memory load. **No implicit trigger migration.**
6. Run genuine **continuous 24h Hetzner shadow** with independently verified logs, backlog/lease/provenance review and ingestion limitations explicitly reported. Only after that can the permanent motor and user-facing signal activation be considered complete.

**Current operational blocker:** the authorized Desktop Commander `smartxflow` agent was last reported **Offline**. No remote commands can presently validate or activate the new durable worker.

See `docs/BASE_SIGNAL_LIVE_DB_PREP_2026_10_19.md` for the actual Supabase migration/index audit and single-job queue record.
