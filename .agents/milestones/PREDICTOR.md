# Predictor Current Milestone

MILESTONE_VERSION: 1
STATUS: ACTIVE

## Current objective
Operate the first clean prediction-to-archive workflow without changing the production prediction engine.

## Required now
1. Analyze only selected football matches; do not archive the entire slate.
2. For every final prediction, preserve `prediction_at`, entry odds, market, selection, confidence, rationale and evidence observed by cutoff.
3. At settlement/end-of-day, review the result and create one final Learning Archive package containing the full SXF prematch history for that match plus the immutable prediction/evidence/result record.
4. Keep PRE and POST strictly separated by actual observation time.
5. Record research lessons only as `OBSERVATION` or `RESEARCH_CANDIDATE`.
6. Do not use Poly/Polymarket inputs.

## Definition of done for each match
- prediction record exists and is immutable,
- external evidence has source + `observed_at`,
- final result is settled,
- full SXF prematch timeline has been exported into the final archive package,
- archive package passes the Learning Archive contract,
- archive file is stored in the dedicated private Learning Archive repository,
- no post-result information has been backfilled into PRE rationale.

## Not in this milestone
- model training,
- production rule promotion,
- automatic betting,
- whole-market archival,
- a separate Collector Agent.
