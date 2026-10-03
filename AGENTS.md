# SmartXFlow Agent Rules

**Repository:** `hazardyk27-sudo/smartxflow`

This file is the short common bootstrap for the active specialized learning workflow. Keep it in session context after one read.

## Canonical instruction branch

- For `PREDICTOR` and `DEVELOPMENT` conversations, this `preview` branch is the canonical source of the active specialized role instructions and Current Milestones.
- The root `main:/AGENTS.md` remains the repository/release/safety rule supplement and must also be respected.
- A specialized session must not fall back to stale or missing role definitions on `main` when the active role files exist on `preview`.

## Session loading

There are exactly two conversational SmartXFlow roles for this learning workflow:

- `PREDICTOR` — researches selected matches, publishes predictions, settles them, and triggers final archive creation.
- `DEVELOPMENT` — builds/maintains the learning archive pipeline, validator, datasets, features, tests, models and controlled improvements.

There is **no separate Collector Agent** and **no separate Match Analyst Agent**.

At the start of a specialized session read once, in this order:

1. `main:/AGENTS.md` for repository/release/safety rules
2. `preview:/AGENTS.md`
3. only your own `preview:/.agents/roles/<ROLE>.md`
4. only your own `preview:/.agents/milestones/<ROLE>.md`

Do not routinely reread them during the same session. Reread only if the file/version changed, the user says rules changed, repository/branch context changed, or a real instruction conflict appears.

Do not preload the other role or long reference documents. Open a detailed reference only when the active task actually needs it.

## Shared learning rules

1. Existing SmartXFlow systems remain the source of live/stored SXF snapshots. Do not build a second scraper just for learning.
2. Only matches actually researched/predicted by Predictor are archived for learning; never archive the entire daily market by default. Formal `BET`, `WATCH`, and `PASS` cases may all be archived when Predictor materially researched the match, so Development can learn from both selected and rejected opportunities.
3. `prediction_at` is the immutable PRE/POST cutoff.
4. External evidence is PRE only when its actual `observed_at <= prediction_at`; publication time alone is not enough.
5. Historical prediction, rationale, result, raw snapshots and evidence timestamps are never silently rewritten. Corrections are append-only/versioned.
6. POST information may be used for settlement, diagnosis and labels, never as PRE training input for that prediction.
7. Poly/Polymarket trader intelligence is excluded from this Learning Engine and its training inputs.
8. A win/loss is evidence, not proof. New predictive rules require repeated evidence, time-ordered testing and controlled validation.
9. No model/method silently changes production. Candidate -> historical test -> shadow -> review -> controlled promotion/rejection.
10. Critical rules should be enforced in code/tests where practical instead of relying only on agent memory.

## Archive safety rules

1. **Instruction branch lock:** active specialized role instructions come from `preview`; `main` supplies the general repository/release/safety supplement.
2. **Retention protection:** once a case is selected for learning, the SXF history required to build that case must not be allowed to disappear through cleanup/retention before a valid final archive package has been created and verified. Development owns the technical protection; Predictor must surface a case that cannot be safely finalized.
3. **No false completion:** a case is not `DONE` merely because settlement was reviewed. Finalization requires deterministic validator `PASS`, successful write to the dedicated archive repository, manifest/checksum verification, and a durable archive path/reference. Failure must remain explicit and retryable; never silently mark success.
4. **Idempotency and duplicate safety:** the same `case_id` must not create duplicate finalized cases or overwrite an existing finalized payload. Re-running export for an already-finalized identical case must be safe/idempotent; materially different corrections require append-only addenda/versioned metadata.
5. **Secret exclusion:** archive payloads, evidence, notes, logs and manifests must never contain API keys, auth tokens, cookies, authorization headers, passwords, private credentials, `.env` values or equivalent secrets. Store only non-secret provenance needed for reproducibility.

## Learning Archive

Finalized selected-match cases belong in a dedicated private GitHub repository named `smartxflow-learning-archive`, not as bulk data in this application repository.

The source repository contains only the archive contract, schema, exporter/validator code and learning-engine implementation. See `/.agents/contracts/LEARNING_ARCHIVE.md` only when archive work requires it.

## Source and release essentials

- GitHub source/history is canonical.
- `main` = latest user-approved production SHA.
- `preview` = development/Preview branch and canonical active specialized-agent instruction branch.
- Replit Preview is only a runner for the exact GitHub `preview` SHA; never use Replit Agent to independently edit/sync source.
- Hetzner is production runtime; never edit production files in place.
- User approval is required before promoting `preview` to `main` or deploying production.
- Never force-push, rebase, reset, or improvise around divergence.
- The user's personal computer is never a work target. Remote tools may be used only as a bridge to authorized remote systems.

For an actual release/sync/deploy task, then and only then open `/.agents/contracts/RELEASE_FLOW.md` and follow it exactly.
