# Analysis V2 Part 8 — Explainable Confidence

Part 8 deliberately does not produce a single opaque `8.7/10` score. It turns
Parts 3–7 into six visible components and a gated user state.

## User states

- `FIRSAT`: core price/money movement is supportive, Part 5 has a real market
  recommendation, Part 6 is cross-confirmed, and no medium/hard contradiction
  is present.
- `IZLE`: the idea is not contradicted hard, but confirmation is incomplete or
  a meaningful secondary risk exists.
- `UZAK_DUR`: a hard contradiction exists in the core market structure, such
  as price-money divergence or directional cross-market conflict.

Poly alone never creates `UZAK_DUR`. A `POLY_CONFLICT` or `POLY_MIXED`
result is a medium secondary risk and therefore downgrades an otherwise clean
opportunity to `IZLE`.

## Explainable components

Every component returns a level, Turkish UI label, reason codes, and the actual
evidence that produced it.

### Price confirmation

Uses the Part 4 decision window and `odds_drop_pct`:

- >= 5% shortening -> `STRONG`
- >= 3% -> `MEDIUM`
- positive but smaller -> `WEAK`
- drifting against incoming money -> `CONFLICT`
- missing observation -> `UNAVAILABLE`

### Money flow

Uses real `money_added` and money-share delta from the same Part 4 decision
window. High money percentage alone is not strength.

Default forward-test bands:

- strong if added money >= 5,000 or share delta >= 15 points
- medium if added money >= 1,000 or share delta >= 5 points
- smaller positive flow -> weak
- reversed flow -> conflict

These bands are explicit configuration for Part 9 testing, not claims of proven
optimality.

### Timing

- `LATE_STEAM` -> strong
- `EARLY_POSITION` -> medium
- 30m/2h decision window -> strong
- 6h -> medium
- opening-only -> weak

The exact `hours_before_kickoff` remains visible in evidence.

### Cross-market

- `CROSS_CONFIRMED` -> strong
- `SINGLE_MARKET_ONLY` -> weak and a watch risk
- `CONFLICT` -> hard contradiction
- `NO_CONFIRMATION` -> incomplete confirmation, therefore watch

The supporting/divergent real provider markets and OU/BTTS structural context
remain visible.

### Poly

- `POLY_CONFIRMED` -> strong
- `POLY_NEUTRAL` -> neutral
- `POLY_UNAVAILABLE` -> data unavailable, not a negative
- `POLY_MIXED` -> mixed secondary risk
- `POLY_CONFLICT` -> conflicting secondary risk

Poly does not overwrite the Part 5 market recommendation in Part 8.

### Risk

Risks are explicit items with `code`, `severity`, and `source` instead of a
hidden penalty score.

Hard examples:
- core price-money divergence
- recent source divergence
- directional cross-market conflict

Medium examples:
- Poly conflict/mixed
- anomalous-money watch
- cross-market no-confirmation
- single-market-only confirmation
- structural-market divergence

Low example:
- structural-market anomaly

`VERY_HIGH_MONEY_SHARE_CONTEXT_ONLY` remains context, not a material risk.
This preserves the central V2 rule that 95% money is not automatically stronger
than 85% money.

## Immutable trigger integration

`apply_explainable_confidence_to_trigger()` freezes the exact Part 8 user
state, component evidence, reason codes and configuration inside the existing
Part 2 immutable trigger metadata.

This makes the future Part 9 backtest able to reproduce why the UI showed
`FIRSAT`, `IZLE`, or `UZAK_DUR` at trigger time.
