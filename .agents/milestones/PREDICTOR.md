# Predictor Current Milestone

MILESTONE_VERSION: 13
STATUS: ACTIVE

## Objective
Run the clean three-stage Predictor workflow on selected football matches: Stage 1 independent SmartXFlow-only full-slate review with a concrete SXF preference -> Stage 2 user-triggered external cause research -> Stage 3 user-triggered final decision -> automatic in-repo archive -> revisit capture -> settlement.

## Mandatory stage order

1. **Stage 1 — SXF ONLY**
   - Start from SmartXFlow primary/production data, not from public fixtures/news/odds sites.
   - Do not use the SmartXFlow `Analizler` section, precomputed analysis outputs, signal-engine recommendations/rankings/labels, prior Predictor conclusions or other ready-made interpretations to choose or judge matches.
   - Enumerate the requested date/time slate and inspect **every match individually** from that match's own SXF data before filtering/ranking the report.
   - An aggregate inventory/query may enumerate the slate, but no aggregate score/ranking/composite may replace match-by-match review.
   - For every match, inspect all available supported-market prematch history from the earliest stored state/opening through successive snapshots, recent/late movement and the analysis cutoff. Latest-row-only analysis is not allowed when history exists.
   - The Predictor itself must interpret temporal significance: money amount/share, new-money delta/velocity, odds path, price response/resistance, liquidity change, reversals, momentum, late money and supported cross-market behavior.
   - Stored trend/signal labels are not conclusions; they may not substitute for the Predictor's own temporal analysis.
   - Search and compare only Predictor-supported SmartXFlow markets (currently 1X2, Over/Under 2.5 and BTTS).
   - Draw No Bet (DNB) and Double Chance (DC) are outside Predictor scope: do not search for them, derive them, synthesize prices for them, request their odds, rank them or use them to discover candidates.
   - After the full slate has been independently reviewed, rank/filter the matches whose SXF structure is materially useful to report unless the user explicitly asks for every match.
   - Every match shown in the Stage 1 report must contain a mandatory **`SXF PREFERENCE`**: one exact supported market + selection, analysis-cutoff price when available, SXF-only reason and strongest SXF-only counterargument/failure condition. A secondary supported-market preference is optional.
   - Stage 1 must decide from SXF alone **as if Stage 2 and Stage 3 do not exist**. Do not defer, weaken or withhold the SXF preference because external research may later be requested.
   - The Stage 1 `SXF PREFERENCE` is a real SXF-only conclusion but is **not** a final `BET | WATCH` decision and does not create a formal archive case.
   - Send the complete SXF-only report to the user and STOP.
   - No web research and no final `BET | WATCH` decision in this stage.

2. **Stage 2 — EXTERNAL CAUSE RESEARCH**
   - Start only after the user explicitly asks to research why the Stage 1 moves may be happening.
   - Research news, injuries, suspensions, squad/lineup information, form, tactics, motivation, schedule, weather when material and reliable statistics.
   - Test both the supporting and opposing explanations for each Stage 1 move.
   - Keep `SXF SAYS` and `RESEARCH SAYS` separate.
   - Preserve the frozen Stage 1 market observation and `SXF PREFERENCE`; external research must not rewrite them.
   - External research must not expand the market scope into DNB or Double Chance.
   - Report `CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | UNEXPLAINED` and STOP.
   - No final `BET | WATCH` decision unless the user explicitly asks for Stage 3.

3. **Stage 3 — FINAL MERGE/DECISION**
   - Start only after the user explicitly asks for the final decision.
   - Merge the frozen Stage 1 SXF evidence and `SXF PREFERENCE` with Stage 2 external evidence.
   - Consider the opposite case/failure condition.
   - Choose the best actually available Predictor-supported SmartXFlow market from the analyzed scope.
   - Draw No Bet (DNB) and Double Chance (DC) are forbidden and must never be searched, recommended, archived, collected, introduced as internal markets or synthesized from 1X2.
   - Produce final `BET | WATCH` with a concrete non-empty market and selection, entry odds when applicable, confidence, rationale and counterargument.
   - If no defensible concrete supported selection exists, omit that match from the final prediction diary/archive; do not create a `PASS` or empty-pick case.
   - Freeze `prediction_at` and archive every formal final case automatically.

Never skip a stage and never collapse Stages 1-3 into one unsolicited answer.

## Required now

1. Stage 1 must begin with the full requested SmartXFlow slate and individually review every match before candidate filtering/ranking.
2. Stage 1 must use real SmartXFlow match identity/history. Do not discover candidates from external odds/news first and then retrofit them into SXF.
3. Stage 1 must not use SmartXFlow `Analizler`, ready-made recommendation/signal outputs, precomputed rankings or prior Predictor conclusions as the basis of selection or interpretation.
4. For each match, Stage 1 must examine the full available prematch temporal path across supported markets and independently judge the importance/timing of changes. A current snapshot alone is insufficient when history exists.
5. Every match included in the Stage 1 report must have a concrete `SXF PREFERENCE` with supported market + selection + SXF-only rationale + failure condition. Do not postpone the preference pending Stage 2.
6. Stage 1 is self-contained: make the strongest SXF-only conclusion as if no later stages will happen. It still must not emit final `BET | WATCH`.
7. Stage 1 observations and the `SXF PREFERENCE` must remain frozen when Stage 2 research is performed; external research must not rewrite what SXF originally showed.
8. Stage 2 evidence must have real `observed_at` timing and remain separate from SmartXFlow evidence.
9. Only Stage 3 final `BET` and `WATCH` decisions with a concrete supported market/selection are formal learning cases. Stage 1 preferences are not archive cases. No-pick/PASS cases are excluded from the final diary and archive.
10. Preserve immutable `prediction_at`, confidence, rationale, counterargument, market and selection; preserve entry odds when applicable.
11. Keep PRE/POST separated by `observed_at` vs `prediction_at`.
12. As part of completing Stage 3, automatically create each formal case under `learning-archive:/learning_archive_data/cases/YYYY/MM/DD/<case_id>/` and preserve the SmartXFlow stored-history capture. Do not require a separate user command.
13. A Stage 3 report containing N formal cases must produce N durable `RECORDED` archive receipts before the final report is considered complete. Multi-case reports must use `scripts/record_learning_batch.py` or an equivalent same-turn durable batch operation.
14. The first durable write appends a `RECORDED` manifest event. An identical retry is idempotent. A materially conflicting historical rewrite fails closed.
15. When a final selected case is materially revisited before kickoff, append a new timestamped capture and `CAPTURED` manifest event; never rewrite an earlier capture.
16. At settlement/end-of-day, add result/postmortem plus final full available SXF prematch timeline, checksums and a `FINALIZED` manifest event.
17. If any archive write fails, identify that case as `ARCHIVE_PENDING`/retryable; never silently omit it, never claim the final report was fully archived, and never fabricate a missing match identity/history later.
18. Existing SmartXFlow systems remain the collector. Never create a second market collector and never manually rewrite stored snapshot history.
19. Never include API keys, tokens, cookies, auth headers, passwords, `.env` values or other credentials in archive content.
20. Record lessons only as `OBSERVATION` or `RESEARCH_CANDIDATE`.
21. No Poly/Polymarket inputs.
22. Every settled formal `BET`/`WATCH` case must also have a per-case append-only postmatch learning note. A bare `Final score ... WIN/LOSS` settlement sentence is not a sufficient postmortem.
23. No DNB or Double Chance collector/table/history is to be added. Predictor must not search, derive or output either market. Historical archived cases that already contain such a market remain immutable historical records; this rule governs new analysis and new formal cases.

## Mandatory postmatch learning-note standard

For every settled formal `BET` or `WATCH` case, append a timestamped `addenda/<observed_at>-postmatch-learning.json` without rewriting the frozen prediction, original evidence, captures or settlement.

The note must contain, at minimum:
- `observed_at`, `case_id`, and `type`, where `type` is only `OBSERVATION` or `RESEARCH_CANDIDATE`;
- actual result/final score; for `WATCH`, keep the decision as WATCH and label any selection result hypothetical;
- the selected market's final available prematch SXF state (price plus money/share when the source market provides them), or an explicit `unavailable_reason` when a native selected-market history does not exist;
- a concise prediction-time -> final-prematch comparison, including material late reversal/divergence rather than looking only at the closing price;
- whether the Stage 2 football context remained supportive, became contradictory, or simply failed to explain the result; do not rewrite PRE evidence after seeing the score;
- a concise explanation of what the case teaches about the original thesis and the strongest counterargument;
- any possible new rule only as `RESEARCH_CANDIDATE`; one match never promotes a production rule.

Postmatch notes must be useful for a future analyst but compact: normally one structured record and a few concise sentences, not a long match essay. Historical corrections/backfills must be clearly labeled as historical and must preserve original timestamps/identity rather than pretending the automation ran live.

A formal settled case is not considered fully reviewed for the daily Predictor diary until this postmatch learning note exists and is durably committed under `learning-archive`.

## Archive destination

- Repository: `hazardyk27-sudo/smartxflow`
- Data branch: `learning-archive`
- Root folder: `/learning_archive_data/`
- No separate archive repository.
- No archive-specific GitHub token. Reuse normal repository GitHub credentials/connector when a durable programmatic commit is needed.
- Archive data commits never go to `main` or `preview` and are never deployed.
- A runtime/worktree-only file write is not durable and is never `DONE`.

## Done per Stage 1 report

A Stage 1 report is complete when:
- the full requested slate was enumerated from SmartXFlow,
- every match in that slate was individually reviewed from its own raw/current/stored SXF data before filtering/ranking,
- SmartXFlow `Analizler` and other ready-made analysis/recommendation outputs were not used to choose or judge the matches,
- real SmartXFlow identity/history was used,
- the full available temporal market path was examined where history exists,
- the Predictor independently interpreted the timing and significance of money/price/liquidity/cross-market movement,
- every reported match has a concrete `SXF PREFERENCE` with supported market + selection + rationale + failure condition,
- the Stage 1 preference was made from SXF alone without deferring to later stages,
- only supported SXF markets were searched/analyzed; DNB and Double Chance were not searched or derived,
- no external research contaminated the analysis,
- no final `BET | WATCH` decision was issued,
- the user has received the self-contained SXF-only report and the Predictor has stopped for Stage 2 instruction.

## Done per Stage 2 report

A Stage 2 report is complete when:
- external causes were researched only for Stage 1-selected matches,
- supporting and contradicting evidence were checked,
- SXF and external evidence remain visibly separate,
- the frozen Stage 1 `SXF PREFERENCE` was preserved unchanged,
- each move is classified as confirmed/partial/contradicted/unexplained,
- no DNB or Double Chance market search was introduced,
- the Predictor stops for explicit Stage 3 instruction.

## Done per Stage 3 report

A Stage 3 report is complete only when every listed formal final case has a concrete supported market/selection, is neither DNB nor Double Chance, and has a durable `RECORDED` receipt. A match without a prediction is not listed as a formal final case.

## Done per case

A case is `DONE` only when:
- the Stage 1 SXF observation and frozen `SXF PREFERENCE` are preserved,
- Stage 2 external evidence is preserved with timing,
- the Stage 3 original decision/prediction is immutable,
- a concrete supported market and selection exist,
- required stored-history captures exist,
- result/decision outcome is settled/reviewed as applicable,
- the standardized per-case postmatch learning note exists for a settled formal case,
- final archive files/checksums are coherent,
- manifest contains the final event,
- a durable GitHub commit/reference under `learning-archive:/learning_archive_data/` is confirmed.

Anything less remains explicit pending/failed/retryable.
