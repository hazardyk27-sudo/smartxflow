# Analysis V2 Part 3 — Market Movement Feature Engine

## Purpose
Part 3 converts raw prematch market snapshots into deterministic movement features for the later signal engines. It does **not** decide whether a movement is a bet or whether it is strong/weak; that classification belongs to Part 4.

## Canonical source
The engine reads `moneyway_snapshots` rather than depending on the differently named columns in the legacy market-specific history tables.

Each row is already canonical per selection:

- `match_id_hash`
- `market` (`1X2`, `DC`, `DNB`, `OU25`, `BTTS`)
- `selection`
- `odds`
- `volume` = real matched amount for that selection
- `share` = selection money share
- `scraped_at_utc`

For DC/DNB the engine uses rows only when the provider actually supplied those markets. It never manufactures Double Chance price, amount or percentage from 1X2.

## Time anchors
For an analysis instant `as_of`:

- `opening`: first real snapshot for that exact selection
- `6h`: latest snapshot at or before `as_of - 6h`
- `2h`: latest snapshot at or before `as_of - 2h`
- `30m`: latest snapshot at or before `as_of - 30m`
- `current`: latest snapshot at or before `as_of`

6h/2h/30m and current anchors have a configurable staleness tolerance. If no sufficiently close prior observation exists the field stays `NULL`/`None`; it is never replaced with zero.

### Anti-leak rule
A snapshot after an anchor target is never used for that anchor. This is mandatory for forward tests/backtests because otherwise later information would leak into an earlier feature.

## Money fields
For the selected runner:

- `amount` = its actual matched amount
- `pct` = its actual snapshot share
- `market_volume` = sum of actual sibling-runner amounts from the same market and same scrape cycle

This means `market_volume` is reconstructed only inside the real provider market. A 1X2 runner is never used to create DC money data.

## Movement metrics
For opening, 6h, 2h and 30m baselines the engine exposes:

- `odds_delta = current_odds - baseline_odds`
- `odds_change_pct`
- `odds_drop_pct = (baseline - current) / baseline * 100`
- `pct_delta`
- `amount_delta`
- `market_volume_delta`

`odds_drop_pct > 0` means the selected price shortened. Part 3 intentionally does not interpret that as confirmation/divergence; Part 4 will combine price and money directions.

## Immutable trigger integration
`movement_to_signal_fields()` produces the Part 2 trigger snapshot columns:

- opening/6h/2h/30m odds
- 6h/2h/30m pct
- 6h/2h/30m amount
- `money_added_6h`, `money_added_2h`, `money_added_30m`
- trigger odds/pct/amount/market volume
- hours before kickoff
- full market-movement feature JSON

Once a signal triggers, Part 2 freezes these values permanently.

## Read path
`SnapshotHistoryClient` performs read-only PostgREST queries:

1. exact selection opening lookup,
2. sibling rows from the exact opening scrape cycle,
3. paginated recent history from 6h + tolerance through `as_of`.

The companion migration adds composite lookup indexes for these access patterns. The migration is preview-only until production approval.
