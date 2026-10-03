# Match Analyst Postmortem Standard

## Purpose

Postmortems exist to improve the process without rewriting history or overreacting to variance. Review every settled FIRSAT using the original immutable prediction record.

## Required review sequence

### 1. Reconstruct the original thesis
Restate exactly what was known at publication:
- SXF market evidence
- external research evidence
- selected market and entry odds
- confidence
- counterargument
- invalidation condition

Do not inject information that became available only after publication.

### 2. Record the outcome
Where available record:
- final score/result
- bet outcome: WIN / LOSS / PUSH / VOID
- closing odds
- CLV
- flat-stake profit/loss
- major match events that materially changed the state (red card, early injury, penalty, etc.)
- post-match underlying performance such as xG, big chances, shots, territory when useful

### 3. Test the causal thesis
Ask:
- Did the expected market signal persist or reverse before kickoff?
- Did the researched cause actually materialize in lineup/team behavior?
- Was the team performance broadly consistent with the thesis even if the result lost?
- Was the chosen market the correct expression of the thesis?
- Was the entry price still good relative to close?
- Was important information missed or stale?

### 4. Error taxonomy
Choose the primary diagnosis from:

`NO_ERROR_VARIANCE`
`BAD_MARKET_SELECTION`
`BAD_PRICE`
`DATA_STALE`
`DATA_MISSING`
`FALSE_MONEY_SIGNAL`
`PRICE_MONEY_MISREAD`
`LINEUP_MISS`
`INJURY_MISS`
`NEWS_MISS`
`MOTIVATION_MISREAD`
`TACTICAL_MISREAD`
`FORM_OVERWEIGHT`
`H2H_OVERWEIGHT`
`LIQUIDITY_DISTORTION`
`LATE_MARKET_REVERSAL`
`OVERCONFIDENCE`
`EXECUTION_ERROR`
`UNKNOWN`

Optionally add secondary diagnoses.

### 5. Was this a model/process error?
Return exactly one:
- `YES`
- `NO`
- `UNCERTAIN`

A loss with strong underlying performance and good closing-line value can be `NO_ERROR_VARIANCE`. A win can still be `YES` if the process was clearly poor and the result was fortunate.

## Root-cause statement

Write one concise cause chain:

`Observed failure -> missed/misread evidence -> decision impact -> corrective hypothesis`

Example:
`Late lineup rotation -> official lineup was not rechecked after predicted XI -> favorite strength was overstated -> require final lineup recheck for lineup-sensitive FIRSAT before kickoff.`

Do not use vague explanations such as "football is unpredictable" when a specific process failure can be identified.

## Corrective action levels

### OBSERVATION
Use for a single event or weak pattern. Record it but do not change methodology.

### PROCESS_FIX
Use when the failure is operational and logically clear, such as stale data, missed official lineup, wrong timestamp, or using an unavailable/synthetic market. A process safeguard can be proposed immediately.

### RESEARCH_CANDIDATE
Use when a repeated predictive pattern appears to deserve formal testing, for example a specific money/price/liquidity/timing combination.

A RESEARCH_CANDIDATE is not a new production rule. It must later be tested by the System Development Agent with adequate historical sample, validation/holdout, and forward evidence.

## Daily postmortem summary

At the end of the settled slate, summarize:
- total FIRSAT count
- W/L/P/V
- average odds
- daily flat-stake ROI
- CLV coverage and average CLV when available
- errors by category
- losses classified as variance vs process error
- strongest correct thesis
- most important failure
- observations
- research candidates
- one or more explicit focus points for the next day's analysis

## Next-day focus

The next day's Match Analyst should read the latest daily lessons and deliberately test the identified weak point, without allowing one bad day to override the base methodology.

Example:
- If `LINEUP_MISS` repeated, increase lineup verification discipline.
- If `LATE_MARKET_REVERSAL` repeated, add a pre-kickoff recheck checkpoint.
- If a market segment appears weak, label it a research candidate rather than silently banning it.

## Anti-hindsight rules

- Never edit the original prediction to make it look closer to the result.
- Never remove a losing prediction from performance records because it later looks "invalid".
- Never count only winners that fit a narrative.
- Never infer a new rule from results without preserving all qualifying losses and wins.
- Always distinguish what was knowable before kickoff from what became known afterward.
