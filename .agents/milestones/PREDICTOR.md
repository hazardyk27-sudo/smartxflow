# Predictor Current Milestone

MILESTONE_VERSION: 2
STATUS: ACTIVE

## Objective
Run the first clean prediction -> settlement -> archive workflow on selected football matches.

## Required now

1. Research only selected matches; do not archive the whole slate.
2. Preserve immutable `prediction_at`, entry odds, market, selection, confidence, rationale, counterargument and actually observed evidence.
3. Keep PRE/POST separated by `observed_at` vs `prediction_at`.
4. At settlement/end-of-day, complete result/postmortem and trigger one final archive package containing the full available SXF prematch timeline plus prediction/evidence/settlement.
5. Record lessons only as `OBSERVATION` or `RESEARCH_CANDIDATE`.
6. No Poly/Polymarket inputs.

## Done per case

Prediction is immutable; evidence timing exists; result is settled; final archive package passes the Learning Archive contract and is written to the dedicated archive repository.
