# SXF Base Signal Scheduler — Phase 3 (GitHub `preview` / shadow only)

## Scope and safety

This phase adds *non-deployed* scheduling and read-only motor evaluation with a local append-only JSONL checkpoint journal. The existing scraper, Sinyal Engine, Supabase schema, `main`, Hetzner and Replit are untouched. No production bets, DB updates, posts, schema migrations, index changes, or service units are performed.

Phase 3 is **not a 24/7 live service** yet. A deliberately gated, executable shadow runner is supplied to exercise the scheduler only after manual index/load verification and operator approval. Its local JSONL journal is preview telemetry **not** the production persistent signal store. Real 24/7 completeness cannot be claimed until Phase 4's DB-backed queue, Phase 7 deployment/health monitoring and live long-run validation.

## Scheduling and precedence

- Early Core: T-72, T-60, T-40, T-24; first eligible signal per fixture only. T-24 is a Core cohort, *not a new standalone motor*.
- Early retention: T-6/T-5/T-4/T-3, tracked separately; a <55% reading breaks validity irreversibly under existing rules.
- Other Base motors: T-8 preliminary; T-6 authoritative when a complete relevant market exists. T-8 becomes `FALLBACK_T8` only if the **market** has no valid T-6 snapshot. If T-6 exists but a rule fails, do not use T-8 to revive it.
- Market-level decisions are independent: 1X2 could use T-6 and BTTS T-8 for the same fixture.
- Each checkpoint is evaluated using a frozen cutoff `checkpoint_at + 10 minute ingestion grace`, and all source snapshots lie before the underlying checkpoint (no lookahead). Grace is a **provisional operational default** and needs production timing review.
- No T-5/T-4/T-3 Base scans are scheduled; these hours belong exclusively to Early retention.
- All snapshots come from `public.moneyway_snapshots`, identity verified against `public.fixtures.fixture_uid` via the Phase 2 reader, and evaluated by the frozen Phase 1 rules.

## Execution

Modules:
- `base_signal_engine.scheduler`: `due_jobs`, `evaluate_job`, `process_due_jobs`, immutable checkpoint jobs and deterministic keys. Failed reads do not mark work done. Job batches are capped, backlog is replayed gradually.
- `base_signal_engine.journal`: optional local shadow append-only JSONL with `flock`, `fsync`, read-back on restart and strict corruption handling. This is **not** the official event table.
- `base_signal_engine.runtime`: read-only paginated fixture catalog; `--once` or 30-second loop, capped work/batch, redacted error types, explicit safety flags. Do not enable until query plans are approved.

Example after explicit approval/index validation, **preview only**:

```bash
SXF_BASE_SHADOW_SCAN_APPROVED=yes SXF_BASE_COMPOSITE_INDEX_VERIFIED=yes \
  python -m base_signal_engine.runtime --once --journal /var/tmp/sxf-base-shadow.jsonl --max-jobs 25
```

The Supabase server credential is read via `SUPABASE_URL` / `SUPABASE_SERVICE_ROLE_KEY`; never expose the key to the frontend. The code never performs `POST`, `PATCH`, `DELETE` or DDL.

## Known production blockers

1. `public.moneyway_snapshots` currently lacks the combined `(fixture_uid, scraped_at_utc)` index. It contains hundreds of thousands of recent rows; do **not** launch high-fanout scanner polling before a measured index migration separately approved by the user.
2. Phase 4 must supply a DB-backed durable checkpoint queue and signal/event ledger with **atomic** idempotency, lease/lock ownership, missed-ingest retry and watermarks; a local JSONL journal is insufficient on more than one host and for permanently retained statistics.
3. Current shadow runner's finite backfill (`--backfill-days`, default 3) is **not** a guarantee for longer outages; DB queue/reconciliation is required before production.
4. T-6 ingestion later than the 10-minute grace can cause a provisional T-8 fallback. Phase 4/5 must reconcile late checkpoint data by append-only correction events rather than rewriting previous signals. A failed check at the grace boundary must not be misrepresented as a final unchangeable truth.
5. Live performance must be measured with bounded endpoint rates, pagination, scrape latency, gap metrics, restart/replay tests and 24h+ shadow coverage.
6. New motor variants remain research and shadow until time-ordered validation and explicit user approval for promotion.

## Test coverage

`tests/test_base_signal_scheduler.py` contains synthetic deterministic test cases for due scheduling, delayed checkpoints, T-6 vs T-8 market precedence, no future lookahead, Early cohort/retention, journal restart/dedup/corruption, error retries and bounded fixture discovery.

Local synthetic scheduler smoke suite: 14/14 passed with a temporary compatibility shim for Phase 1 rules, while the actual Phase 1/2 code is already in GitHub. An end-to-end run of these new tests against the canonical checked-out `preview` source is still needed before declaring integrated validation complete.