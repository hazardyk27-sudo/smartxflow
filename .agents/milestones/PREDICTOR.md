# Predictor Current Milestone

MILESTONE_VERSION: 16
STATUS: ACTIVE

## Objective

Run the three-stage Predictor workflow on the user's explicitly defined match universe:
Stage 1 = native SXF evidence/thesis -> Stage 2 = external cause research -> Stage 3 = best risk/value execution market -> automatic archive for formal cases -> separate daily prediction diary -> settlement/postmatch learning.

## Scope authority

The user's requested date/time window or named match set is authoritative and persists across stages until the user changes it.

- Never invent extra scope filters.
- Kickoff passing, current clock, low/high odds, obscure league, volatility or weak liquidity do not remove a match from scope.
- Those factors may change confidence, `BET | WATCH` or execution-market choice.
- If the user says "continue with these matches", evaluate the same set.
- Archive eligibility and analytical scope are separate. Never backdate `prediction_at`; archive problems become `ARCHIVE_PENDING`, not hidden matches.

## Native evidence vs execution market

### Native SXF evidence markets

Stage 1 reads and interprets only SmartXFlow native stored markets:
- 1X2
- Over/Under 2.5
- BTTS

These markets establish the frozen `SXF PREFERENCE` and thesis.

### Allowed Stage 3 execution markets

Stage 3 may implement the frozen thesis through a better real-world risk/value market even if SmartXFlow does not natively store it:
- native 1X2 / O-U 2.5 / BTTS;
- Double Chance (`1X`, `X2`, `12`);
- logical handicaps such as `+1.5`, `-1`, `-1.5`;
- nearby alternative totals such as O/U `1.5`, `3.5` when the expected scoring distribution justifies the line.

Draw No Bet (DNB) remains forbidden.

Alternative execution markets are implementations, not new SXF evidence. Never fabricate an exact price.

- verified real price -> may be used and archived with source/observed time;
- exact price unavailable -> state a minimum acceptable price threshold and mark it conditional;
- threshold is not actual odds;
- a formal priced `BET` requires a real available price when the execution market itself is not natively priced in SXF.

## Risk/value translation heuristics

Heuristics, not hard formulas:

- Strong underdog, 1X2 roughly `4.00+`: inspect `+1.5 handicap` because it may retain meaningful price while protecting a narrow loss.
- Medium underdog, roughly `2.70–3.80`: `+1.5` can become too short; inspect Double Chance if its real price still compensates for risk.
- Around `2.20` or shorter: Double Chance is often over-protected/too short. Prefer straight result if thesis is strong, otherwise do not force a protected bet.
- Very short O2.5 (around `1.30–1.35`) plus a genuine 4+ goal thesis: inspect O3.5.
- O2.5 around `1.40–1.60` with a simple 3+ goal thesis: usually retain O2.5 rather than adding unnecessary variance.
- Apply the same principle symmetrically to unders and favorite handicaps: protection/aggression must match the thesis, not merely chase a nicer number.

## Mandatory stage order

### 1. Stage 1 — SXF ONLY

- Enumerate the full user-defined slate from SmartXFlow production data.
- Inspect every match individually from its own raw/current/stored history before ranking/report filtering.
- Do not use `Analizler`, precomputed signals/rankings/labels or prior Predictor conclusions.
- Read the full available temporal path, not only the latest row.
- Independently interpret money amount/share, new-money velocity, odds path, price response/resistance, liquidity, reversals, momentum, late moves and native cross-market behavior.
- Native Stage 1 evidence/search is only 1X2, O/U2.5 and BTTS.
- Every reported match gets a frozen `SXF PREFERENCE`: native market + exact selection + cutoff price when available + SXF-only rationale + strongest SXF-only failure condition.
- Decide from SXF alone as if later stages do not exist.
- No web research, no final `BET | WATCH`, no fabricated DC/handicap/alternative-line prices, no DNB.
- Send Stage 1 and STOP.

### 2. Stage 2 — EXTERNAL CAUSE RESEARCH

- Start only after explicit user request.
- Carry forward the exact selected match set.
- Research injuries, suspensions, squad/lineups, form, tactics, motivation, schedule/travel, weather when material and reliable statistics/news.
- Search support and contradiction equally.
- Keep `SXF SAYS` and `RESEARCH SAYS` separate; preserve frozen Stage 1.
- Classify `CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | UNEXPLAINED`.
- Stage 2 may note whether a protected/aggressive execution line would logically fit, but may not pretend it exists in SXF.
- No final decision. STOP.

### 3. Stage 3 — FINAL MERGE / EXECUTION MARKET

- Evaluate every user-carried match; kickoff/current time is not an exclusion rule.
- Merge frozen Stage 1 + Stage 2 and strongest countercase.
- Determine the underlying thesis first, execution market second.
- Compare the native selection with logical DC/handicap/alternative-total implementations.
- Use the market with the best risk/value relationship, not automatically the safest or highest-odds option.
- Never use DNB.
- Never invent an exact alternative price. Use a verified real price or a clearly labeled minimum acceptable threshold.
- A high-odds underdog may become `+1.5`; a mid-priced underdog may become DC; a short favorite/DC may stay straight; an overly short O2.5 may become O3.5 only if 4+ goals are genuinely expected.
- Produce `BET | WATCH` with market, selection, price/threshold, confidence, rationale and strongest counterargument.
- If no formal selection is defensible, keep the match visible and explain why.
- Freeze real `prediction_at`; never backdate.
- Archive every formal case automatically when possible; failures remain `ARCHIVE_PENDING`.
- Create the separate daily diary; case archive receipts do not satisfy diary completion.

## Mandatory daily diary separation

For every day with at least one formal Stage 3 case, Predictor must create a separate durable diary under:

`learning_archive_data/diaries/YYYY/MM/DD/`

Required:
- `predictions.md` after Stage 3;
- `postmatch.md` after settlement/end-of-day review.

The diary must summarize the day across cases. It is not a substitute for case evidence, and case evidence is not a substitute for the diary.

**Never treat any of the following as a daily diary:**
- `cases/YYYY/MM/DD/<case_id>/`;
- `manifest.jsonl` `RECORDED`/`FINALIZED` events;
- `settlement.json`;
- captures or final SXF snapshots;
- checksums;
- per-case postmatch addenda.

If those exist but the daily diary does not, report `DIARY_PENDING`; do not report end-of-day `DONE`.

`postmatch.md` must report BET, conditional-BET and WATCH performance separately. WATCH outcomes remain hypothetical and conditional-BET performance must not pretend an unverified threshold price was actually available.

## Required now

1. Preserve user scope across all stages.
2. Stage 1 must be raw/native SXF-only and match-by-match.
3. Stage 1 `SXF PREFERENCE` stays native and frozen.
4. Stage 3 may transform the native thesis into DC/handicap/alternative totals for better risk/value.
5. Protection must not destroy price: safer is not automatically better.
6. Aggression must be justified by expected distribution: do not raise lines merely to chase odds.
7. Never synthesize exact execution odds. A threshold must be labeled as a threshold.
8. DNB remains prohibited.
9. Native SXF history must never be relabeled as history for an alternative execution market.
10. External execution-market prices, when actually used, require source and `observed_at`.
11. Formal cases preserve immutable prediction timing, market, selection, actual entry odds when available, confidence, rationale and counterargument.
12. Formal cases must be durably archived on `learning-archive`; failures are explicit/retryable.
13. Settled formal cases require append-only postmatch learning notes.
14. Every active prediction day requires a separate durable daily diary.
15. Case archive completion and diary completion are independent checks; neither implies the other.
16. End-of-day `DONE` requires both archive and diary completion.

## Archive behavior for alternative execution markets

If Stage 3 selects DC/handicap/alternative total:
- archive the execution market/selection as the final prediction;
- preserve the underlying native SXF market(s) as evidence/provenance;
- record actual execution price only if genuinely observed;
- otherwise preserve a conditional minimum price separately, never as fake entry odds;
- explicitly mark native history for that execution line unavailable;
- keep the original 1X2/O-U2.5/BTTS timeline unchanged.

No second collector is required. No DC/handicap/alternative-line SXF history should be fabricated.

## Done per Stage 1

Complete when the full user slate was enumerated, every match was independently reviewed from native SXF temporal data, every reported match has a frozen native `SXF PREFERENCE`, no external evidence contaminated the stage and no final decision was issued.

## Done per Stage 2

Complete when every carried match was researched with support and contradiction, Stage 1 remained frozen, and every move was classified without final `BET | WATCH`.

## Done per Stage 3

Complete analytically when every carried match is visible with either a final view or explicit no-formal-case reason. Formal case archive completion additionally requires durable `RECORDED` receipts for formal cases. **Daily workflow completion additionally requires the separate `predictions.md`; case receipts alone do not satisfy this.**

## Done per end-of-day

End-of-day is `DONE` only when:
1. all settleable formal cases have the required archive/settlement/postmatch state (or explicit unresolved/pending state);
2. `learning_archive_data/diaries/YYYY/MM/DD/predictions.md` exists durably;
3. `learning_archive_data/diaries/YYYY/MM/DD/postmatch.md` exists durably and summarizes results/performance/learning.

If the cases are complete but the diary is missing, the correct status is `DIARY_PENDING`, never `DONE`.
