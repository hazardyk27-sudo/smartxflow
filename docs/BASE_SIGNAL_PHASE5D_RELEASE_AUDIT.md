# SmartXFlow Base Signals — Phase 5D pre-release security & operations audit

**Canonical repo:** `hazardyk27-sudo/smartxflow` · **Branch:** `preview` only
**Audit disposition: NO-GO for production as of 2026-10-19.**

This is a source-only, evidence-based gate, not a release authorization.
No migration, live Supabase write, Replit sync, Hetzner deployment or
`main` promotion was carried out. Existing Base motor formula/thresholds,
market clocks, Predictor workflows and historical output are unchanged.

## Delivered (source changes only)

1. `base_signal_engine/release_gate.py` supplies an offline, fail-closed
   evidence review with an explicit dependency-ordered eleven-file SQL
   migration inventory. The composite snapshot index is **separately
   approval-gated** and must run outside a transaction via
   `CREATE INDEX CONCURRENTLY`; it is **not** part of the eleven SQL files.
2. `base_signal_engine/release_report.py` is an **offline/no-credential**
   local report: `python -m base_signal_engine.release_report
   --manifest /secure/operator-evidence.json
   --shadow /secure/shadow-observations.jsonl`.
   The CLI exits **nonzero**; it is not a migration executor, deployment
   program or remotely authenticated approval authority. It does not print
   raw evidence or credentials. A supplied true-valued approval checklist
   cannot create authentic user consent.
3. Disposable PostgreSQL CI verifies a restricted source writer can
   invoke proposed `SECURITY DEFINER` capture triggers while being unable
   to read or mutate source outbox tables, claim jobs or bypass RLS.
4. CI performs **transactionally rolled back trigger removal**, tests
   the capture-disabled gap, checks trigger restoration after ROLLBACK,
   and confirms the original ledger remained append-only.

## Blocking findings to clear before any production permission

- **LIVE_SCHEMA_UNVERIFIED:** Actual native `fixtures` /
  `moneyway_snapshots` columns, IDs, constraints, table owners, triggers,
  ingestion strategy, privileges and cancellation/remap semantics have
  not been read-verified against the target source service. The
  disposable PostgreSQL schema is a test fixture, not the live schema.
- **SOURCE_WRITE_AMPLIFICATION_UNBENCHMARKED:** Part 5A would add
  transactional trigger writes to source insert/update/delete.
  Writer failure, locks, WAL, disk, high-frequency snapshot throughput
  and P95/P99 latency require an authorized DBA load assessment.
- **NO_REAL_24H_SHADOW:** CI virtual clocks and SHA-256 evidence cannot
  substitute for 24h of actual read-only runtime observations and
  independent system-log validation. The report can only say its
  observations meet specified gates; it never authenticates their origin.
- **COMMIT_TIME_NOT_PROVEN:** `clock_timestamp()` in a trigger measures
  capture time, not commit visibility. Nonmonotonic commit order makes a
  high-water-by-change-ID unsafe; use the persistent delivery state.
- **SNAPSHOT_MUTATION_PENDING_POLICY:** Snapshot UPDATE/DELETE outbox
  events remain `SOURCE_MUTATION_REVIEW`; historical signals must not
  be silently considered valid or automatically erased.
- **HISTORICAL_BACKFILL_GAP:** Trigger installation cannot capture
  changes before activation. Backfill, reference kickoff and source
  retention must be audited before the first operational run.
- **SOURCE_INDEX_UNAPPROVED:** Real `EXPLAIN (FORMAT JSON)` evidence,
  size and writer overhead are outstanding for the separately
  proposed Moneyway composite index.
- **RELEASE_APPROVAL_ABSENT:** User has not authorized Preview
  synchronization, DB migration, live shadow, main promotion or
  production deployment. Do not infer authorization from "devam".

## Deployment order / guardrails (manual only)

The eleven Phase 4–5 SQL migration files must be reviewed for conflicts,
ownership, RLS and trigger load in a DBA-approved staging copy first.
Apply nothing to live until an exact 40-hex preview SHA and separate
signoff exist for each risky surface. The source capture trigger migration
is especially sensitive and must be an independent opt-in. Run
`CREATE INDEX CONCURRENTLY` only as a separately authorized
nontransactional operation; do not wrap it in the eleven-file transaction.

Release flow remains `preview` → **explicit Preview approval** →
approved exact SHA fast-forward to `main` → separate exact-`main` SHA
deployment. No reset, rebase, force push or cherry-pick, and stop on
branch divergence.

## Independent rollback drill (not run on production)

In disposable Postgres, remove only
`sxf_base_fixture_source_capture` from `public.fixtures` and
`sxf_base_snapshot_source_capture` from
`public.moneyway_snapshots` inside a transaction. Confirm source
inserts work without capture and the prior outbox ledger persists.
Rollback the transaction and verify both triggers restore and future
source writes again capture events. This exercise proves DDL
transaction semantics under the test fixture, **not** that live
production rollback will be risk-free. For a production emergency,
halt the new consumer, obtain DBA approval for scoped trigger
removal, retain append-only ledger and document the missing-capture
time range for explicit backfill.

## Acceptance evidence required

Provide schema owner/grants and source retention review, representative
read-only EXPLAIN plans, snapshot insert/update/delete peak write
benchmark, source trigger threat-model and trigger-owner audit,
historical backfill verification, 24h genuine read-only shadow
observations plus independent logs, reviewed historical-snapshot
mutation policy, tested rollback/alerts, Preview UI evidence and
separate explicit user approval for migration and production rollout.

**Current release state: NO-GO.** The development work can continue
on `preview` without exposing the production pipeline.
