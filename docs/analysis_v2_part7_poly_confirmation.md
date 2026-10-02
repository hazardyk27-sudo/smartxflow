# Analysis V2 Part 7 — Poly Confirmation

Part 7 follows the handoff contract exactly:

1. general Polymarket direction,
2. big trades,
3. successful tracked-wallet consensus.

It is a secondary confirmation/risk layer. It does not create the Betwatch
direction, does not select the betting market, and does not overwrite Part 5/6.

## Exact event identity

Part 7 reads Polymarket data only when an exact `event_id` is already known.
It deliberately does not fuzzy-match home/away team names to discover an event.

This prevents Poly evidence from being attached to the wrong fixture. Event
resolution can be added later as a separate audited identity layer.

## Anti-leakage / trigger-time cutoff

The Supabase client requires an explicit `as_of` timestamp. Every prematch
trade and tracked-wallet activity query is capped at that instant. If `as_of`
is after kickoff, the effective cutoff is capped at kickoff.

Tracked-wallet performance rows are also accepted only when
`last_synced_at <= effective_cutoff`. Because `tracked_wallets` stores the
latest aggregate rather than a historical series, this deliberately makes old
retroactive wallet consensus unavailable instead of leaking present-day wallet
performance into a historical trigger. Live forward triggers freeze the
point-in-time Poly result inside the immutable Part 2 signal.

## Component 1 — General Poly direction

Only prematch 1X2 direct `BUY + YES` trades are used to infer a clear outcome
direction. `NO` exposure is not converted into a fake opposite selection,
because "No home" does not uniquely mean away; it also includes draw.

Default forward-test thresholds:

- at least $10,000 direct 1X2 BUY/YES volume,
- leading outcome share >= 55%,
- lead over second outcome >= 10 percentage points.

The result is SUPPORT, CONFLICT, NEUTRAL or UNAVAILABLE relative to the V2
target direction.

## Component 2 — Big trades

Only direct prematch 1X2 BUY/YES trades >= $5,000 are considered big trades.

The component is decisive only if the leading outcome has at least $5,000 more
big-trade volume than the runner-up. This avoids treating two opposing whales
as confirmation.

## Component 3 — Successful wallet consensus

A tracked wallet can vote only when its stored performance snapshot satisfies:

- win rate >= 55%,
- at least 10 resolved bets,
- its direct BUY/YES bet on this match is >= $1,000.

Each qualified wallet receives one directional vote based on its dominant
direct exposure on the match. A wallet with tied/ambiguous exposure does not
vote.

Default consensus:

- at least 2 qualified voting wallets,
- leader has >= 2/3 of wallet votes.

Historical win rate is used only as a qualification filter. It is not converted
into a hidden numeric confidence score.

## Final Poly state

- at least 2 components support and no component conflicts -> `POLY_CONFIRMED`
- at least 2 components conflict and no component supports -> `POLY_CONFLICT`
- at least one support and one conflict -> `POLY_MIXED`
- otherwise -> `POLY_NEUTRAL`
- no usable component data -> `POLY_UNAVAILABLE`

All three component traces remain visible.

## Important interpretation rule

Poly is not allowed to rewrite the core recommendation in Part 7.

For example, if Part 5 selected X2 and Part 6 cross-market evidence is valid,
`POLY_CONFLICT` is stored as an explicit independent risk. Part 8 will decide
how that affects explainable confidence/user state.

## Existing data only

Part 7 uses existing tables:

- `polymarket_matches`
- `polymarket_trades`
- `tracked_wallet_activity`
- `tracked_wallets`

No new migration is required.

All thresholds are versioned forward-test configuration, not claims of proven
optimality.
