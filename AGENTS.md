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
3. `prediction_at` is the immutable PRE/POST cutoff.
4. External evidence is PRE only when actual `observed_at <= prediction_at`; publication time alone is insufficient.
5. Historical prediction, rationale, counterargument, confidence, result, raw snapshots and evidence timestamps are never silently rewritten. Corrections are append-only.
6. POST information may be used for settlement/diagnosis/labels, never as PRE training input for that prediction.
7. Poly/Polymarket intelligence is excluded from this Learning Engine.
8. A win/loss is evidence, not proof. New rules require repeated evidence and time-ordered validation.
9. No model/method silently changes production. Candidate -> historical test -> shadow -> review -> controlled promotion/rejection.
10. Enforce critical rules in code/tests where practical.

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
