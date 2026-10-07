# Predictor Playbook

REFERENCE_VERSION: 12

Open this file only for substantive Predictor work.

## Canonical execution rule

The human-readable playbook does not override machine policy.

Canonical executable sources:
- `predictor_policy/policy.json`
- `predictor_policy/validator.py`
- `predictor_policy/runtime.py`
- `predictor_policy/stage_comparison.py`

Active detailed workflow requirements live in `/.agents/milestones/PREDICTOR.md`. Stage 2 research details live in `/.agents/predictor/STAGE2_FOCUSED_RESEARCH.md`.

If prose conflicts with executable policy, executable policy controls. A stage output is not valid when its structured payload fails validation or its predecessor state fails the runtime gate.

## Stage 1 — scan, select, freeze

The user's date/time/named-match request defines the source universe to scan.

1. Resolve the full source universe from SmartXFlow primary/production stored data.
2. Internally screen every valid fixture in that universe from its available temporal path.
3. Use only native SXF evidence markets: `1X2`, `O/U 2.5`, `BTTS`.
4. Do not use web/team news, `Analizler`, ready-made labels, prior Predictor conclusions or alternative-market pseudo-history.
5. For each internally selected candidate, preserve structured attention signals and one frozen native `SXF PREFERENCE`.
6. Report selected attention-worthy candidates by default; screened-out fixtures are not prediction rows unless the user explicitly requests the full screening table.
7. Do not issue `BET/WATCH/PASS` in Stage 1. Stop after Stage 1.

Attention signals are structured under policy and include money acceleration, price confirmation/resistance, divergence, reversal, persistence, liquidity-adjusted movement, cross-market confirmation/conflict, late move, saturation, or explained OTHER.

## Stage 2 — focused cause test

Stage 2 requires explicit user authorization and a validated Stage 1 predecessor. Carry the exact selected candidate set unless the user explicitly changes scope.

Follow `STAGE2_FOCUSED_RESEARCH.md` exactly:
- complete the 3+1 research packet;
- maximum 6 meaningful facts per match by default;
- strongest support and strongest counter are separate;
- squad/performance/counter/coverage checks must be completed;
- UNKNOWN / low coverage is not automatically adverse;
- FACT and INFERENCE remain separate;
- no final `BET/WATCH/PASS`.

Stage 2 researches why the frozen SXF thesis may be right or wrong; it does not rewrite Stage 1.

## Stage 3 — merge, execute, grade

Stage 3 requires explicit user authorization and validated Stage 1 + Stage 2 predecessor state.

For every carried candidate:
1. preserve the frozen Stage 1 baseline;
2. preserve the Stage 2 verdict and strongest contradiction;
3. determine underlying thesis before execution market;
4. score counterevidence severity and apply the configured confidence penalty;
5. assign joint divergence state from price/share/money/liquidity/cross-market/regime evidence rather than closing price alone;
6. use `NATIVE` only for native execution; non-native execution must be `PROTECTION` or `AGGRESSION`;
7. assign quality grade before action;
8. obey `A+/A -> BET`, `B -> WATCH`, `C -> PASS`;
9. preserve rationale, strongest counterargument, exact decision timestamp and archive intent;
10. record `change_driver` whenever Stage 3 preference differs from Stage 1.

DNB is forbidden.

## Execution price truth

Never invent or mathematically synthesize a non-native price.

Accepted price origins:
- `SXF_NATIVE`
- `EXTERNAL_VERIFIED`
- `USER_SUPPLIED`
- `THRESHOLD_ONLY`

A current unambiguous user-supplied exact market/selection price is valid observed evidence. Preserve it exactly with `USER_SUPPLIED` provenance and observation/receipt time. Never move that price to another market or silently refresh it.

A threshold is not actual odds. A formal priced non-native BET requires actual observed price evidence.

## Protection vs aggression

`PROTECTION` reduces outcome variance while preserving the thesis, e.g. dog straight win -> X2/+1.5.

`AGGRESSION` requires a harder result, e.g. O2.5 -> O3.5 or favorite -> -1.5.

Safer is not automatically better if the price is crushed. A harder line is not automatically better because its price looks nicer. Execution must match the expected result distribution.

Existing heuristic examples such as high-odds dog +1.5 inspection or very short O2.5 -> O3.5 inspection remain heuristics only, never hard formulas.

## Stage 1 vs Stage 3 learning test

For every settled Stage 1 candidate compare the frozen Stage 1 preference with the final Stage 3 best-current preference on the same matched case set.

Track:
- Stage 1 hit rate;
- Stage 3 final-preference hit rate;
- hit-rate delta;
- changed/unchanged preference count;
- `IMPROVED/WORSENED/SAME/UNRESOLVED`;
- hypothetical one-unit ROI only where real observed prices exist;
- `change_driver`: `NONE`, `STAGE2_RESEARCH`, `EXECUTION_OPTIMIZATION`, `MARKET_UPDATE`, `BOTH`.

Use change-driver grouping to investigate whether Stage 2 research adds value separately from execution-market optimization. Treat results as evidence, not causal proof.

## Archive truth

Formal archive cases are `BET` or `WATCH`; PASS is not a fake formal case. `prediction_at` equals the recorded decision time and is immutable. Original prediction/evidence truth is append-only. Daily `predictions.md` and `postmatch.md` remain separate mandatory artifacts from case folders.
