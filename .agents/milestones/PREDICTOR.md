# Predictor Current Milestone

MILESTONE_VERSION: 7
STATUS: ACTIVE

## Objective
Run the first clean prediction -> automatic in-repo archive -> revisit capture -> settlement workflow on selected football matches, with archive completion enforced before a prediction report is considered complete.

## Required now

1. Research only selected matches; do not archive the whole slate.
2. Formal materially researched `BET`, `WATCH`, and `PASS` decisions are learning cases; never retroactively change the original decision after the result.
3. Preserve immutable `prediction_at`, confidence, rationale, counterargument, and market/selection/entry odds when applicable.
4. Keep PRE/POST separated by `observed_at` vs `prediction_at`.
5. As part of completing a formal prediction, automatically create its case under `learning-archive:/learning_archive_data/cases/YYYY/MM/DD/<case_id>/` and preserve a current SmartXFlow stored-history capture. Do not require a separate user command.
6. A report containing N formal cases must produce N durable `RECORDED` archive receipts before the report is considered complete. Multi-case reports must use `scripts/record_learning_batch.py` (or an equivalent same-turn durable batch operation) rather than relying on N manually remembered per-case commands.
7. The first durable write appends a `RECORDED` manifest event. An identical retry is idempotent. A materially conflicting historical rewrite fails closed.
8. When that selected case is materially revisited before kickoff, append a new timestamped capture and `CAPTURED` manifest event; never rewrite an earlier capture.
9. At settlement/end-of-day, add result/postmortem plus final full available SXF prematch timeline, checksums and a `FINALIZED` manifest event.
10. If any archive write fails, identify that case as `ARCHIVE_PENDING`/retryable; never silently omit it, never claim the report was fully archived, and never fabricate a missing match identity/history later.
11. Existing SmartXFlow systems remain the collector. Never create a second market collector and never manually rewrite stored snapshot history.
12. Never include API keys, tokens, cookies, auth headers, passwords, `.env` values or other credentials in archive content.
13. Record lessons only as `OBSERVATION` or `RESEARCH_CANDIDATE`.
14. No Poly/Polymarket inputs.

## Archive destination

- Repository: `hazardyk27-sudo/smartxflow`
- Data branch: `learning-archive`
- Root folder: `/learning_archive_data/`
- No separate archive repository.
- No archive-specific GitHub token. Reuse normal repository GitHub credentials/connector when a durable programmatic commit is needed.
- Archive data commits never go to `main` or `preview` and are never deployed.
- A runtime/worktree-only file write is not durable and is never `DONE`.

## Done per report

A report is complete only when every formal case has a durable `RECORDED` receipt. If even one formal case lacks a receipt, the report's archive state is incomplete and must be explicit.

## Done per case

A case is `DONE` only when:
- the original decision/prediction is immutable,
- evidence timing exists,
- required stored-history captures exist,
- result/decision outcome is settled/reviewed as applicable,
- final archive files/checksums are coherent,
- manifest contains the final event,
- a durable GitHub commit/reference under `learning-archive:/learning_archive_data/` is confirmed.

Anything less remains explicit pending/failed/retryable.
