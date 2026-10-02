# Analysis V2 Part 4 — Price/Money Classification

## Scope

Part 4 consumes the deterministic market-movement features from Part 3 and
assigns a transparent market-behaviour class.

It does not choose ML/DNB/DC. Market selection belongs to Part 5.

## Core rule

Money percentage is not a confidence score.

- money increases + odds shorten -> `CONFIRMED_MOVE`
- money increases + odds drift higher -> `PRICE_MONEY_DIVERGENCE`
- unusually large money + price remains flat -> `ANOMALOUS_MONEY`
- late confirmed 30m move -> `LATE_STEAM`
- sufficiently early confirmed move -> `EARLY_POSITION`
- otherwise -> `NO_EDGE`

A 95% money share by itself does not outrank 85%, and it does not trigger a
signal without actual matched-money movement plus price behaviour.

## Divergence semantics

`PRICE_MONEY_DIVERGENCE` is a warning about disagreement between money and
price. It is not an instruction to bet the opposite side.

Recent divergence receives priority over an older confirmed move so a stale
positive condition cannot hide a new contradiction.

## Default configuration

Defaults are explicit and versioned:

- minimum market volume: £5,000
- minimum newly added selection money: £500
- confirmed price shortening: 5%
- divergence price drift: 5%
- flat-price band: +/-1%
- anomalous newly added money: £5,000
- anomalous current selection amount: £10,000
- late steam: within 2h of kickoff, >=3% 30m shortening and >=£1,000 added
- early position: >=24h before kickoff, >=3% shortening and >=£1,000 added

These are forward-test configuration, not claims of proven optimality.
Part 9 will evaluate them with backtest/out-of-sample metrics.

## Windows

Every available `open`, `6h`, `2h`, and `30m` window gets evidence for:

- price state
- money state
- odds drop percentage
- money added
- money-share delta
- current selection amount
- current market volume
- reason codes

The general decision prefers `2h -> 6h -> 30m -> open`.
The newest available window is checked separately for divergence.

## Immutable persistence bridge

`classification_to_signal_metadata()` maps the exact classifier reason,
configuration and per-window evidence into the Part 2 immutable metadata
fields. That makes later backtests reproducible.

## Deliberate non-goals

Part 4 does not synthesize DC from 1X2, choose ML/DNB/DC, call divergence an
opposite-side bet, turn high money share into confidence, rewrite old signals,
or generate an opaque score.
