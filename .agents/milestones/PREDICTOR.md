# Predictor Current Milestone

MILESTONE_VERSION: 5
STATUS: ACTIVE

## Objective
Run the first clean prediction -> automatic shared-folder archive -> settlement workflow on selected football matches.

## Required now

1. Research only selected matches; do not archive the whole slate.
2. Formal materially researched `BET`, `WATCH`, and `PASS` decisions are learning cases; never retroactively change the original decision after the result.
3. Preserve immutable `prediction_at`, entry odds/market/selection when applicable, confidence, rationale, counterargument and actually observed evidence.
4. Keep PRE/POST separated by `observed_at` vs `prediction_at`.
5. As part of completing a formal prediction, automatically create its case under `learning-archive:/learning_archive_data/cases/YYYY/MM/DD/<case_id>/` and preserve a current SmartXFlow stored-history capture. Do not require a separate user command.
6. When that selected case is materially revisited before kickoff, append a new timestamped stored-history capture; never rewrite an earlier capture.
7. At settlement/end-of-day, add result/postmortem plus the final full available SXF prematch timeline.
8. Existing SmartXFlow systems remain the collector. Never create a second market collector and never manually rewrite stored snapshot history.
9. Never include API keys, tokens, cookies, auth headers, passwords, `.env` values or other credentials in archive content.
10. Record lessons only as `OBSERVATION` or `RESEARCH_CANDIDATE`.
11. No Poly/Polymarket inputs.

## Archive destination

- Repository: existing `hazardyk27-sudo/smartxflow`
- Data branch: `learning-archive`
- Root folder: `/learning_archive_data/`
- No separate archive repository.
- No extra archive GitHub token.
- Archive writes never go to `main` or `preview`.

## Done per case

A case is `DONE` only when:
- the original decision/prediction is immutable,
- evidence timing exists,
- the case was written to the shared archive folder,
- required SmartXFlow history captures exist,
- result/decision outcome is settled/reviewed as applicable,
- final archive files/checksums are coherent,
- manifest entry exists,
- a durable `learning-archive` branch path is confirmed.

Anything less remains explicit pending/failed/retryable.
