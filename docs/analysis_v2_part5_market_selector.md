# Analysis V2 Part 5 — Market Selector

Part 5 chooses how an already-confirmed team direction should be expressed:
Match Odds (ML), Draw No Bet (DNB), or real provider Double Chance (DC).

It does not create a new directional signal and does not synthesize prices,
money percentages or matched amounts.

## Same-direction mapping

Home direction:
- ML -> 1
- DNB -> 1
- DC -> 1X

Away direction:
- ML -> 2
- DNB -> 2
- DC -> X2

Draw direction:
- ML -> X only

DC `12` is deliberately not treated as a draw-direction market because it is
the opposite exposure: it wins when there is no draw.

## Eligibility

A market can be selected only when:
1. a real current provider quote exists,
2. its own Part 4 classification is supportive
   (`CONFIRMED_MOVE`, `LATE_STEAM`, or `EARLY_POSITION`),
3. it has no recent price-money divergence risk.

`PRICE_MONEY_DIVERGENCE`, `ANOMALOUS_MONEY`, missing data and `NO_EDGE`
are not betting recommendations.

By default the source market that created the directional signal must itself
remain eligible. Part 5 does not use another market to hide a source-market
contradiction; cross-market reconciliation belongs to Part 6.

## Protection ladder

No opaque score is used. Among eligible markets the deterministic preference is:

- ML odds >= 2.75: DC -> DNB -> ML
- ML odds 2.00 to 2.74: DNB -> DC -> ML
- ML odds < 2.00: ML -> DNB -> DC

This directly addresses the V1 underdog problem: a 3.40 away direction is no
longer automatically emitted as away ML. If real X2 is available and confirmed,
X2 is preferred; if not, confirmed DNB can be used; only then does ML remain.

These thresholds are explicit forward-test configuration and are not presented
as proven optimal values. Part 9 will evaluate them.

## Real-provider guarantee

`build_direction_market_views()` requests only canonical provider selections
from Part 3:
- away -> 1X2/2, DNB/2, DC/X2
- home -> 1X2/1, DNB/1, DC/1X

If Betwatch does not provide DC/DNB, Part 3 returns no current quote and the
candidate remains unavailable. No synthetic fallback is created.

## Explainability

Every candidate retains:
- availability
- eligibility
- current odds
- Part 4 class
- protection level
- rejection/acceptance reason codes

The selector returns either `RECOMMEND` or `WATCH_ONLY`, plus the full
preference order and candidate trace.

`apply_market_selection_to_trigger()` merges the chosen market and selector
trace into the Part 2 immutable trigger without overwriting existing Part 3/4
metadata.
