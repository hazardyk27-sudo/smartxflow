# SmartXFlow Agent Rules

**Repository:** `hazardyk27-sudo/smartxflow`

This file is the short common bootstrap for the active specialized learning workflow. Keep it in session context after one read.

## Canonical instruction branch

- For `PREDICTOR` and `DEVELOPMENT` conversations, `preview` is the canonical source of active specialized role instructions and Current Milestones.
- `main:/AGENTS.md` remains the repository/release/safety supplement and must also be respected.
- Do not fall back to stale role definitions on `main` when the active files exist on `preview`.

## Session loading

There are exactly two conversational SmartXFlow roles for this workflow:

- `PREDICTOR` — researches selected matches, publishes formal decisions, settles them, and automatically preserves selected cases.
- `DEVELOPMENT` — builds/maintains archive integrity, datasets, features, tests, models and controlled improvements.

At the start of a specialized session read once, in this order:
1. `main:/AGENTS.md`
2. `preview:/AGENTS.md`
3. only your own `preview:/.agents/roles/<ROLE>.md`
4. only your own `preview:/.agents/milestones/<ROLE>.md`

Do not routinely reread them. Open detailed contracts only when the active task requires them.

## Shared learning rules

1. Existing SmartXFlow systems remain the source of live/stored SXF snapshots. Do not build a second scraper for learning.
2. Archive only matches materially researched by Predictor and formalized as `BET` or `WATCH` with a concrete non-empty market and selection. A match with no defensible prediction/selection is omitted from the final prediction diary and Learning Archive rather than stored as `PASS`.
3. **The final prediction diary and the Learning Archive case store are separate mandatory artifacts. Individual case folders, `manifest.jsonl` events, settlements, captures or postmatch addenda NEVER count as the daily diary and must never be described as if they do.**
4. `prediction_at` is the immutable PRE/POST cutoff.
5. External evidence is PRE only when actual `observed_at <= prediction_at`; publication time alone is insufficient.
6. Historical prediction, rationale, counterargument, confidence, result, raw snapshots and evidence timestamps are never silently rewritten. Corrections are append-only.
7. POST information may be used for settlement/diagnosis/labels, never as PRE training input for that prediction.
8. Poly/Polymarket intelligence is excluded from this Learning Engine.
9. A win/loss is evidence, not proof. New rules require repeated evidence and time-ordered validation.
10. No model/method silently changes production. Candidate -> historical test -> shadow -> review -> controlled promotion/rejection.
11. Enforce critical rules in code/tests where practical.

## Learning Archive

- No separate repository is used.
- Canonical repository: `hazardyk27-sudo/smartxflow`.
- Canonical data branch: `learning-archive`.
- Canonical data folder: `/learning_archive_data/`.
- Application/source development remains on `preview`; archive data commits remain isolated on `learning-archive` and are never deployed/promoted to production.
- Predictor automatically creates the immutable case plus first stored-history capture when a formal selected case is published; later prematch revisits append captures; settlement writes the final package.
- Development reads the same archive folder.
- No archive-specific GitHub repository or token may be required. Durable programmatic writes may reuse normal SmartXFlow repository GitHub credentials/connector.
- Writing files only into a runtime/worktree is not durable and must never be reported as `DONE`. `DONE` requires validator PASS, checksum/manifest verification and a confirmed GitHub commit/reference on the archive data branch.
- Re-running identical writes is idempotent. Same case/event with materially different historical payload fails closed; factual corrections use append-only addenda/versioned records.
- Never place secrets in archive payloads, manifests, captures, evidence, logs or addenda.

## Daily Prediction Diary — separate mandatory artifact

For every calendar day that contains at least one formal Stage 3 `BET` or `WATCH`, Predictor must create a separate durable daily diary under:

`learning_archive_data/diaries/YYYY/MM/DD/`

The diary is a human-readable day-level record and is **not** satisfied by case archiving.

Required daily diary phases:
- `predictions.md` — created after Stage 3. It summarizes the user scope and every carried/formal final view, including frozen Stage 1 preference, Stage 2 classification, Stage 3 decision, execution market, actual price or threshold, confidence, `prediction_at`, and linked case id/archive state.
- `postmatch.md` — created after settlement. It records final scores/outcomes, keeps BET vs conditional-BET vs WATCH performance separate, summarizes late SXF/postmatch learning, and links back to the immutable case records.

Hard rules:
- `cases/YYYY/MM/DD/<case_id>/` is **case evidence**, not the diary.
- `manifest.jsonl` is **an event index**, not the diary.
- `settlement.json`, `sxf_snapshots.json.gz`, checksums and per-case addenda are **case package artifacts**, not the diary.
- Never say or imply “the diary exists because the cases were archived.”
- A day is not end-of-day `DONE` until both the required case archive state and the separate daily diary state are durable on `learning-archive`.
- Diary summaries must reference immutable case truth rather than rewrite it. Corrections are append-only/versioned; never silently alter historical decisions.

See `/.agents/contracts/LEARNING_ARCHIVE.md` when archive/export/validation work requires it.

## Source and release essentials

- GitHub source/history is canonical.
- `main` = latest user-approved production SHA.
- `preview` = development/Preview branch and active specialized-agent instruction branch.
- `learning-archive` = selected-match data only; it is not deployed and does not participate in source promotion.
- Replit Preview is only a runner for the exact GitHub `preview` SHA; never use Replit Agent to edit/sync source.
- Hetzner is production runtime; never edit production files in place.
- User approval is required before promoting `preview` to `main` or deploying production.
- Never force-push, rebase, reset, cherry-pick, or improvise around divergence.
- The user's personal computer is never a work target.

For an actual release/sync/deploy task, open `/.agents/contracts/RELEASE_FLOW.md` and follow it exactly.
