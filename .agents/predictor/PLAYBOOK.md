# Predictor Playbook

REFERENCE_VERSION: 11

Open this file only for substantive match-analysis/prediction work.

## Core rule

The Predictor workflow has three separate user-controlled stages. Never collapse them into one unsolicited analysis.

The user-defined match/date/time scope is authoritative and persists across stages. Do not invent extra exclusions because kickoff passed, current time advanced, odds are short/long, liquidity is weak, the league is obscure, or the Predictor prefers a smaller list.

## Market architecture

Predictor uses two different market concepts:

### Native SXF evidence markets

Stage 1 evidence comes only from SmartXFlow native stored markets:
- 1X2
- Over/Under 2.5
- BTTS

These establish the frozen SXF thesis and `SXF PREFERENCE`.

### Stage 3 execution markets

Stage 3 may express that thesis through a more efficient real-world market even if SmartXFlow does not store it natively:
- native 1X2 / O-U2.5 / BTTS;
- Double Chance (`1X`, `X2`, `12`);
- logical team/result handicaps such as `+1.5`, `-1`, `-1.5`;
- nearby alternative goal lines such as O/U `1.5`, `3.5` when the expected scoring distribution supports them.

Draw No Bet (DNB) remains forbidden.

An execution market is not new evidence. Never relabel native 1X2/O-U2.5/BTTS rows as DC/handicap/alternative-line history.

## Alternative-price truth

- Never mathematically invent or synthesize an exact alternative-market price from SXF base odds.
- A real externally available price may be used only when actually verified; preserve source and `observed_at`.
- If exact price is unavailable, give a clearly labeled **minimum acceptable price** condition.
- A minimum acceptable price is a threshold, not actual entry odds.
- Do not call an unverified-price alternative a priced formal `BET`.
- Safer is not automatically better: protection that crushes the price may be inferior to the straight market.
- Higher line is not automatically better: only increase/decrease a total/handicap when the expected outcome distribution supports it.

## Risk/value translation heuristics

These guide Stage 3 but are not rigid formulas:

- **High-odds underdog (roughly 4.00+)**: if the thesis says the underdog is much more competitive than market price suggests, inspect `+1.5 handicap` first. It can preserve meaningful price while protecting a one-goal defeat.
- **Medium underdog (roughly 2.70–3.80)**: +1.5 can become too short; inspect Double Chance if its real price is still worthwhile.
- **Around 2.20 or shorter**: DC is often too compressed. Prefer the straight side if conviction justifies it, otherwise do not force protection.
- **Very short Over 2.5 (around 1.30–1.35)** plus a genuine expectation of 4+ goals: inspect Over 3.5.
- **Over 2.5 around 1.40–1.60** with a normal 3+ goal thesis: usually keep O2.5 rather than adding unnecessary variance.
- Mirror the same logic for unders and favorite handicaps when the thesis clearly supports margin/score distribution.

Examples of the intended logic:
- Liverpool U21 around 5.00 with a strong competitive-underdog thesis -> `Liverpool U21 +1.5` may be superior to the raw 1X2 if its real/threshold price is still attractive.
- Stafford around 3.20 -> +1.5 may be over-protected; `X2` may be a better risk/value expression if the price remains meaningful.
- A side around 2.20 -> DC can become too short; do not recommend it merely to be safer.
- O2.5 around 1.30 with a strong 4+ goal thesis -> O3.5 may be the better execution line only when the 4+ distribution itself is supported.
- O2.5 around 1.45 with only a 3+ goal thesis -> keep O2.5.

## Mandatory Stage 3 decision framework

The following framework is active for every final decision. It is designed to improve hit-rate by rejecting or downgrading weak BETs rather than by manufacturing extra selections.

### Counterevidence severity and confidence penalty

Stage 2 must preserve the strongest support and the strongest contradiction separately. Stage 3 assigns the contradiction one severity:

- `NONE`: 0
- `LIGHT`: -3 confidence points
- `MEDIUM`: -7
- `STRONG`: -12
- `STRUCTURAL`: -20

Apply the deduction to the pre-penalty confidence before the final grade. These are operational starting values to be recalibrated by Development from archived evidence; they are not claimed as statistically optimized coefficients.

Examples of strong/structural counterevidence include material defensive absences against an Under thesis, a repeatable tactical mismatch directly opposing the selection, or a major team-strength premise that no longer holds. Never record a serious counterargument merely as prose while leaving the confidence unchanged.

### Joint divergence state — no closing-price veto

Do not classify a pick from closing odds alone. Compare prediction-time evidence with the latest valid PRE state across:
- selected-side price path;
- selected-side money-share path;
- absolute selected money growth;
- total market/liquidity growth;
- native cross-market agreement;
- market depth/price regime, including possible saturation.

Assign one state:
- `CONFIRMED`: the joint structure remains aligned or strengthens.
- `MIXED`: one component weakens but the broader structure remains defensible.
- `ADVERSE`: multiple components weaken or price resists the thesis materially.
- `MATERIAL_REVERSAL`: the original market story has materially changed, e.g. concentration reverses and price/action no longer supports the thesis.

A `MATERIAL_REVERSAL` normally caps the case at Grade B/WATCH. It may avoid that cap only when new verified PRE evidence directly explains the reversal and the remaining case is still demonstrably strong. A simple adverse closing-price move is never by itself an automatic cancellation.

### Protection vs aggression

Every non-native execution change must be labeled:
- `PROTECTION`: reduces outcome variance while preserving the same directional thesis, e.g. underdog straight win -> X2 or +1.5.
- `AGGRESSION`: asks the outcome to clear a harder line for a better price, e.g. O2.5 -> O3.5 or favorite win -> -1.5.

Protection is preferred when the directional thesis is good but the straight outcome is unnecessarily fragile, **and** a real available price remains worthwhile.

Aggression requires stronger evidence than the native line. Do not raise a total/handicap merely because native odds are short. The expected score/margin distribution itself must support the harder line. If not, keep the native line or WATCH/PASS.

### Quality grade and decision gate

Every Stage 3 match receives one quality grade **before** the final label:

- `A+`: SXF temporal structure, Stage 2 context, divergence state and execution choice strongly align; no unresolved STRONG/STRUCTURAL contradiction; price is real/verified when required.
- `A`: strong overall case with at most one non-material caveat; no unexplained MATERIAL_REVERSAL and no unresolved structural contradiction.
- `B`: mixed evidence, meaningful counterevidence, material warning, low execution certainty, or insufficient confirmation. `WATCH` only.
- `C`: contradiction dominates, execution cannot be defended/verified, or risk shape is poor. User-visible `PASS`; no formal archive case.

Decision mapping is mandatory:
- `A+ -> BET`
- `A -> BET`
- `B -> WATCH`
- `C -> PASS / no formal case`

A confidence number cannot override the grade gate. `82% + Grade B` is WATCH, not BET.

## Stage 1 — independent SmartXFlow-only analysis

Goal: independently inspect every match in the requested SXF slate and create a complete native-market thesis as if later stages do not exist.

1. Start from SmartXFlow primary/production data for the user's exact scope.
2. Enumerate the full slate and inspect **every match individually** before ranking/filtering the report.
3. Do not use SmartXFlow `Analizler`, precomputed signals/rankings/labels/composite scores or prior Predictor conclusions.
4. Use each match's real SmartXFlow identity.
5. Inspect the full available temporal path: earliest stored state/opening, successive snapshots, recent/late movement and analysis cutoff.
6. Independently interpret:
   - absolute money;
   - money share;
   - new-money delta/velocity;
   - full odds path;
   - price response/resistance while money arrives;
   - liquidity and its changes;
   - reversals/momentum/late acceleration;
   - cross-market relationships among native 1X2, O/U2.5 and BTTS.
7. Do not use stored trend/signal labels as the conclusion.
8. Stage 1 searches/analyzes only native SXF markets. Do not pretend DC, handicap or O/U3.5 exists in SXF if it does not.
9. Every match shown must have a mandatory frozen `SXF PREFERENCE`:
   - native market;
   - exact selection;
   - cutoff price when available;
   - SXF-only rationale;
   - strongest SXF-only counterargument/failure condition.
10. Make the strongest SXF-only conclusion as if Stage 2/3 will never happen.
11. No final `BET | WATCH | PASS`.
12. Send Stage 1 and STOP.

### Stage 1 prohibitions

- no web/team-news/external football knowledge;
- no Replit Agent as data source;
- no `Analizler`/precomputed recommendation shortcut;
- no latest-snapshot-only shortcut when history exists;
- no fabricated DC/handicap/alternative-line data or prices;
- no DNB;
- no self-invented started/not-started filter.

## Stage 2 — external cause research

Enter only after explicit user request.

For every carried Stage 1 match:
1. Preserve the frozen native SXF observation and `SXF PREFERENCE`.
2. Research injuries, suspensions, squad/lineups, form, tactics, motivation, schedule/congestion, travel and weather when material.
3. Prefer official team/competition sources, then reliable reporters/data sources.
4. Actively seek support **and** contradiction.
5. Keep `SXF SAYS` and `RESEARCH SAYS` separate.
6. Record strongest support and strongest contradiction separately so both survive into Stage 3.
7. Label `CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | UNEXPLAINED`.
8. Stage 2 may note whether the football context implies a likely margin/scoring distribution relevant to Stage 3 execution-market choice, but it must not fabricate an alternative price or rewrite Stage 1.
9. No final `BET | WATCH | PASS`.
10. STOP.

## Stage 3 — final merge and execution-market selection

Enter only after explicit user request.

1. Evaluate every match the user carried into Stage 3; kickoff/current clock is not an exclusion rule unless the user made it one.
2. Merge frozen Stage 1 + Stage 2 + strongest counterargument.
3. Determine the core thesis first: winner/competitive side, expected scoring level, likely margin, and main failure mode.
4. Assign counterevidence severity and apply the mandatory confidence penalty.
5. Assign joint divergence state from the full valid PRE path; never decide from closing price alone.
6. Compare the native Stage 1 market with logical execution alternatives.
7. Label any alternative as `PROTECTION` or `AGGRESSION`.
8. Choose the market that best balances probability and price:
   - high-odds dog -> consider +1.5 protection;
   - medium dog -> consider DC protection if +1.5 is too short;
   - short side -> avoid crushed DC unless still genuinely valuable;
   - very short O2.5 -> O3.5 only if 4+ goals are genuinely supported, otherwise do not add variance;
   - reasonable O2.5 + 3+ goal thesis -> keep O2.5.
9. Never use DNB.
10. Never invent an exact alternative price.
11. Use either:
   - a verified real execution price; or
   - a clearly labeled `BET/WATCH if price >= X` threshold.
12. If protection/aggression destroys expected value, use the straight market or downgrade to WATCH/PASS.
13. Assign `A+ | A | B | C` quality grade.
14. Apply the mandatory mapping: A+/A BET, B WATCH, C PASS/no formal case.
15. Output market, selection, actual price or threshold, pre-penalty confidence, counterevidence severity/penalty, final confidence, divergence state, execution type, quality grade, rationale and strongest counterargument.
16. Keep every user-scoped match visible. `PASS` means visible no-formal-case, not silent deletion.
17. Freeze real `prediction_at`; never backdate.
18. Archive every formal `BET`/`WATCH` final case when supported; PASS is not archived. Archive failure remains `ARCHIVE_PENDING`.
19. Immediately write Diary 1 `predictions.md`; **do not infer diary completion from case archive success**.
20. For each formal BET/WATCH match write a 1–3 sentence `Why this prediction` note before any result is known.

## Exactly two diary protocol — NOT the case archive

Every day containing at least one formal Stage 3 view has exactly two required diary artifacts under:

`learning_archive_data/diaries/YYYY/MM/DD/`

### Diary 1 — `predictions.md`

Timing: immediately after Stage 3 final decisions.

For every formal final BET/WATCH match record:
- match identity;
- final decision class (`BET`, conditional-BET/execution view, `WATCH`);
- quality grade (`A+`, `A`, or `B`);
- execution market + selection;
- actual price or explicit threshold;
- confidence;
- real `prediction_at`;
- case id/archive state;
- **`Why this prediction`**: 1–3 concise sentences stating the decisive PRE reason for the pick. Mention the key SXF pattern, Stage 2 confirmation/contradiction, risk/value translation and principal caution as appropriate.

User-visible PASS rows remain in the Stage 3 report but are not formal archive/diary cases.

This is contemporaneous rationale. No postmatch facts may be added to it later.

### Diary 2 — `postmatch.md`

Timing: after results become known / settlement review.

For every diary match record:
- original immutable prediction;
- final score/result;
- WIN / LOSS / VOID, with WATCH explicitly hypothetical;
- **`Why it won/lost`**: 1–3 concise sentences explaining why the prediction appears to have worked or failed.

The explanation must be analytical, not “score was X so it lost.” Evaluate whether:
- the original thesis was validated;
- the strongest pre-recorded counterargument materialized;
- final prematch money/share/price reversal or resistance mattered;
- the execution line was wrongly shaped even if directional thesis was right;
- Stage 2 football context explained the outcome or misled the decision;
- normal variance is the best supported explanation.

Never modify the old PRE rationale to make it look smarter after the result.

### Diary performance grouping

Diary 2 must report separately:
1. actual/native `BET`;
2. conditional execution views (`BET_IF_PRICE` / conditional-BET);
3. pure `WATCH`.

WATCH outcomes are hypothetical only. Do not claim a conditional bet was executed unless a qualifying real price was actually verified.

### Completion gate

Case packages and diary files serve different purposes:
- case package = immutable per-match evidence/audit truth;
- Diary 1 = prediction-time day-level reasons;
- Diary 2 = post-result day-level explanations/learning.

Therefore:
- many valid case folders do **not** equal Diary 1 or Diary 2;
- `RECORDED`/`FINALIZED` manifest receipts do **not** equal a diary;
- settlement/addendum completion does **not** equal a diary;
- missing Diary 1, missing Diary 2, or missing a required per-match reason => `DIARY_PENDING`.

## Archive mapping for alternative execution markets

When final execution market is DC/handicap/alternative total:
- preserve the native SXF evidence that generated the thesis;
- archive execution market/selection separately;
- record real execution price only when genuinely observed;
- if only a threshold exists, store it as conditional metadata, not as fake `entry_odds`;
- explicitly mark native SXF history for the execution line unavailable;
- never fabricate alternative-line history.

## Market principles

- Money share alone is weak; price response to money is central.
- More money is not automatically stronger.
- Bigger odds collapse is not automatically better value.
- Use full temporal path, not just opening/current endpoints.
- Distinguish confirmation, divergence, resistance, reversal and late acceleration.
- Closing odds alone never decide confirmation/cancellation.
- Native cross-market analysis remains restricted to 1X2/O-U2.5/BTTS.
- Execution-market choice happens only after the thesis is established.
- Protection and aggression are different operations and must be labeled.
- Always state failure condition/counterargument and score its severity at Stage 3.
- Scope membership and bet quality are different concepts.

## Output minimum

### Stage 1
Show match identity, relevant native market history, temporal interpretation, frozen `SXF PREFERENCE`, cutoff price, rationale and failure condition.

### Stage 2
Show frozen `SXF SAYS`, `RESEARCH SAYS`, strongest support, strongest contradiction and classification.

### Stage 3
For every user-carried match show either a final view or explicit PASS/no-formal-case explanation. A formal BET/WATCH view must include:
- frozen native SXF thesis;
- research classification/context;
- merged view;
- `BET | WATCH`;
- execution market + selection;
- actual entry price or clearly labeled minimum acceptable threshold;
- pre-penalty confidence;
- counterevidence severity and penalty;
- final confidence;
- divergence state;
- execution type (`NATIVE | PROTECTION | AGGRESSION`);
- quality grade;
- strongest support;
- strongest counterargument;
- real `prediction_at`;
- archive state;
- Diary 1 state (`DIARY_RECORDED` or `DIARY_PENDING`).

For a Grade C row, show `PASS`, the failed gate(s), and the reason; do not create a fake archive case.

## Postmortem

After settlement separate process/model error, execution/price error, missing/stale data and normal football variance. A win does not validate a rule and a loss does not invalidate one; method changes require repeated archived evidence and Development testing.

End-of-day is not `DONE` until per-case archive requirements, Diary 1 with `Why this prediction` for every formal match, and Diary 2 with `Why it won/lost` for every settled diary match are all satisfied.