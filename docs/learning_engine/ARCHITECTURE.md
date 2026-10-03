# SmartXFlow Learning Engine Architecture

## Goal
Create a long-lived, leakage-safe learning system from real SmartXFlow prediction cases without duplicating the existing live collector and without mixing Poly/Polymarket intelligence into the training set.

## Operating model
There are two conversational agents and no Collector Agent:

1. **Predictor Agent** — researches matches, uses SXF + external evidence, makes selective predictions, settles them and triggers final archival.
2. **Development Agent** — builds the archive/export/validation/feature/backtest/ML system and evaluates repeated evidence.
3. **Existing SmartXFlow data pipeline** — continues collecting market snapshots as it already does. This is infrastructure, not a conversational agent.

## Data flow

```text
Existing SXF snapshot tables
          |
          v
Predictor selects/researches match
          |
          v
Immutable prediction_at + evidence observed_at
          |
          v
Match settles / end-of-day review
          |
          v
Final exporter reads full stored SXF history for that selected match
          |
          v
Validator -> private GitHub Learning Archive
          |
          v
Development builds PRE-only datasets/features
          |
          v
Walk-forward tests -> candidate -> shadow -> controlled review/promotion
```

## Why archive at settlement
SmartXFlow already has the market timeline; continuously collecting it a second time is wasteful. The permanent archive is created after the result/review, while the source history is still available, and contains the entire selected match timeline plus the prediction cutoff.

This also avoids permanently retaining every market in the live database. Only cases that matter to the prediction-learning process become long-term evidence.

## Source retention constraint
The current SmartXFlow operational database has retention cleanup. Therefore a permanent learning case cannot rely only on a pointer to live tables. The selected match payload must be exported before source retention can remove it.

The exporter should detect cases approaching retention expiry and report a hard failure if a selected settled case has not yet been archived.

## Prediction case boundaries
A case is anchored to one immutable prediction event. Required time fields are UTC.

- `prediction_at`: decision cutoff.
- `observed_at`: when the system actually saw an external evidence item.
- `published_at`: source publication time when known, informative but not sufficient for PRE eligibility.
- kickoff/result/finalization timestamps.

PRE eligibility: information must have been observed at or before `prediction_at`.

## Decisions
Use `BET`, `WATCH`, `PASS`. PASS is a first-class outcome and should be learned/tested, not treated as missing data.

## Markets
The Predictor may select the most suitable real market, including 1X2, Double Chance, DNB or another actually available market. Learning datasets must preserve which market was chosen rather than collapsing everything into a single winner label.

## Outcome and execution metrics
Preserve at minimum when available:
- WIN/LOSS/VOID,
- entry odds,
- closing odds,
- CLV,
- P/L and ROI under a declared stake convention,
- confidence,
- time to kickoff,
- final/HT result,
- favorable/adverse movement after entry,
- drawdown contribution or sequence metrics at dataset/report level.

## Feature engineering
Development derives features only from timestamp-valid archived data. Candidate families include money deltas/velocity/acceleration, odds movement/velocity, price response after flow, divergence, liquidity/volume path, opening-to-current move, reversal/momentum, cross-market confirmation, 1X2 vs Double Chance, time-to-kickoff, lineup/news timing, injury/suspension severity, rotation/schedule context and valid form/xG inputs.

## ML/testing lifecycle
1. Build immutable versioned dataset.
2. Establish interpretable baselines.
3. Use time-ordered walk-forward validation.
4. Evaluate hit rate, ROI, CLV, max drawdown, losing streak, variance, calibration, sample size and subgroup stability.
5. Register promising methods/models as `CANDIDATE`.
6. Run `SHADOW` comparison on future unseen cases.
7. Require controlled human review before production promotion.

No automatic self-modification of production.

## Reproducibility
Every experiment/report must identify dataset/archive version, feature version, model/method version, source commit, config/seed, train/test periods, sample size, metrics and status.

## Repository/storage split
- `hazardyk27-sudo/smartxflow`: application source, exporter/validator code, schemas, agent instructions and Learning Engine implementation.
- private `smartxflow-learning-archive`: finalized historical case packages and manifest.
- live Supabase: operational SmartXFlow data with its normal retention policy.

If the archive later becomes too large for normal Git, migrate only the physical archive backend to object storage while preserving package IDs, checksums and logical contract.

## Non-negotiables
- no hindsight rewrite,
- no POST -> PRE leakage,
- no Poly/Polymarket inputs,
- no automatic production promotion,
- no second whole-market collector,
- no silent modification of finalized historical cases.
