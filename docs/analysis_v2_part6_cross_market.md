# Analysis V2 Part 6 — Cross-Market Confirmation

Part 6 reconciles the direction identified by the signal engine across real
provider markets and separately describes the match structure visible in O/U
2.5 and BTTS.

## Directional confirmation

Only markets that actually express the same team exposure can confirm a team
direction:

Home:
- 1X2 -> 1
- DNB -> 1
- DC -> 1X

Away:
- 1X2 -> 2
- DNB -> 2
- DC -> X2

Draw:
- 1X2 -> X only

A supportive directional market must have a real quote and a supportive Part 4
classification. Missing DC/DNB is marked unavailable; it is never synthesized.

Default statuses:
- at least two real same-direction markets support -> `CROSS_CONFIRMED`
- only one supports -> `SINGLE_MARKET_ONLY`
- no support -> `NO_CONFIRMATION`
- any same-direction market shows price-money divergence -> `CONFLICT`

By default the source market must remain supportive. Another market is not
allowed to hide a source-market failure.

## Why O/U and BTTS do not confirm home/away

Over/Under and BTTS describe match shape, not which team wins. Therefore Part 6
does not make invalid implications such as:

`Over price shortened -> away team is confirmed`

Instead, OU2.5 and BTTS are a separate structural context layer.

Clear combinations:
- Over + BTTS Yes -> `OPEN_GAME`
- Under + BTTS No -> `LOW_EVENT`
- only one clear leg or a different combination -> `MIXED`
- no clear confirmed leg -> `NEUTRAL`

A divergence/anomaly in OU or BTTS is exposed as a risk flag but does not invert
the team direction.

## Part 5 reconciliation

`reconcile_market_selection()` can consume the Part 5 recommendation.

- `CROSS_CONFIRMED` keeps the recommendation.
- `SINGLE_MARKET_ONLY` keeps it but records that cross confirmation is absent.
- `CONFLICT` or `NO_CONFIRMATION` converts an existing recommendation to
  `WATCH_ONLY`.

This prevents a selected X2/DNB/ML from surviving a contradictory real
same-direction market.

## Immutable history

`apply_cross_market_to_trigger()` preserves:
- directional support/conflict list
- structural context
- reason/risk codes
- cross-market configuration
- per-market evidence

inside the Part 2 immutable trigger metadata for later backtesting and UI
explanations.

No new production table or migration is required for Part 6.
