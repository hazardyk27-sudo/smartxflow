# Predictor Playbook

REFERENCE_VERSION: 5

Open this file only for substantive match-analysis/prediction work.

## Core rule

The Predictor workflow has three separate user-controlled stages. Never collapse them into a single unsolicited analysis. Each stage has its own evidence boundary and stopping point.

The Predictor market scope is the set of real SmartXFlow-supported markets used by this workflow, currently 1X2, Over/Under 2.5 and BTTS. Draw No Bet (DNB) and Double Chance (DC) are outside scope. Do not search for them, derive them, synthesize odds for them, request them from external sources, rank them, recommend them or create new formal cases using them.

## Stage 1 — SmartXFlow-only candidate analysis

Goal: discover interesting matches from SmartXFlow itself and describe the market behavior without external-news contamination.

1. Start from SmartXFlow match data for the requested date/time window.
2. Read Stage 1 data directly from SmartXFlow's primary data source / production data path. Do not use Replit Agent as the data-reading layer for Predictor analysis.
3. Use real SmartXFlow match identity and stored market history.
4. Evaluate only supported SmartXFlow markets, including:
   - absolute money,
   - money share,
   - new-money delta/velocity when available,
   - odds opening/current/path,
   - whether price confirms or resists the money,
   - liquidity/volume quality,
   - timing of the move,
   - reversals/momentum,
   - cross-market relationships among supported 1X2, Over/Under 2.5 and BTTS data when available.
5. Do not search for or derive DNB or Double Chance as part of candidate discovery or cross-market analysis.
6. Rank only the matches whose SmartXFlow structure deserves further investigation.
7. For each candidate, state:
   - what SXF shows,
   - why the move is unusual/interesting,
   - what market behavior must be explained in Stage 2,
   - what would invalidate the SXF-only thesis from a market-data perspective.
8. Send the Stage 1 report to the user and STOP.

### Stage 1 prohibitions

- No Replit Agent as a SmartXFlow data source or proxy for the analysis.
- No web browsing.
- No team-news research.
- No injuries/suspensions/form/lineup/manager commentary from external sources.
- No public odds sites used to discover or justify candidates.
- No external football knowledge used as the cause of a move.
- No final `BET | WATCH` decision.
- No DNB or Double Chance search, collection, derivation, synthetic pricing, ranking or recommendation.

If SmartXFlow data cannot be read reliably from the direct/primary source, do not substitute Replit or external markets. Report the SXF data-access problem instead.

## Stage 2 — external cause research

Enter only after the user explicitly asks to investigate the Stage 1 candidates/moves.

Goal: determine whether real football information explains, supports, contradicts, or fails to explain what SmartXFlow showed.

For each selected Stage 1 match:

1. Research injuries and suspensions.
2. Research squad selection and expected/confirmed lineups where available.
3. Research recent form and performance context.
4. Research tactical/context factors, motivation, schedule/congestion, travel and weather when material.
5. Check official team/competition sources first, then reliable reporters/data sources.
6. Actively search for the opposite case, not only confirmation.
7. Keep the original Stage 1 market observation frozen.
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

1. Merge the frozen Stage 1 market evidence with the Stage 2 external research.
2. Evaluate the strongest supporting case and strongest counterargument.
3. Decide whether the market has already consumed the edge.
4. Compare only the actually available supported SmartXFlow structures analyzed in Stage 1, currently 1X2, Over/Under 2.5 and BTTS.
5. Never search for, derive, synthesize, compare, recommend or output DNB or Double Chance.
6. Prefer the supported structure with the best risk/value profile rather than blindly taking the highest odds.
7. Output `BET` or `WATCH` only when a concrete supported market and selection can be stated.
8. If there is no defensible concrete supported market/selection, omit that match from the final prediction diary and Learning Archive rather than emitting `PASS` or an empty pick.
9. Freeze:
   - `prediction_at`,
   - market,
   - selection,
   - entry odds when applicable,
   - confidence,
   - rationale,
   - counterargument/failure condition,
   - Stage 1 SXF evidence,
   - Stage 2 external evidence with `observed_at`.
10. Automatically archive every formal final case and confirm durable `RECORDED` receipts before claiming the Stage 3 report is complete.

## Market principles

- Money share alone is weak; price response to money is central.
- More money is not automatically stronger.
- A larger odds collapse is not automatically better value.
- Distinguish absolute money, money share, new-money delta, velocity, liquidity and timing.
- Use the full stored path where available: opening and successive time points, not only the latest snapshot.
- Look for price/money confirmation, divergence, reversal, momentum and cross-market relationships.
- Cross-market comparison is restricted to supported SXF markets; DNB and Double Chance are never part of the search or comparison set.
- Always state the failure condition/counterargument.

## External evidence rules

These rules apply only in Stage 2 and Stage 3.

Prefer official team/competition sources for lineups, injuries/suspensions and announcements; then reliable reporters/data sources. Record source identity/reference, `published_at` when known, mandatory `observed_at`, factual note, evidence category and whether it supports/contradicts/is neutral.

Never backfill Stage 1 with information learned later in Stage 2.

## Output minimum by stage

### Stage 1

For every candidate show:
- match + SmartXFlow match identity when available,
- key supported market(s),
- money/volume/liquidity facts available in SXF,
- odds path and timing,
- price-vs-money interpretation,
- supported cross-market confirmation/divergence,
- why the match deserves Stage 2 research,
- SXF-only failure condition.

### Stage 2

For every researched candidate show:
- frozen `SXF SAYS`,
- `RESEARCH SAYS`,
- strongest supporting evidence,
- strongest contradictory evidence,
- `CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | UNEXPLAINED`,
- source timing/observed timing.

### Stage 3

For every listed final view show:
- `SXF SAYS`,
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
