# Development Current Milestone

MILESTONE_VERSION: 7
STATUS: ACTIVE

## Objective
Finish and verify the minimum reliable selected-match Learning Archive workflow inside the existing SmartXFlow repository before model training.

## Implemented on `preview`

- Existing SXF stored-history reader; no second live collector.
- Internal history API remains `GET /api/internal/learning-archive/match/<match_id_hash>/history`, Bearer-authenticated by `LEARNING_ARCHIVE_ACCESS_SECRET`, with fail-closed behavior and allow-listed response fields.
- Moneyway Double Chance and Draw No Bet history remain optional until those history tables exist.
- Canonical archive repository is `hazardyk27-sudo/smartxflow`; archive data branch is `learning-archive`; archive root is `/learning_archive_data/`.
- No separate archive repository and no archive-specific GitHub token/configuration.
- Durable writer is locked to the SmartXFlow repository and prefixes all paths with `learning_archive_data/`.
- Predictor lifecycle supports first `RECORDED` write, append-only `CAPTURED` revisits and `FINALIZED` settlement package.
- Manifest is append-only event JSONL; identical reruns are idempotent and conflicting same-event rewrites fail closed.
- Deterministic package/checksum support remains in place.
- PRE/POST classification is derived from immutable `observed_at <= prediction_at` cutoff.
- Validator enforces formal decision metadata, required rationale/counterargument/confidence, secret rejection and Poly/Polymarket exclusion.
- `LearningArchiveReader` provides Development-side integrity reading with checksum verification and separate PRE/POST evidence views.
- Worktree-only writes are explicitly non-durable and cannot produce final `DONE` status.

## Required now

1. Run one real formal `BET|WATCH|PASS` case and verify Predictor automatically creates the case folder, first capture and `RECORDED` manifest event without a separate user command.
2. Re-run the exact same record operation and verify idempotent behavior.
3. Attempt a same-case historical rewrite and verify fail-closed conflict behavior.
4. Revisit the selected case before kickoff and verify a new `CAPTURED` event/file is appended rather than replacing the first.
5. Settle the case and verify result/postmortem, final full prematch history, checksums and `FINALIZED` manifest event.
6. Verify Development reads the same archive folder with `LearningArchiveReader` and derives PRE-only inputs without consuming POST evidence.
7. Keep production retention migration unapplied until explicit user permission is given.

## Acceptance

One real settled/reviewed selected case is self-contained and reproducible under `learning-archive:/learning_archive_data/`, and:
- no separate archive repo/token setup exists,
- original prediction and evidence timing remain immutable,
- selected-match SXF history is preserved in organized captures,
- Development can read the same files directly,
- duplicate/idempotent behavior is deterministic,
- conflicting historical reruns fail closed,
- secret material and Poly inputs are excluded,
- failures/worktree-only writes never produce false `DONE`.

## Later, not now

After the first real case lifecycle passes: PRE-only feature builder -> reproducible datasets -> baseline models -> walk-forward backtests -> candidate/shadow registry.
