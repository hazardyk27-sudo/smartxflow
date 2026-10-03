# SmartXFlow Learning Engine Architecture

ARCHITECTURE_VERSION: 2

## Goal

Learn from real historical SmartXFlow prediction cases without hindsight leakage, without duplicating the existing market collector and without bloating the live database or source repository.

## Roles

### Predictor

Selects/researches matches, publishes immutable predictions using PRE information only, settles outcomes, and provides final case content.

### Development

Builds exporter/validator, archive integrity, PRE-only datasets/features, evaluation, models and controlled candidate/shadow improvements.

There is no separate Collector conversational agent. Existing SmartXFlow systems already collect/store the market timeline.

## Case lifecycle

```text
existing SXF data flow
        |
Predictor researches selected match
        |
immutable prediction_at
        |
existing SXF storage continues normally
        |
result / end-of-day settlement
        |
export full available prematch timeline for selected case
        |
validate timing + schema + checksums
        |
private GitHub Learning Archive
        |
Development reads finalized cases
        |
PRE-only features/datasets -> walk-forward tests -> candidate -> shadow -> review
```

## Storage boundary

Application repo `hazardyk27-sudo/smartxflow` stores source code, contracts, schema and learning-engine tooling.

Final historical prediction cases belong in a separate private repository: `smartxflow-learning-archive`.

Canonical archive layout is defined by `/.agents/contracts/LEARNING_ARCHIVE.md`. Bulk finalized case data must not accumulate in the application repository.

## Truth boundary

For each prediction:

- `prediction_at` is the fixed PRE/POST cutoff.
- external evidence is PRE only if `observed_at <= prediction_at`.
- PRE may feed prediction/training features.
- POST may feed settlement, labels, diagnosis and retrospective error analysis only.
- original prediction/rationale/snapshots/evidence timestamps are append-only historical truth.

## Learning discipline

Primary validation is time-ordered walk-forward evaluation. Track at least sample size, hit rate, ROI, CLV, drawdown, losing streak/variance, calibration and subgroup stability when data supports them.

Do not promote a model/method from anecdotal wins or one backtest. Candidate methods pass historical testing, then shadow comparison, then controlled review before production promotion.

Poly/Polymarket intelligence is excluded from this Learning Engine.
