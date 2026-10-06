# Predictor Playbook

REFERENCE_VERSION: 9

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
- O2.5 around 1.30 with a strong 4+ goal thesis -> O3.5 may be the better execution line.
- O2.5 around 1.45 with only a 3+ goal thesis -> keep O2.5.

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
11. No final `BET | WATCH`.
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
6. Label `CONFIRMED | PARTIALLY_CONFIRMED | CONTRADICTED | UNEXPLAINED`.
7. Stage 2 may note whether the football context implies a likely margin/scoring distribution relevant to Stage 3 execution-market choice, but it must not fabricate an alternative price or rewrite Stage 1.
8. No final `BET | WATCH`.
9. STOP.

## Stage 3 — final merge and execution-market selection

Enter only after explicit user request.

1. Evaluate every match the user carried into Stage 3; kickoff/current clock is not an exclusion rule unless the user made it one.
2. Merge frozen Stage 1 + Stage 2 + strongest counterargument.
3. Determine the core thesis first: winner/competitive side, expected scoring level, likely margin, and main failure mode.
4. Compare the native Stage 1 market with logical execution alternatives.
5. Choose the market that best balances probability and price:
   - high-odds dog -> consider +1.5;
   - medium dog -> consider DC if +1.5 is too short;
   - short side -> avoid crushed DC unless still genuinely valuable;
   - very short O2.5 + 4+ goal thesis -> consider O3.5;
   - reasonable O2.5 + 3+ goal thesis -> keep O2.5.
6. Never use DNB.
7. Never invent an exact alternative price.
8. Use either:
   - a verified real execution price; or
   - a clearly labeled `BET/WATCH if price >= X` threshold.
9. If protection/aggression destroys expected value, use the straight market or keep WATCH/no formal bet.
10. Output market, selection, actual price or threshold, confidence, rationale and strongest counterargument.
11. Keep every user-scoped match visible. If no formal selection is defensible, explain why instead of silently dropping it.
12. Freeze real `prediction_at`; never backdate.
13. Archive every formal final case when supported; archive failure remains `ARCHIVE_PENDING`.
14. Write the separate daily diary `predictions.md`; **do not infer diary completion from case archive success**.

## Daily diary protocol — NOT the case archive

Every day containing at least one formal Stage 3 view has a separate diary namespace:

`learning_archive_data/diaries/YYYY/MM/DD/`

Required artifacts:
- `predictions.md` — day-level Stage 1 -> Stage 2 -> Stage 3 summary created after final decisions;
- `postmatch.md` — day-level settlement/performance/learning summary created after results are available.

Case packages and diary files serve different purposes:
- case package = immutable per-match evidence/audit truth;
- diary = human-readable day-level decision/performance narrative.

Therefore:
- many valid case folders do **not** equal one daily diary;
- `RECORDED`/`FINALIZED` manifest receipts do **not** equal a diary;
- settlement/addendum completion does **not** equal a diary;
- if cases are complete and diary is absent, status is `DIARY_PENDING`.

`predictions.md` must include the requested scope and each final formal view with Stage 1 preference, Stage 2 classification, Stage 3 market/selection, decision class, price/threshold, confidence, `prediction_at` and case id.

`postmatch.md` must include each final score/outcome and must report these groups separately:
1. actual/native `BET`;
2. conditional execution views (`BET_IF_PRICE` / conditional-BET); and
3. pure `WATCH`.

Do not convert WATCH into a bet after the result. Do not claim a conditional bet was executed unless a qualifying real price was actually verified. Diary lessons must reference the immutable cases/addenda rather than rewrite them.

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
- Native cross-market analysis remains restricted to 1X2/O-U2.5/BTTS.
- Execution-market choice happens only after the thesis is established.
- Always state failure condition/counterargument.
- Scope membership and bet quality are different concepts.

## Output minimum

### Stage 1
Show match identity, relevant native market history, temporal interpretation, frozen `SXF PREFERENCE`, cutoff price, rationale and failure condition.

### Stage 2
Show frozen `SXF SAYS`, `RESEARCH SAYS`, strongest support, strongest contradiction and classification.

### Stage 3
For every user-carried match show either a final view or explicit no-formal-case explanation. A formal view must include:
- frozen native SXF thesis;
- research classification/context;
- merged view;
- `BET | WATCH`;
- execution market + selection;
- actual entry price or clearly labeled minimum acceptable threshold;
- confidence;
- strongest support;
- strongest counterargument;
- real `prediction_at`;
- archive state;
- diary state (`DIARY_RECORDED` or `DIARY_PENDING`).

## Postmortem

After settlement separate process/model error, execution/price error, missing/stale data and normal football variance. A win does not validate a rule and a loss does not invalidate one; method changes require repeated archived evidence and Development testing.

End-of-day is not `DONE` until both per-case archive requirements and the separate daily diary requirements are satisfied.
