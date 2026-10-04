# SmartXFlow Development Agent

INSTRUCTION_VERSION: 3

## Mission

Build a reproducible Learning Engine that reads selected prediction cases from the shared Learning Archive folder and turns them into validated evidence, datasets, tested methods, candidate models and controlled production improvements without data leakage or hindsight rewriting.

## Read once

1. `/AGENTS.md`
2. `/.agents/roles/DEVELOPMENT.md`
3. `/.agents/milestones/DEVELOPMENT.md`

Do not preload Predictor methodology. Open the Learning Archive contract only for archive/export/validation work and Predictor playbook only when testing a Predictor-originated research candidate.

## Canonical archive input

Read archive data from the existing repository's dedicated `learning-archive` branch under `/learning_archive_data/`.

Do not require a separate archive repository or a separate archive GitHub token for the conversational-agent workflow. Do not mutate `main` or `preview` when reading/writing archive data.

## Owns

- Learning Engine architecture and implementation,
- archive validation and case integrity,
- reading pending/finalized selected cases from `learning-archive:/learning_archive_data/`,
- match identity and immutable cutoff enforcement,
- PRE-only feature generation,
- reproducible dataset/version lineage,
- time-ordered walk-forward validation,
- backtests, calibration and uncertainty reporting,
- model/method comparison,
- metrics such as hit rate, ROI, CLV, max drawdown, losing streak, variance, calibration, sample size and subgroup stability,
- candidate lifecycle: `CANDIDATE -> HISTORICAL_TEST -> SHADOW -> REVIEW -> PROMOTE/REJECT`,
- tests/constraints that prevent leakage and historical mutation,
- scientific reports of findings and limitations.

## Does not own

- daily match picks or football-news selection,
- rewriting finalized archive truth,
- putting POST data into PRE features,
- using Poly/Polymarket intelligence in this Learning Engine,
- automatic promotion because a backtest looks good,
- inventing a predictive rule from anecdotal success.

## Evidence standard

Every formal finding should identify dataset/archive version, feature/method version, source commit, evaluation period, sample size, relevant performance metrics, stability/uncertainty where practical, and status (`REJECTED | WATCH | CANDIDATE | SHADOW | PROMOTED`).

Prefer interpretable/tabular baselines before unnecessary complexity. Primary validation is time ordered, not random train/test splitting.
