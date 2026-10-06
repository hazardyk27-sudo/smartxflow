# Predictor Current Milestone

MILESTONE_VERSION: 11
STATUS: ACTIVE

## Objective
Run the first clean three-stage Predictor workflow on selected football matches: Stage 1 SmartXFlow-only discovery/analysis -> Stage 2 user-triggered external cause research -> Stage 3 user-triggered final decision -> automatic in-repo archive -> revisit capture -> settlement.

## Mandatory stage order

1. **Stage 1 — SXF ONLY**
   - Start from SmartXFlow data, not from public fixtures/news/odds sites.
   - Find candidate matches using stored SmartXFlow money, odds, history, timing, liquidity/volume and cross-market behavior.
   - Explain only what the SmartXFlow data itself shows.
   - Send the SXF-only candidate report to the user and STOP.
   - No web research and no final `BET | WATCH` decision in this stage.

2. **Stage 2 — EXTERNAL CAUSE RESEARCH**
   - Start only after the user explicitly asks to research why the Stage 1 moves may be happening.
   - Research news, injuries, suspensions, squad/lineup information, form, tactics, motivation, schedule, weather when material and reliable statistics.
   - Test both the supporting and opposing explanations for each Stage 1 move.
   - Keep `SXF SAYS` and `RESEARCH SAYS` separate.
   - Report `CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | UNEXPLAINED` and STOP.
   - No final `BET | WATCH` decision unless the user explicitly asks for Stage 3.

3. **Stage 3 — FINAL MERGE/DECISION**
   - Start only after the user explicitly asks for the final decision.
   - Merge the frozen Stage 1 SXF view with Stage 2 external evidence.
   - Consider the opposite case/failure condition.
   - Choose the best actually available market.
   - Draw No Bet (DNB) is forbidden and must never be recommended, archived, collected, or introduced as an internal market.
   - Double Chance (DC) may be recommended only when a real externally available DC market and real odds are known for that exact match/selection. Do not invent/derive a synthetic DC price from 1X2, and do not create an internal DC collector/history table.
   - Produce final `BET | WATCH` with a concrete non-empty market and selection, entry odds when applicable, confidence, rationale and counterargument.
   - If no defensible concrete selection exists, omit that match from the final prediction diary/archive; do not create a `PASS` or empty-pick case.
   - Freeze `prediction_at` and archive every formal final case automatically.

Never skip a stage and never collapse Stages 1-3 into one unsolicited answer.

## Required now

1. Research only selected matches; do not archive the whole slate.
2. Stage 1 must use real SmartXFlow match identity/history. Do not discover candidates from external odds/news first and then retrofit them into SXF.
3. Stage 1 observations must remain frozen when Stage 2 research is performed; external research must not rewrite what SXF originally showed.
4. Stage 2 evidence must have real `observed_at` timing and remain separate from SmartXFlow evidence.
5. Only Stage 3 final `BET` and `WATCH` decisions with a concrete market/selection are formal learning cases. No-pick/PASS cases are excluded from the final diary and archive.
6. Preserve immutable `prediction_at`, confidence, rationale, counterargument, market and selection; preserve entry odds when applicable.
7. Keep PRE/POST separated by `observed_at` vs `prediction_at`.
8. As part of completing Stage 3, automatically create each formal case under `learning-archive:/learning_archive_data/cases/YYYY/MM/DD/<case_id>/` and preserve the SmartXFlow stored-history capture. Do not require a separate user command.
9. A Stage 3 report containing N formal cases must produce N durable `RECORDED` archive receipts before the final report is considered complete. Multi-case reports must use `scripts/record_learning_batch.py` or an equivalent same-turn durable batch operation.
10. The first durable write appends a `RECORDED` manifest event. An identical retry is idempotent. A materially conflicting historical rewrite fails closed.
11. When a final selected case is materially revisited before kickoff, append a new timestamped capture and `CAPTURED` manifest event; never rewrite an earlier capture.
12. At settlement/end-of-day, add result/postmortem plus final full available SXF prematch timeline, checksums and a `FINALIZED` manifest event.
13. If any archive write fails, identify that case as `ARCHIVE_PENDING`/retryable; never silently omit it, never claim the final report was fully archived, and never fabricate a missing match identity/history later.
14. Existing SmartXFlow systems remain the collector. Never create a second market collector and never manually rewrite stored snapshot history.
15. Never include API keys, tokens, cookies, auth headers, passwords, `.env` values or other credentials in archive content.
16. Record lessons only as `OBSERVATION` or `RESEARCH_CANDIDATE`.
17. No Poly/Polymarket inputs.
18. Every settled formal `BET`/`WATCH` case must also have a per-case append-only postmatch learning note. A bare `Final score ... WIN/LOSS` settlement sentence is not a sufficient postmortem.
19. No DNB collector/table/history is to be added. No internal DC collector/table/history is to be added. If a real DC selection is used, absence of native SXF DC history must be stated explicitly; underlying 1X2 evidence may be referenced only as underlying evidence, never mislabeled as DC history.

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
- the candidate list came from SmartXFlow data,
- real SmartXFlow identity/history was used,
- the market movement was described using SXF evidence only,
- no external research contaminated the analysis,
- no final `BET | WATCH` decision was issued,
- the user has received the SXF-only report and the Predictor has stopped for Stage 2 instruction.

## Done per Stage 2 report

A Stage 2 report is complete when:
- external causes were researched only for Stage 1-selected matches,
- supporting and contradicting evidence were checked,
- SXF and external evidence remain visibly separate,
- each move is classified as confirmed/partial/contradicted/unexplained,
- the Predictor stops for explicit Stage 3 instruction.

## Done per Stage 3 report

A Stage 3 report is complete only when every listed formal final case has a concrete market/selection and a durable `RECORDED` receipt. A match without a prediction is not listed as a formal final case.

## Done per case

A case is `DONE` only when:
- the Stage 1 SXF observation is preserved,
- Stage 2 external evidence is preserved with timing,
- the Stage 3 original decision/prediction is immutable,
- a concrete market and selection exist,
- required stored-history captures exist,
- result/decision outcome is settled/reviewed as applicable,
- the standardized per-case postmatch learning note exists for a settled formal case,
- final archive files/checksums are coherent,
- manifest contains the final event,
- a durable GitHub commit/reference under `learning-archive:/learning_archive_data/` is confirmed.

Anything less remains explicit pending/failed/retryable.
