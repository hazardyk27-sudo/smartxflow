# Predictor Playbook

REFERENCE_VERSION: 6

Open this file only for substantive match-analysis/prediction work.

## Core rule

The Predictor workflow has three separate user-controlled stages. Never collapse them into a single unsolicited analysis. Each stage has its own evidence boundary and stopping point.

The Predictor market scope is the set of real SmartXFlow-supported markets used by this workflow, currently 1X2, Over/Under 2.5 and BTTS. Draw No Bet (DNB) and Double Chance (DC) are outside scope. Do not search for them, derive them, synthesize odds for them, request them from external sources, rank them, recommend them or create new formal cases using them.

## Stage 1 — independent SmartXFlow-only match analysis

Goal: independently inspect every match in the requested SmartXFlow slate from its own raw/current/stored-history data, interpret the full prematch market path, and produce a self-contained SmartXFlow-only preference for every match that is reported. Stage 1 must stand on its own as if Stage 2 and Stage 3 do not exist.

1. Start from SmartXFlow match data for the requested date/time window.
2. Read Stage 1 data directly from SmartXFlow's primary data source / production data path. Do not use Replit Agent as the data-reading layer for Predictor analysis.
3. Do **not** use the SmartXFlow `Analizler` section, precomputed analysis outputs, signal-engine recommendations, rankings, labels, composite scores, prior Predictor conclusions or any other ready-made interpretation to choose or judge Stage 1 matches. The Predictor must perform the analysis itself from the underlying SXF match data.
4. Inspect **every match in the requested window individually** before filtering/ranking the slate. An aggregate inventory/query may be used to enumerate the slate, but an aggregate score, ranking or first-pass summary must never replace per-match review.
5. For each match, use its real SmartXFlow match identity and inspect all available supported-market data belonging to that physical match.
6. Inspect the **full available prematch time series**, not only the latest row. Read the earliest stored state/opening when available, successive snapshots, recent/late snapshots and the analysis-cutoff state. The Predictor itself must determine which timing changes are important.
7. Evaluate only supported SmartXFlow markets, including:
   - absolute money,
   - money share,
   - new-money delta and velocity when available,
   - odds opening/current/full path,
   - price response while money is arriving,
   - liquidity/volume quality and how it changes over time,
   - timing and acceleration/deceleration of the move,
   - reversals, resistance and momentum,
   - late-money behavior,
   - cross-market relationships among supported 1X2, Over/Under 2.5 and BTTS data when available.
8. Do not rely on a stored `trend`, signal label or other precomputed interpretation as the conclusion. Raw/stored SXF values may be read, but the Predictor must independently interpret the temporal path and its significance.
9. Do not search for or derive DNB or Double Chance as part of candidate discovery or cross-market analysis.
10. After every match has been individually reviewed, rank/filter the matches whose SXF structure is materially useful to report unless the user explicitly asks for the full slate.
11. For **every match shown in the Stage 1 report**, give a mandatory `SXF PREFERENCE`:
   - one primary supported market,
   - one exact selection in that market,
   - the current/analysis-cutoff price when available,
   - a concise reason based only on that match's SXF evidence,
   - the strongest SXF-only counterargument/failure condition.
   An optional secondary SXF preference may be shown when another supported market independently reinforces the primary view.
12. The `SXF PREFERENCE` is a real Stage 1 conclusion, not a placeholder for later research. Stage 1 must make the strongest decision that SXF alone supports **as if no later stage will ever happen**. Do not withhold, soften or defer the preference merely because Stage 2 may later research football causes.
13. `SXF PREFERENCE` is **not** a final `BET | WATCH` decision and does not create a formal Learning Archive prediction case. It is the frozen SXF-only view that later stages may test only if the user requests them.
14. Send the Stage 1 report to the user and STOP.

### Stage 1 prohibitions

- No Replit Agent as a SmartXFlow data source or proxy for the analysis.
- No SmartXFlow `Analizler` section or ready-made analysis/recommendation output as an input to Stage 1 judgment.
- No prefiltering the requested slate by a precomputed signal, score, ranking or recommendation instead of reviewing every match individually.
- No latest-snapshot-only analysis when stored temporal history is available.
- No web browsing.
- No team-news research.
- No injuries/suspensions/form/lineup/manager commentary from external sources.
- No public odds sites used to discover or justify candidates.
- No external football knowledge used as the cause of a move.
- No final `BET | WATCH` decision.
- No DNB or Double Chance search, collection, derivation, synthetic pricing, ranking or recommendation.
- Do not say a preference cannot be made merely because Stage 2 research has not happened. Stage 1 must conclude from SXF alone.

If SmartXFlow data cannot be read reliably from the direct/primary source, do not substitute Replit or external markets. Report the SXF data-access problem instead.

## Stage 2 — external cause research

Enter only after the user explicitly asks to investigate the Stage 1 matches/moves.

Goal: determine whether real football information explains, supports, contradicts, or fails to explain what SmartXFlow showed.

For each selected Stage 1 match:

1. Research injuries and suspensions.
2. Research squad selection and expected/confirmed lineups where available.
3. Research recent form and performance context.
4. Research tactical/context factors, motivation, schedule/congestion, travel and weather when material.
5. Check official team/competition sources first, then reliable reporters/data sources.
6. Actively search for the opposite case, not only confirmation.
7. Keep the original Stage 1 market observation and `SXF PREFERENCE` frozen.
8. Keep market scope frozen as well: Stage 2 research must not introduce DNB or Double Chance discovery.
9. Label the external finding:
   - `CONFIRMED`
   - `PARTIALLY_CONFIRMED`
   - `CONTRADICTED`
   - `UNEXPLAINED`
10. Send the Stage 2 report and STOP.

Stage 2 must show `SXF SAYS` and `RESEARCH SAYS` separately. Do not issue the final betting decision unless the user explicitly requests Stage 3.

## Stage 3 — final merge and decision

Enter only after the user explicitly asks for the final decision/merge.

1. Merge the frozen Stage 1 market evidence and `SXF PREFERENCE` with the Stage 2 external research.
2. Evaluate the strongest supporting case and strongest counterargument.
3. Decide whether the market has already consumed the edge.
4. Compare only the actually available supported SmartXFlow structures analyzed in Stage 1, currently 1X2, Over/Under 2.5 and BTTS.
5. Never search for, derive, synthesize, compare, recommend or output DNB or Double Chance.
6. Prefer the supported structure with the best risk/value profile rather than blindly taking the highest odds.
7. Output `BET` or `WATCH` only when a concrete supported market and selection can be stated.
8. If no defensible concrete supported market/selection can be produced, omit that match from the final prediction diary and Learning Archive rather than emitting `PASS` or an empty pick.
9. Freeze:
   - `prediction_at`,
   - market,
   - selection,
   - entry odds when applicable,
   - confidence,
   - rationale,
   - counterargument/failure condition,
   - Stage 1 SXF evidence and `SXF PREFERENCE`,
   - Stage 2 external evidence with `observed_at`.
10. Automatically archive every formal final case and confirm durable `RECORDED` receipts before claiming the Stage 3 report is complete.

## Market principles

- Money share alone is weak; price response to money is central.
- More money is not automatically stronger.
- A larger odds collapse is not automatically better value.
- Distinguish absolute money, money share, new-money delta, velocity, liquidity and timing.
- Use the full stored path where available: opening and successive time points, not only the latest snapshot.
- The Predictor must independently judge temporal significance; a precomputed trend/signal label is never a substitute for reading the path.
- Look for price/money confirmation, divergence, reversal, resistance, momentum, late acceleration and cross-market relationships.
- Cross-market comparison is restricted to supported SXF markets; DNB and Double Chance are never part of the search or comparison set.
- Always state the failure condition/counterargument.

## External evidence rules

These rules apply only in Stage 2 and Stage 3.

Prefer official team/competition sources for lineups, injuries/suspensions and announcements; then reliable reporters/data sources. Record source identity/reference, `published_at` when known, mandatory `observed_at`, factual note, evidence category and whether it supports/contradicts/is neutral.

Never backfill Stage 1 with information learned later in Stage 2.

## Output minimum by stage

### Stage 1

Before producing the report, every match in the requested window must have been individually reviewed from its own SXF data/history. The report may remain ranked/filtered to material matches unless the user asks for every match.

For every match shown, show:
- match + SmartXFlow match identity when available,
- key supported market(s),
- money/volume/liquidity facts available in SXF,
- full relevant odds/money path and timing, not only opening/current endpoints when intermediate movement is material,
- the Predictor's own interpretation of temporal significance,
- price-vs-money interpretation,
- supported cross-market confirmation/divergence,
- mandatory `SXF PREFERENCE` with exact supported market + selection + analysis-cutoff price when available,
- why that is the preferred SXF-only structure,
- strongest SXF-only counterargument/failure condition.

Do not frame Stage 1 as merely preparing questions for Stage 2. It must be a complete SXF-only analysis and preference in its own right.

### Stage 2

For every researched candidate show:
- frozen `SXF SAYS`, including the original `SXF PREFERENCE`,
- `RESEARCH SAYS`,
- strongest supporting evidence,
- strongest contradictory evidence,
- `CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | UNEXPLAINED`,
- source timing/observed timing.

### Stage 3

For every listed final view show:
- `SXF SAYS`, including the frozen Stage 1 preference,
- `RESEARCH SAYS`,
- `MERGED VIEW`,
- decision (`BET | WATCH`),
- mandatory supported market + selection,
- entry odds when applicable,
- confidence if used,
- strongest supporting evidence,
- strongest counterargument/failure condition,
- `prediction_at`,
- archive receipt state.

A match without a concrete supported prediction is not shown as a final diary entry. DNB and Double Chance are not valid new final markets.

## Postmortem

After settlement separate:

- process/model error,
- execution/price error,
- missing/stale data,
- normal football variance.

A win does not validate the method and a loss does not invalidate it. Predictive-method changes require repeated archived evidence and Development testing.
