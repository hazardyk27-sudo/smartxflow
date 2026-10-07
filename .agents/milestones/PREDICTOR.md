# Predictor Current Milestone

MILESTONE_VERSION: 21
STATUS: ACTIVE

## Objective

Run the three-stage Predictor workflow with deterministic executable guardrails:
Stage 1 = scan the full user-defined fixture universe from native SXF data and surface only attention-worthy candidates -> Stage 2 = focused external cause research on that candidate set -> Stage 3 = graded best risk/value execution decision -> automatic archive for formal BET/WATCH cases -> Diary 1 at prediction time -> settlement/postmatch learning -> Diary 2 after results -> matched Stage 1 baseline vs Stage 3 final-preference performance comparison.

## Executable policy precedence

The canonical machine-readable Predictor policy is:

`predictor_policy/policy.json`

Validation implementation:

`predictor_policy/validator.py`

Matched Stage 1 vs Stage 3 evaluation:

`predictor_policy/stage_comparison.py`

If lower-level markdown wording conflicts with the executable policy, the executable policy controls. Do not relax a failing rule to finish faster; surface the violated rule ID and fix the payload/workflow.

## Scope authority — source universe first, candidate set second

The user's requested date/time window or named match criteria define the **Stage 1 source universe**.

- Stage 1 must internally screen every valid fixture satisfying that explicit scope.
- Stage 1 is not required to dump every screened fixture into the user-facing report.
- By default, Stage 1 surfaces only matches with analytically useful/attention-worthy SXF behavior, such as meaningful money/price interaction, divergence, persistence, acceleration, reversal, liquidity-adjusted movement or native cross-market confirmation.
- Every surfaced Stage 1 match must state at least one concrete attention reason and one frozen native `SXF PREFERENCE`.
- The exact surfaced Stage 1 candidate set becomes the default Stage 2/Stage 3 carry-forward set unless the user changes it.
- A screened-out fixture is not a prediction row and does not require a visible preference.
- If the user explicitly asks to see every screened fixture, show all of them.
- Archive eligibility and analytical scope remain separate. Never backdate `prediction_at`; archive problems become `ARCHIVE_PENDING`, not hidden formal cases.

## Native evidence vs execution market

### Native SXF evidence markets

Stage 1 reads and interprets only SmartXFlow native stored markets:
- 1X2
- Over/Under 2.5
- BTTS

These markets establish the frozen `SXF PREFERENCE` and thesis for every reported Stage 1 candidate.

### Allowed Stage 3 execution markets

Stage 3 may implement the frozen thesis through a better real-world risk/value market even if SmartXFlow does not natively store it:
- native 1X2 / O-U 2.5 / BTTS;
- Double Chance (`1X`, `X2`, `12`);
- logical handicaps such as `+1.5`, `-1`, `-1.5`;
- nearby alternative totals such as O/U `1.5`, `3.5` when the expected scoring distribution justifies the line.

Draw No Bet (DNB) remains forbidden.

Alternative execution markets are implementations, not new SXF evidence. Never fabricate an exact price.

- externally verified real price -> may be used and archived with source/observed time;
- user-supplied real price -> may be used as actual observed price evidence when exact market, exact selection, price and observation time/provenance are preserved as `USER_SUPPLIED`;
- exact price unavailable -> state a minimum acceptable price threshold and mark it conditional;
- threshold is not actual odds;
- a formal priced `BET` requires a real observed available price when the execution market itself is not natively priced in SXF.

### User-supplied execution price truth

When the user gives a current non-native price such as `Frosinone +1.5 @1.72`:

- preserve exact market + exact selection + exact numeric price;
- source/origin = `USER_SUPPLIED`;
- `observed_at` = explicit user-stated observation time when supplied, otherwise message receipt time;
- it is valid observed price evidence and does not require independent web verification;
- never alter/round it into another price, reuse it for another line/selection, or silently refresh it later;
- ambiguous/stale values become `STALE` / `NEEDS_CONFIRMATION` or conditional only and cannot support a formal priced BET.

## Active Stage 2 focused-research protocol

When Stage 2 begins, Predictor MUST open and follow:

`/.agents/predictor/STAGE2_FOCUSED_RESEARCH.md`

This is the **canonical operational Stage 2 research protocol**. Generic Stage 2 wording elsewhere is only a summary and MUST be interpreted through this file. If generic wording could encourage broader research, unnecessary source collection, or treating missing data as negative evidence, this focused protocol controls.

The purpose is to improve research quality without overloading the model or eliminating candidates merely because external coverage is sparse.

### Mandatory 3+1 research packet

For every carried Stage 1 candidate, Stage 2 first researches only:
1. critical squad impact;
2. market-relevant recent performance;
3. the single strongest plausible counter-case against the frozen Stage 1 thesis;
4. research coverage/source quality (`HIGH | MEDIUM | LOW` internally; Turkish equivalents user-facing).

Default information budget is a maximum of **6 meaningful Stage 2 facts per match**. Prefer a few high-value facts over broad news/stat dumps.

### UNKNOWN is not negative evidence

- Missing information is `UNKNOWN`, not `CONTRADICTED`.
- Low research coverage does not create an automatic confidence penalty.
- Only verified adverse evidence may become Stage 3 counterevidence.
- Small/obscure leagues must not be downgraded solely because reporting or advanced stats are sparse.

### Early-stop rule

Stop Stage 2 research when:
- critical squad status is sufficiently understood for the market;
- 1-2 material market-relevant performance findings are available;
- the strongest plausible counter-case has been investigated;
- coverage/source quality can be classified.

Do not continue collecting marginal articles/statistics merely for volume.

### Source stack

Normal research should usually require only 2-3 sources. Hard/contradictory cases may expand to 3-4; roughly 5 sources is exceptional, not a target.

Core source roles:
- `Flashscore` = broad coverage, absences, predicted/confirmed lineups and quick match context;
- `FotMob` = primary performance hub when coverage exists;
- `Reuters` and official federation/competition/club sources = critical team news, coach comments, availability and factual verification.

Fallback/escalation only when needed:
`Sofascore -> FBref -> Soccerway -> credible local/specialist reporting`.

Do not count the same metric from FotMob/Sofascore/another provider as multiple independent evidence items.

For coach/manager comments prefer:
`Reuters -> official press conference/federation/club source -> credible local reporter`.
Generic motivational press-conference language has no evidential value unless it contains a concrete squad, tactical, workload, role or availability implication.

### Market-specific focus

- `1X2`: material squad imbalance, genuine recent performance strength/weakness, strongest draw/opponent-success path.
- `O/U`: critical attacking/defensive personnel, real creation/concession profile, strongest game-state path that breaks the total thesis.
- `BTTS`: home scoring path, away scoring path, and whether either side's scoring probability is materially misread by the Stage 1 thesis.

Detailed tactics, H2H and broader context are trigger-based rather than mandatory. H2H remains secondary unless recent coach/squad/style conditions are genuinely comparable.

### Compact Stage 2 output

For every carried match use the Turkish user-facing structure required by `STAGE2_FOCUSED_RESEARCH.md`:
- `SXF NE DİYOR`;
- `ARAŞTIRMA DESTEĞİ`;
- `EN GÜÇLÜ ÇELİŞKİ`;
- `ÖNEMLİ EKSİK` when material;
- `ARAŞTIRMA KAPSAMI` — `YÜKSEK | ORTA | DÜŞÜK`;
- `ARAŞTIRMA NE DİYOR`;
- `2. AŞAMA SONUCU` — `DOĞRULANDI | KISMEN DOĞRULANDI | ÇELİŞTİ | AÇIKLANAMADI`.

Internal machine fields may retain English enum names. Important claims remain claim-level and separate `SUPPORTS | CONTRADICTS | NEUTRAL`; do not bundle opposite-direction facts into one generic support row.

## Active Stage 3 hit-rate gates

### Counterevidence severity

Every Stage 3 case must score the strongest contradiction and deduct it from raw confidence:
- `NONE = 0`
- `LIGHT = -3`
- `MEDIUM = -7`
- `STRONG = -12`
- `STRUCTURAL = -20`

These are starting operational penalties, not learned coefficients. Development must later recalibrate them from archived evidence. Serious counterevidence may not remain prose-only while confidence stays effectively untouched.

### Joint divergence state

Closing odds alone are never an automatic confirm/cancel rule. Compare price path, share path, absolute selected money, total market/liquidity growth, native cross-market agreement and market depth/price regime.

Assign exactly one:
`CONFIRMED | MIXED | ADVERSE | MATERIAL_REVERSAL`.

Unexplained `MATERIAL_REVERSAL` normally caps the case at Grade B/WATCH. A price drift with stable or strengthening concentration is not automatically a PASS.

### Protection versus aggression

Any non-native execution transformation must be labeled:
- `PROTECTION`: lower-variance implementation of the same thesis, such as underdog straight -> X2/+1.5.
- `AGGRESSION`: harder line taken for a better price, such as O2.5 -> O3.5 or favorite -> -1.5.

Protection may be preferred when it materially improves hit probability and the real price still has value. Aggression requires stronger distribution evidence than the native line and must never be used only to chase a nicer price.

### Quality grade gate

Every Stage 3 match receives a quality grade before the decision:
- `A+`: all main evidence layers strongly aligned; no unresolved strong/structural contradiction; execution price verified when required.
- `A`: strong overall case with at most one non-material caveat; no unexplained material reversal.
- `B`: mixed evidence, meaningful counterevidence, execution uncertainty or material warning.
- `C`: contradiction dominates, execution is not defensible/verified, or risk shape is poor.

Mandatory mapping:
- `A+ -> BET`
- `A -> BET`
- `B -> WATCH`
- `C -> PASS / no formal archive case`

A high numeric confidence cannot override the grade gate.

## Risk/value translation heuristics

Heuristics, not hard formulas:

- Strong underdog, 1X2 roughly `4.00+`: inspect `+1.5 handicap` because it may retain meaningful price while protecting a narrow loss.
- Medium underdog, roughly `2.70–3.80`: `+1.5` can become too short; inspect Double Chance if its real price still compensates for risk.
- Around `2.20` or shorter: Double Chance is often over-protected/too short. Prefer straight result if thesis is strong, otherwise do not force a protected bet.
- Very short O2.5 (around `1.30–1.35`) plus a genuine 4+ goal thesis: inspect O3.5 only as aggression and only when the harder scoring distribution is independently supported.
- O2.5 around `1.40–1.60` with a simple 3+ goal thesis: usually retain O2.5 rather than adding unnecessary variance.
- Apply the same principle symmetrically to unders and favorite handicaps: protection/aggression must match the thesis, not merely chase a nicer number.

## Mandatory stage order

### 1. Stage 1 — SXF ONLY / SCAN THEN SELECT

- Build the full source universe from the user's explicit SmartXFlow date/time/named-match criteria.
- Inspect every valid fixture in that source universe internally from its own raw/current/stored history.
- Do not use `Analizler`, precomputed signals/rankings/labels or prior Predictor conclusions.
- Read the full available temporal path, not only the latest row.
- Independently interpret money amount/share, new-money velocity, odds path, price response/resistance, liquidity, reversals, momentum, late moves and native cross-market behavior.
- Native Stage 1 evidence/search is only 1X2, O/U2.5 and BTTS.
- Select/report only candidates with a defensible attention reason unless the user explicitly requests every scanned match.
- Every reported candidate gets a frozen `SXF PREFERENCE`: native market + exact selection + cutoff price when available + SXF-only rationale + strongest SXF-only failure condition.
- Screened-out fixtures are not user-facing prediction rows and do not need a visible preference.
- The reported candidate set becomes the default carry-forward set.
- Decide from SXF alone as if later stages do not exist.
- No web research, no final `BET | WATCH | PASS`, no fabricated DC/handicap/alternative-line prices, no DNB.
- Send Stage 1 and STOP.

### 2. Stage 2 — FOCUSED EXTERNAL CAUSE RESEARCH

- Start only after explicit user request.
- Carry forward the exact reported Stage 1 candidate set unless the user changes it.
- Open and follow `/.agents/predictor/STAGE2_FOCUSED_RESEARCH.md` before researching the matches.
- Use the mandatory 3+1 packet and information/source budgets above; do not revert to broad unstructured research.
- Preserve strongest support and strongest contradiction separately as claim-level evidence.
- Keep frozen Stage 1 and external research separate; never rewrite the Stage 1 baseline.
- Missing information remains UNKNOWN; it is never automatically adverse.
- Classify `CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | UNEXPLAINED` internally and use the mandated Turkish wording user-facing.
- Stage 2 may note whether a protected/aggressive execution line would logically fit, but may not pretend it exists in SXF.
- No final decision. STOP.

### 3. Stage 3 — FINAL MERGE / EXECUTION MARKET

- Evaluate every carried Stage 1 candidate unless the user changes the carried set.
- Merge frozen Stage 1 + Stage 2 and strongest countercase.
- Determine the underlying thesis first, execution market second.
- Apply counterevidence severity and confidence penalty.
- Assign the joint divergence state from the complete valid PRE path; closing odds alone cannot decide the case.
- Compare the native selection with logical DC/handicap/alternative-total implementations.
- Label non-native execution as `PROTECTION` or `AGGRESSION`.
- Use the market with the best risk/value relationship, not automatically the safest or highest-odds option.
- Never use DNB.
- Never invent an exact alternative price. Use an actual observed price (`SXF_NATIVE`, `EXTERNAL_VERIFIED`, or `USER_SUPPLIED`) or a clearly labeled minimum acceptable threshold.
- Assign `A+ | A | B | C` before final decision.
- Apply `A+/A = BET`, `B = WATCH`, `C = PASS/no formal case`.
- Every Stage 3 row retains one concrete best-current preference even when action is PASS.
- For BET/WATCH output market, selection, price/threshold, pre-penalty confidence, counterevidence penalty, final confidence, divergence state, execution type, quality grade, rationale and strongest counterargument.
- Keep PASS rows visible with their concrete preference, failed gate(s) and reason; do not archive a fake PASS case.
- Preserve the frozen Stage 1 market/selection in `stage1_baseline` for later matched comparison.
- Freeze real `prediction_at`; never backdate.
- Archive every formal BET/WATCH case automatically when possible; failures remain `ARCHIVE_PENDING`.
- Immediately create Diary 1 `predictions.md`; case archive receipts do not satisfy this.
- Every formal BET/WATCH match in Diary 1 must have a short 1–3 sentence `Why this prediction` explanation written only from PRE evidence.

## Matched Stage 1 vs Stage 3 performance — mandatory

At settlement/end-of-day, evaluate the same settled Stage 1 candidate set twice:

1. **Stage 1 baseline:** settle the original frozen native `SXF PREFERENCE`.
2. **Stage 3 final preference:** settle the final best-current preference hypothetically regardless of action `BET/WATCH/PASS`.

Report at minimum:
- Stage 1 baseline hit rate;
- Stage 3 final-preference hit rate;
- hit-rate delta on the same matched set;
- preference changed vs unchanged counts;
- per-case `IMPROVED | WORSENED | SAME | UNRESOLVED` transition;
- one-unit hypothetical ROI for each stage only where an actual observed price exists.

This comparison is specifically used to answer whether Stage 2/context and Stage 3 execution changes add value over the raw Stage 1 SXF baseline. Positive delta is evidence, not proof; negative delta must be surfaced rather than rationalized away.

## Exactly two mandatory diaries

For every day with at least one formal Stage 3 BET/WATCH case, Predictor MUST create exactly two durable diary files under:

`learning_archive_data/diaries/YYYY/MM/DD/`

### Diary 1 — `predictions.md`

Created immediately when final preferences are issued.

Every formal BET/WATCH match must include:
- final category and quality grade;
- execution market/selection;
- actual price or clearly labeled threshold;
- price provenance when non-native (`EXTERNAL_VERIFIED` or `USER_SUPPLIED` when applicable);
- confidence and immutable `prediction_at`;
- `case_id` / archive state;
- **`Why this prediction`** — concise 1–3 sentence contemporaneous explanation of why that prediction was chosen, based on decisive SXF evidence, Stage 2 context, risk/value logic and the key caution when material.

PASS rows stay visible in the user-facing report but are not formal archive/diary cases.

No later score/result knowledge is allowed in Diary 1.

### Diary 2 — `postmatch.md`

Created/updated once results are available.

Every diary match must include:
- original immutable prediction;
- final score/result;
- WIN / LOSS / VOID, with WATCH explicitly hypothetical;
- **`Why it won/lost`** — concise 1–3 sentence postmatch explanation connecting the result to the thesis, counterargument, final prematch market behavior, execution-line quality, Stage 2 context, or normal variance.

The day-level postmatch review must also include or link the matched Stage 1 baseline vs Stage 3 final-preference summary for the full settled Stage 1 candidate set, including candidates whose final action was PASS.

Merely repeating the score is insufficient. Never rewrite the original prediction after the result.

## Non-substitution and completion gate

Never treat any of the following as either diary:
- `cases/YYYY/MM/DD/<case_id>/`;
- `manifest.jsonl` `RECORDED`/`FINALIZED` events;
- `settlement.json`;
- captures or final SXF snapshots;
- checksums;
- per-case postmatch addenda.

If cases exist but Diary 1 is absent/incomplete, status is `DIARY_PENDING`.
If results exist but Diary 2 is absent/incomplete or any formal match lacks `Why it won/lost`, status is `DIARY_PENDING`.

WATCH outcomes remain hypothetical. Conditional-BET performance must not pretend an unverified threshold price was actually available. A clear `USER_SUPPLIED` observed price may be treated as actual price evidence with exact provenance.

## Required now

1. Treat user date/time/named-match criteria as the Stage 1 source universe; scan every valid fixture internally.
2. Stage 1 must be raw/native SXF-only and match-by-match internally, but user-facing output defaults to attention-worthy candidates only.
3. Every reported Stage 1 candidate requires at least one attention reason and a native frozen `SXF PREFERENCE`.
4. The reported Stage 1 candidate set, not the entire source universe, becomes the default Stage 2/3 carried set.
5. Stage 2 MUST use the canonical Focused Research protocol and its 3+1 packet, information budget, source routing and early-stop rules.
6. Stage 2 must preserve strongest support and strongest contradiction separately at claim level.
7. Missing/low-coverage Stage 2 information is UNKNOWN, not adverse evidence.
8. Stage 3 must score counterevidence severity and apply the active confidence penalty.
9. Stage 3 must use joint divergence state; closing price alone never confirms/cancels.
10. Stage 3 must distinguish `PROTECTION` from `AGGRESSION`.
11. Stage 3 must grade every carried candidate `A+ | A | B | C` and obey A+/A BET, B WATCH, C PASS.
12. Stage 3 may transform the native thesis into DC/handicap/alternative totals for better risk/value.
13. Protection must not destroy price: safer is not automatically better.
14. Aggression must be justified by expected distribution: do not raise lines merely to chase odds.
15. Never synthesize exact execution odds. A threshold must be labeled as a threshold.
16. A clear exact user-supplied non-native price is valid observed price evidence with `USER_SUPPLIED` provenance; never modify or silently refresh it.
17. DNB remains prohibited.
18. Native SXF history must never be relabeled as history for an alternative execution market.
19. Actual non-native execution prices require provenance and `observed_at`.
20. Formal BET/WATCH cases preserve immutable prediction timing, market, selection, actual entry odds when available, confidence, rationale and counterargument.
21. PASS is user-visible only and is not archived as a fake formal case.
22. Formal cases must be durably archived on `learning-archive`; failures are explicit/retryable.
23. Settled formal cases require append-only postmatch learning notes.
24. Every active prediction day requires Diary 1 and Diary 2 as separate durable artifacts.
25. Every formal match requires `Why this prediction` in Diary 1.
26. Every settled diary match requires `Why it won/lost` in Diary 2.
27. Every settled Stage 1 candidate requires matched Stage 1-baseline vs Stage 3-final-preference evaluation, including final PASS rows hypothetically.
28. Case archive completion and diary completion are independent checks; neither implies the other.
29. End-of-day `DONE` requires archive + both complete diaries + the matched stage-comparison output for settled candidates.
30. Predictor structured outputs must satisfy `predictor_policy/validator.py`; do not waive validation failures.

## Archive behavior for alternative execution markets

If Stage 3 selects DC/handicap/alternative total:
- archive the execution market/selection as the final prediction for formal BET/WATCH cases;
- preserve the underlying native SXF market(s) as evidence/provenance;
- record actual execution price only if genuinely observed externally or clearly supplied by the user;
- store origin/source and `observed_at` for actual non-native prices;
- otherwise preserve a conditional minimum price separately, never as fake entry odds;
- explicitly mark native history for that execution line unavailable;
- keep the original 1X2/O-U2.5/BTTS timeline unchanged.

No second collector is required. No DC/handicap/alternative-line SXF history should be fabricated.

## Done per Stage 1

Complete when the full user-defined source universe was enumerated and internally reviewed from native SXF temporal data, every surfaced candidate has an explicit attention reason plus frozen native `SXF PREFERENCE`, screened-out fixtures were not falsely presented as predictions, no external evidence contaminated the stage and no final decision was issued.

## Done per Stage 2

Complete only when every carried Stage 1 candidate has been processed under the canonical Focused Research protocol, the compact 3+1 packet is sufficient for available coverage, strongest support/counterevidence are separated, coverage is classified, Stage 1 remains frozen, and no final `BET | WATCH | PASS` was issued.

## Done per Stage 3

Complete analytically when every carried Stage 1 candidate is visible with a concrete final preference plus graded `BET | WATCH | PASS` outcome and the active quality/price gates were applied. Formal BET/WATCH archive completion additionally requires durable `RECORDED` receipts. Prediction-day workflow additionally requires durable Diary 1 with `Why this prediction` for every formal match.

## Done per end-of-day

End-of-day is `DONE` only when:
1. all settleable formal cases have the required archive/settlement/postmatch state (or explicit unresolved/pending state);
2. `learning_archive_data/diaries/YYYY/MM/DD/predictions.md` exists durably and every formal match has `Why this prediction`;
3. `learning_archive_data/diaries/YYYY/MM/DD/postmatch.md` exists durably and every settled formal match has `Why it won/lost` (unresolved matches explicitly pending);
4. the settled Stage 1 candidate set has a matched Stage 1 baseline vs Stage 3 final-preference comparison, with PASS rows included hypothetically where applicable.

Anything less is `DIARY_PENDING` or comparison-pending, never fully `DONE`.
