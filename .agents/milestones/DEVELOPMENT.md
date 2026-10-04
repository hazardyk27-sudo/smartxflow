# Development Current Milestone

MILESTONE_VERSION: 6
STATUS: ACTIVE

## Objective
Finish and verify the minimum reliable selected-match Learning Archive workflow using the shared archive folder before model training.

## Implemented on `preview`

- Existing SXF stored-history reader; no second live collector.
- Learning Archive history access through the SmartXFlow backend remains available for selected-match stored history.
- Internal API contract: `GET /api/internal/learning-archive/match/<match_id_hash>/history`, Bearer-authenticated by `LEARNING_ARCHIVE_ACCESS_SECRET`, with fail-closed `401/400/404/503` behavior and allow-listed response fields.
- Six existing prematch history tables are required by the current reader; Moneyway Double Chance and Draw No Bet history are optional when present.
- Deterministic case packaging support with prediction/evidence/settlement/history/checksum validation.
- PRE/POST evidence classification from immutable `observed_at <= prediction_at` cutoff.
- Validator with required metadata checks, secret rejection and Poly/Polymarket exclusion.
- Unit coverage for cutoff, secrets, Poly, deterministic checksums, empty history, API authentication/source behavior, idempotency and optional market-history handling.
- A dedicated `learning-archive` branch now exists inside the existing `hazardyk27-sudo/smartxflow` repository.
- Canonical archive root is `learning-archive:/learning_archive_data/` with a manifest and per-case folders.

## Simplified archive architecture

There is no separate archive repository and no extra archive GitHub token requirement for the conversational Predictor/Development workflow.

Predictor writes selected-match cases directly to `learning-archive:/learning_archive_data/` as part of the prediction workflow. Development reads the same branch/folder. Archive writes are isolated from `main` and `preview` and are never deployed.

Existing SmartXFlow systems continue collecting market history. The archive does not run a second scraper. A first stored-history capture is preserved when a formal case is recorded; later substantive revisits append captures; settlement adds the final full available prematch timeline.

## Required now

1. Run one real formal `BET|WATCH|PASS` case and verify Predictor automatically creates the case folder and manifest entry without a separate user command.
2. Verify the first archive write preserves immutable prediction/evidence plus a SmartXFlow history capture.
3. Revisit that case once before kickoff and verify a new capture is appended rather than replacing the first.
4. Settle the case and verify final result/postmortem plus the final full prematch history are present.
5. Verify Development can read the case directly from the `learning-archive` branch and derive PRE-only features without touching POST evidence.
6. Re-run an identical archive action and verify idempotent behavior; conflicting historical rewrites must fail/require an append-only addendum.

## Acceptance

One real settled/reviewed selected `BET|WATCH|PASS` case is self-contained and reproducible under `learning-archive:/learning_archive_data/`, and:
- no separate archive repo/token setup is required,
- the original prediction and evidence timing remain immutable,
- selected-match SmartXFlow history is preserved in organized captures,
- Development can read the same files directly,
- duplicate/idempotent behavior is deterministic,
- secret material is excluded,
- failures never produce a false `DONE` state.

## Later, not now

PRE-only feature builder -> reproducible datasets -> baseline models -> walk-forward backtests -> candidate/shadow registry.
