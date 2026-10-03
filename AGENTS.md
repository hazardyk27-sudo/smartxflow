# SmartXFlow Agent Rules

**Repository:** `hazardyk27-sudo/smartxflow`

This file is the short common bootstrap. Keep it in session context after one read.

## Session loading

There are exactly two conversational SmartXFlow roles for this learning workflow:

- `PREDICTOR` — researches selected matches, publishes predictions, settles them, and triggers final archive creation.
- `DEVELOPMENT` — builds/maintains the learning archive pipeline, validator, datasets, features, tests, models and controlled improvements.

There is **no separate Collector Agent** and **no separate Match Analyst Agent**.

At the start of a specialized session read once, in this order:

1. `/AGENTS.md`
2. only your own `/.agents/roles/<ROLE>.md`
3. only your own `/.agents/milestones/<ROLE>.md`

Do not routinely reread them during the same session. Reread only if the file/version changed, the user says rules changed, repository/branch context changed, or a real instruction conflict appears.

Do not preload the other role or long reference documents. Open a detailed reference only when the active task actually needs it.

## Shared learning rules

1. Existing SmartXFlow systems remain the source of live/stored SXF snapshots. Do not build a second scraper just for learning.
2. Only matches actually researched/predicted by Predictor are archived for learning; never archive the entire daily market by default.
3. `prediction_at` is the immutable PRE/POST cutoff.
4. External evidence is PRE only when its actual `observed_at <= prediction_at`; publication time alone is not enough.
5. Historical prediction, rationale, result, raw snapshots and evidence timestamps are never silently rewritten. Corrections are append-only/versioned.
6. POST information may be used for settlement, diagnosis and labels, never as PRE training input for that prediction.
7. Poly/Polymarket trader intelligence is excluded from this Learning Engine and its training inputs.
8. A win/loss is evidence, not proof. New predictive rules require repeated evidence, time-ordered testing and controlled validation.
9. No model/method silently changes production. Candidate -> historical test -> shadow -> review -> controlled promotion/rejection.
10. Critical rules should be enforced in code/tests where practical instead of relying only on agent memory.

## Learning Archive

Finalized selected-match cases belong in a dedicated private GitHub repository named `smartxflow-learning-archive`, not as bulk data in this application repository.

The source repository contains only the archive contract, schema, exporter/validator code and learning-engine implementation. See `/.agents/contracts/LEARNING_ARCHIVE.md` only when archive work requires it.

## Source and release essentials

- GitHub source/history is canonical.
- `main` = latest user-approved production SHA.
- `preview` = development/Preview branch.
- Replit Preview is only a runner for the exact GitHub `preview` SHA; never use Replit Agent to independently edit/sync source.
- Hetzner is production runtime; never edit production files in place.
- User approval is required before promoting `preview` to `main` or deploying production.
- Never force-push, rebase, reset, or improvise around divergence.
- The user's personal computer is never a work target. Remote tools may be used only as a bridge to authorized remote systems.

For an actual release/sync/deploy task, then and only then open `/.agents/contracts/RELEASE_FLOW.md` and follow it exactly.
