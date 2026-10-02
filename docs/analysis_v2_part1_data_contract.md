# Analysis V2 — Part 1 Data Contract Audit

Date: 2026-10-02 (Turkey time)

## Goal

Freeze the market-data contract before building Analysis V2. The V2 engine must
reason from real provider odds + matched money, not infer a market's money share
from another market.

## Live Betwatch API audit

Read-only audit against the currently configured Betwatch API v1
`/football/prematch` feed:

- 750 prematch football events inspected.
- Match Odds: 740 events.
- Over/Under 2.5 Goals: 697 events.
- Both teams to Score?: 572 events.
- Draw no Bet: 402 events.
- Double Chance: **0 events**.

A second read-only audit of a concrete `/football/event/<id>` response returned
19 markets (including Match Odds, Draw no Bet, multiple goal lines, half-time and
correct score), but no Double Chance market.

Therefore the current provider payload does **not** expose real 1X / X2 / 12
prices or matched-volume shares at the time of this audit.

## Non-negotiable V2 rule

SmartXFlow must never label derived 1X/X2/12 numbers as provider data.

In particular:

- no synthetic Double Chance matched amount;
- no synthetic Double Chance money percentage;
- no fabricated Double Chance price history;
- no fallback that adds 1X2 money percentages together.

If Betwatch starts exposing a real `Double Chance` market, the parser is now
ready to recognize it and the optional tables below can store it immediately.

## Canonical market contract

| Market | Key | Selections | Current table | History table |
| --- | --- | --- | --- | --- |
| Match Odds | 1X2 | 1, X, 2 | moneyway_1x2 | moneyway_1x2_history |
| Double Chance | DC | 1X, X2, 12 | moneyway_double_chance | moneyway_double_chance_history |
| Draw no Bet | DNB | 1, 2 | moneyway_draw_no_bet | moneyway_draw_no_bet_history |
| O/U 2.5 | OU25 | O, U | moneyway_ou25 | moneyway_ou25_history |
| BTTS | BTTS | Y, N | moneyway_btts | moneyway_btts_history |

### Double Chance fields

Current/history rows use:

`odds1x, oddsx2, odds12, pct1x, pctx2, pct12, amt1x, amtx2, amt12, volume`.

### Draw No Bet fields

Current/history rows use:

`odds1, odds2, pct1, pct2, amt1, amt2, volume`.

All money percentages are computed only from the volumes of runners inside the
same provider market.

## Provider-availability behavior

Optional market rows are written only when the provider supplies at least one
usable quote or matched amount. Empty placeholder markets are not persisted.

This matters for Draw no Bet: the market name is present in many current
Betwatch responses, while some events currently carry null runner odds/volume.

## Part 1 implementation

- `betwatch_client.map_market` now supports optional DC and DNB while preserving
  the existing 1X2 / OU25 / BTTS contract.
- DC parser supports generic labels, compact 1X/X2/12 labels, and team-aware
  labels.
- `betwatch_prematch.py` can build current/history rows and snapshots for real
  DC/DNB data when available.
- Additive migration creates DC/DNB current and history tables.
- Parser regression tests guarantee that existing 1X2 mapping is unchanged and
  unknown markets are never synthesized.

## Next dependency

Before enabling Double Chance-based selection logic in Analysis V2, we need a
provider that actually returns real Double Chance odds + matched volume, or
Betwatch must add that market to its API payload. Until then V2 may use DNB as a
real auxiliary market, while Double Chance recommendations must not claim a
provider money-share confirmation.
