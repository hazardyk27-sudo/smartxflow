# Development Current Milestone

MILESTONE_VERSION: 8
STATUS: ACTIVE

## Objective
Finish and verify the minimum reliable selected-match Learning Archive workflow inside the existing SmartXFlow repository before model training, while preserving a matched Stage 1 baseline vs Stage 3 final-preference comparison so Development can measure whether later research/execution changes add value.

## Implemented on `preview`

- Existing SXF stored-history reader; no second live collector.
- Internal history API remains `GET /api/internal/learning-archive/match/<match_id_hash>/history`, Bearer-authenticated by `LEARNING_ARCHIVE_ACCESS_SECRET`, with fail-closed behavior and allow-listed response fields.
- Double Chance/handicap/alternative execution markets may be used as execution expressions when real price provenance is preserved; they are not relabeled as native SXF history.
- Draw No Bet is prohibited for new Predictor cases; no DNB collector/history table is to be introduced for this Learning Engine.
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
- Predictor executable workflow policy now lives under `predictor_policy/`; its hard rules must be validated rather than left as prose-only instructions.
- `predictor_policy/stage_comparison.py` provides matched Stage 1 baseline vs Stage 3 final-preference outcome and aggregate hit-rate/ROI comparison.

## Required now

1. Run one real formal `BET|WATCH` case and verify Predictor automatically creates the case folder, first capture and `RECORDED` manifest event without a separate user command.
2. Re-run the exact same record operation and verify idempotent behavior.
3. Attempt a same-case historical rewrite and verify fail-closed conflict behavior.
4. Revisit the selected case before kickoff and verify a new `CAPTURED` event/file is appended rather than replacing the first.
5. Settle the case and verify result/postmortem, final full prematch history, checksums and `FINALIZED` manifest event.
6. Verify Development reads the same archive folder with `LearningArchiveReader` and derives PRE-only inputs without consuming POST evidence.
7. For every settled Stage 1 candidate, preserve/grade the frozen Stage 1 preference and separately grade the final Stage 3 best-current preference on the same matched case set, including Stage 3 PASS rows hypothetically when a final preference exists.
8. Produce Stage 1 vs Stage 3 matched metrics: hit rate, hit-rate delta, changed/unchanged preference counts, `IMPROVED|WORSENED|SAME|UNRESOLVED` transitions and one-unit hypothetical ROI only where real observed prices exist.
9. Treat the matched delta as evidence about Stage 2/Stage 3 added value; do not claim Stage 2 helps from isolated examples or unmatched samples.
10. Keep production retention migration unapplied until explicit user permission is given.

## Acceptance

One real settled/reviewed selected case is self-contained and reproducible under `learning-archive:/learning_archive_data/`, and:
- no separate archive repo/token setup exists,
- original prediction and evidence timing remain immutable,
- selected-match SXF history is preserved in organized captures,
- Development can read the same files directly,
- duplicate/idempotent behavior is deterministic,
- conflicting historical reruns fail closed,
- secret material and Poly inputs are excluded,
- failures/worktree-only writes never produce false `DONE`,
- Stage 1 baseline and Stage 3 final-preference outcomes can be compared on the same settled candidate set without hindsight rewriting.

## Later, not now

After the first real case lifecycle and matched stage-comparison path pass: PRE-only feature builder -> reproducible datasets -> baseline models -> walk-forward backtests -> candidate/shadow registry.
