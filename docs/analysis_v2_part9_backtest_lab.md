# Analysis V2 Part 9 — Backtest Laboratory

Part 9 is the reproducible evaluation layer for the immutable Analysis V2
ledger. It reports performance; it does not rewrite old triggers, delete failed
signals, or use future information to decide whether a historical signal
qualified.

## Critical entry-price correction

Part 5 can detect a direction in one market and recommend a safer market.

Example:

- source: Away ML at 3.40
- selected recommendation: X2 at 1.62

The old settlement path evaluated the X2 result but still used the source 3.40
trigger price. That would create impossible PnL and materially inflate ROI.

Part 9 fixes the contract:

- every recommendation can freeze a separate recommended_odds value,
- settlement uses recommended_odds when present,
- trigger_odds is allowed only as a legacy fallback when the recommended market
  and selection are exactly the original trigger market and selection,
- if the market changed and recommended_odds is missing, entry price stays
  unknown; the lab never substitutes the source price.

Existing immutable rows are not mutated or backfilled.

## Core metrics

For each cohort the lab reports:

- N rows and N actually staked
- wins / losses / pushes / voids / unknown
- hit rate
- average entry odds
- flat-stake profit units
- flat-stake ROI
- ending equity units
- maximum peak-to-trough drawdown
- CLV sample size
- average CLV
- median CLV
- positive-CLV rate

Hit rate uses WIN / (WIN + LOSS). Pushes are excluded from the hit-rate
denominator.

ROI uses one flat stake for WIN, LOSS and PUSH. A push contributes zero profit
but still represents a placed stake. VOID and UNKNOWN are not included as
staked outcomes.

## CLV

For a valid pre-kickoff closing price:

CLV % = (entry decimal odds / closing decimal odds - 1) * 100

Positive CLV means the signal obtained a better price than the final usable
pre-kickoff snapshot.

The closing-line reader:

- queries the exact match_id_hash,
- queries the actually recommended market and selection,
- only accepts snapshots strictly before kickoff,
- rejects a closing snapshot older than the configured tolerance,
- never feeds closing odds back into signal selection.

Default closing-line maximum age is 180 minutes.

## Drawdown

Maximum drawdown is calculated from cumulative flat-stake realized PnL ordered
by settlement time, with trigger time and signal_id as deterministic tie
breakers.

This is a bankroll-path metric, not just a count of consecutive losses.

## Explainable calibration

Part 8 intentionally has no opaque numeric confidence score, so Part 9 does not
invent one for calibration.

Instead it reports empirical performance for:

- user state: FIRSAT / IZLE / UZAK DUR
- engine key + engine version
- recommended market
- primary classification
- exact config fingerprint
- every Part 8 component level:
  - price confirmation
  - money flow
  - timing
  - cross-market
  - Poly
  - risk

This lets us answer questions such as:

- does FIRSAT actually outperform IZLE?
- does STRONG price confirmation beat MEDIUM?
- does POLY_CONFIRMED improve ROI or CLV?
- does CROSS_CONFIRMED reduce drawdown?
- which exact config version performs better out of sample?

## Market-implied calibration

For non-DNB WIN/LOSS rows the report also exposes:

- average market implied probability from 1 / entry_odds,
- observed hit rate,
- observed minus implied percentage points.

DNB is excluded from this particular comparison because pushes make raw
1 / odds non-equivalent to a simple binary probability.

This field is a market-price reference, not a claimed model probability.

## Data-quality protection

The lab audits old settlement rows before using them.

Flags include:

- ENTRY_ODDS_MISSING
- SETTLEMENT_ENTRY_ODDS_MISMATCH
- SETTLEMENT_PNL_MISMATCH

If a historical cross-market recommendation was settled with the wrong source
odds, the lab recalculates only when the immutable recommended_odds is known.
If the correct recommendation price was never frozen, the row is not trusted
for ROI.

This is intentionally conservative.

## Small samples

Default small-sample warning: N < 30.

The lab still reports the numbers, but marks the cohort SMALL_SAMPLE rather
than presenting it as a stable rule.

## Chronological / out-of-sample comparison

period_report() slices rows by immutable trigger_at. This supports explicit
train / validation / forward-test periods without moving historical signals
between cohorts after results are known.

The same-dataset discoveries from V1 must therefore remain hypotheses until a
later chronological cohort confirms them.

## Config fingerprint

Every immutable config_snapshot receives a deterministic SHA-256-derived short
fingerprint. Results can be grouped by this fingerprint so threshold revisions
are measured separately rather than mixed into one headline number.

## Read path

BacktestDataClient reads:

- analysis_v2_signal_current for settled immutable V2 signals,
- moneyway_snapshots for exact recommended-market closing prices.

No production table is changed by the backtest client.

## Current deployment status

Part 9 code and migrations are prepared on GitHub preview only.

The Analysis V2 ledger migration has not been applied to production, so a real
production V2 historical performance report must not be claimed yet. Once the
V2 ledger is deployed and accumulates immutable signals, this lab can evaluate
those rows without survivorship bias.
