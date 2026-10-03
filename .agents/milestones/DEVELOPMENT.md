# Development Current Milestone

MILESTONE_VERSION: 5
STATUS: ACTIVE

## Objective
Finish and verify the minimum reliable selected-match Learning Archive pipeline before model training.

## Implemented on `preview`

- Existing SXF stored-history reader; no second live collector.
- Learning Archive no longer needs direct Supabase credentials for SXF history. It reads selected-match history through a dedicated SmartXFlow server-to-server read-only API; SmartXFlow backend remains the only owner of the database connection.
- Internal API contract: `GET /api/internal/learning-archive/match/<match_id_hash>/history`, Bearer-authenticated by `LEARNING_ARCHIVE_ACCESS_SECRET`, with fail-closed `401/400/404/503` behavior and allow-listed response fields.
- Six existing prematch history tables are required; Moneyway Double Chance and Draw No Bet history are optional when present.
- Deterministic case packaging with `case.json`, `evidence.json`, `settlement.json`, `sxf_snapshots.json.gz`, SHA-256 checksums.
- PRE/POST evidence classification from immutable `observed_at <= prediction_at` cutoff.
- Validator with required metadata checks, secret rejection and Poly/Polymarket exclusion.
- Configurable dedicated private GitHub archive backend with append-only conflict handling, retry-safe partial writes, idempotent identical reruns, manifest and post-write verification.
- Bootstrap/finalize CLI interfaces.
- Retention-hold registry code and SQL migration.
- Web cleanup guard that blocks cleanup while any Learning Archive case is pending and fails closed if hold state cannot be verified.
- Finalizer does not return `DONE` while enabled hold release is unverified.
- Unit coverage for cutoff, secrets, Poly, deterministic checksums, empty history, API authentication/source behavior, idempotent finalization and optional market-history handling.

## Required now

1. Create/connect the actual private `smartxflow-learning-archive` GitHub repository and initialize it with `README.md`, `manifest.jsonl`, and `schema/match_case_v1.schema.json` using the bootstrap command.
2. Verify the new internal SmartXFlow history endpoint on the canonical GitHub `preview` SHA in Replit Preview using the configured `LEARNING_ARCHIVE_ACCESS_SECRET`: unauthorized request -> 401; authorized real match -> 200 with complete expected history payload.
3. Apply `migrations/2026_10_03_learning_archive_retention_holds.sql` to the **SmartXFlow** Supabase project through the authorized SmartXFlow runtime path, not any unrelated project.
4. Configure the runtime archive destination/token and enable retention holds.
5. Run one real selected `BET|WATCH|PASS` case through: immutable case -> hold -> SmartXFlow internal history API -> settlement/review -> validator -> archive write -> manifest/checksum verification -> hold release.
6. Re-run that same finalized case and verify deterministic idempotent behavior returns the existing archive identity without duplicate case/manifest rows.
7. Verify a materially changed rerun of the same `case_id` fails closed and requires explicit append-only correction/version handling.

## Acceptance

One real settled/reviewed selected `BET|WATCH|PASS` case is self-contained and reproducible in the dedicated private archive, and:
- Learning Archive itself never needs SmartXFlow Supabase credentials to fetch SXF history,
- retention protection preserves required source history until finalization,
- validator returns deterministic PASS/FAIL with reasons,
- duplicate/idempotent re-run behavior is deterministic,
- secret material is rejected before write,
- successful write is verified by manifest/checksums and returns a durable archive reference,
- failure never produces a false `DONE` state.

## Later, not now

PRE-only feature builder -> reproducible datasets -> baseline models -> walk-forward backtests -> candidate/shadow registry.
