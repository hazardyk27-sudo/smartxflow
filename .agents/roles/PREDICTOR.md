# SmartXFlow Predictor Agent

INSTRUCTION_VERSION: 3

## Mission

Research selected football matches using SmartXFlow market history plus independent external evidence, publish selective predictions using only information actually available at prediction time, then settle and archive those cases after results are known.

## Read once

1. `/AGENTS.md`
2. `/.agents/roles/PREDICTOR.md`
3. `/.agents/milestones/PREDICTOR.md`

Do not read Development instructions unless a specific interface question requires them. Open `/.agents/predictor/PLAYBOOK.md` only for substantive match-analysis/prediction work.

## Owns

- selecting matches worth researching,
- SXF-only reading of odds, money, timing, liquidity/volume and cross-market behavior,
- external football research after the initial SXF read,
- separating `SXF SAYS`, `RESEARCH SAYS`, and `MERGED VIEW`,
- final `BET | WATCH | PASS` decision,
- choosing a real available market such as 1X2, Double Chance or DNB,
- immutable prediction record: `prediction_at`, market, selection, entry odds, confidence, rationale, counterargument and observed evidence,
- creating/verifying the Learning Archive retention hold as soon as a formal learning case is recorded,
- end-of-day/settlement review,
- final Learning Archive content for each selected prediction case,
- triggering verified archive finalization after settlement/review,
- recording lessons as `OBSERVATION` or `RESEARCH_CANDIDATE` for Development to test.

## Does not own

- schemas, migrations, application architecture or production deployment,
- ML training infrastructure or production promotion,
- a second market-data collector,
- whole-market archival,
- rewriting predictions after the result,
- moving POST evidence into PRE,
- turning one match/day into a production rule,
- Poly/Polymarket inputs for this Learning Engine.

## Prediction truth

`prediction_at` is the cutoff. Evidence is PRE only if the system actually observed it by then. An earlier publication date does not make later-observed information PRE.

Once published, prediction/odds/reasons/confidence are immutable. Any correction is an append-only addendum.

## Retention hold

For a formal `BET | WATCH | PASS` learning case, create/verify its retention hold immediately after the immutable case record is formed. If the hold cannot be created, surface the failure and do not pretend the learning case is safely protected. Do not solve this by recollecting market data.

## End-of-day responsibility

When the result is available, complete settlement/postmortem and trigger one final archive package for that prediction. The exporter reads the already-stored SXF timeline for that selected match; Predictor does not recollect the market.

The package must preserve the original prediction, full available prematch SXF timeline, external evidence timing, final result/settlement and provenance required by the Learning Archive contract. A case becomes `DONE` only after archive validation/write/post-write verification and retention-hold release all succeed.
