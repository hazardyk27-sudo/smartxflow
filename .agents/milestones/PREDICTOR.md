# Predictor Current Milestone

MILESTONE_VERSION: 4
STATUS: ACTIVE

## Objective
Run the first clean prediction -> retention hold -> settlement -> verified archive workflow on selected football matches.

## Required now

1. Research only selected matches; do not archive the whole slate.
2. Formal materially researched `BET`, `WATCH`, and `PASS` decisions may be retained as learning cases; never retroactively change the original decision after the result.
3. Preserve immutable `prediction_at`, entry odds/market/selection when applicable, confidence, rationale, counterargument and actually observed evidence.
4. Keep PRE/POST separated by `observed_at` vs `prediction_at`.
5. When a formal learning case is recorded, create/verify its retention hold immediately so D-8 cleanup cannot remove required SXF history before archive finalization.
6. At settlement/end-of-day, complete result/postmortem where applicable and trigger one final archive package containing the full available SXF prematch timeline plus prediction/evidence/settlement or decision outcome.
7. If source SXF history is incomplete, the retention hold is missing/unverifiable, archive validation fails, write fails, manifest/checksum verification fails, hold release fails, or no durable archive reference is returned, do **not** treat the case as complete. Surface the failure explicitly for retry/Development action.
8. Never create a second market collector or manually rewrite stored snapshot history.
9. Never include API keys, tokens, cookies, auth headers, passwords, `.env` values or other credentials in evidence/notes/archive content.
10. Record lessons only as `OBSERVATION` or `RESEARCH_CANDIDATE`.
11. No Poly/Polymarket inputs.

## Operational interface now available

- Create/refresh case protection: `python scripts/hold_learning_case.py <case.json>`
- Finalize after settlement/review: `python scripts/finalize_learning_case.py <case.json>`
- Finalizer reads existing SXF history; it does not recollect the market.

## Done per case

A case is `DONE` only when:
- the original decision/prediction is immutable,
- evidence timing exists,
- a retention hold protected the source history,
- result/decision outcome is settled/reviewed as applicable,
- final archive package passes the Learning Archive contract,
- the package is successfully written to the dedicated archive repository,
- manifest/checksums are verified after write,
- the retention hold is verified/released,
- a durable archive path/reference is confirmed.

Anything less remains explicit pending/failed/retryable.
