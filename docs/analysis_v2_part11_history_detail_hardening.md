# Analysis V2 Part 11 — History, Exact Detail and Integration Hardening

Part 11 completes the Analysis V2 user interface defined by the handoff. It does
not introduce new signal thresholds or replace V1.

## Feed scopes

The V2 page now has three immutable-ledger scopes:

- Active — signals without settlement yet
- History — settled signals
- All — both

The feed supports bounded pagination and keeps the current loaded counts
consistent as more rows are appended.

## Filters

The UI supports:

- FIRSAT / IZLE / UZAK DUR
- canonical recommended market
- match / team / league search

The server validates all enumerated filters before using them. Search text is
bounded and stripped to safe text characters before being used in the
PostgREST ilike filter.

## Exact signal detail

Every card has a Signal History action.

Detail requests use only the immutable signal identity:

GET /api/analysis-v2/signals/<signal_id>

The signal_id must match the canonical sig_<32 hex> format. There is no team
name, league or fuzzy fallback.

The detail endpoint reads:

- analysis_v2_signal_current
- analysis_v2_signal_state_events
- analysis_v2_signal_settlements

and returns a stable presenter payload.

## Lifecycle drawer

The detail drawer shows the append-only lifecycle chronologically:

- TRIGGERED
- ACTIVE
- CONFIRMED
- WEAKENED
- INVALIDATED
- SETTLED

Each available state event keeps its observed odds, money share, matched amount
and reason code visible.

Invalidation never removes the original trigger from history.

## Settlement section

For settled signals the drawer shows:

- WIN / LOSS / PUSH / VOID
- exact final score
- immutable recommended entry odds
- canonical flat-stake PnL
- settlement time
- settlement source

This uses the Part 9 entry-price correction; a source ML quote cannot be shown
as the entry for a selected DC/DNB recommendation.

## Immutable audit

The drawer includes an audit surface for:

- signal_id
- match_id_hash
- engine key/version
- trigger timestamp
- source market/selection
- trigger odds and trigger money
- recommended market/selection/odds

The user-facing card stays simple while the audit trail remains available.

## Read-only guarantee

The Part 11 web routes use GET only.

The Analysis V2 UI does not:

- create signals
- mutate trigger rows
- append states
- settle matches
- update/delete V2 history
- create demo data

Signal generation/persistence remains the responsibility of the V2 engine and
immutable store layers built in earlier parts.

## Guarded runtime bridge

Part 11 also closes the gap between the earlier V2 modules and the immutable
ledger.

After a successful moneyway_snapshots write, betwatch_prematch can call the V2
runtime orchestration layer. The runtime:

- reads one exact match snapshot history batch,
- builds Part 3 movement features,
- runs Part 4 price/money classification,
- applies Part 5 real-market selection,
- runs Part 6 cross-market confirmation,
- keeps Poly unavailable unless exact Poly evidence is supplied,
- builds Part 8 explainable user state,
- writes the first trigger through SignalStore.create_signal_once().

Primary engine identity is selected without duplicate cards:

- price_money_divergence_v2
- anomalous_money_v2
- late_steam_v2
- early_money_lock_v2
- underdog_pressure_v2 when real 1X2 source odds are >= 2.90
- double_chance_pressure_v2 only when real provider DC exists
- otherwise confirmed_money_v2

The runtime is deliberately disabled by default:

ANALYSIS_V2_RUNTIME_ENABLED=0

It also fails closed before history reads if the immutable V2 ledger/view is not
available. A V2 runtime error is isolated from the canonical Betwatch scraper
and must not turn a successful V1/current-market scrape into a failure.

## Missing-ledger behavior

Production migration is still intentionally not applied.

If the ledger/view does not exist, both list and detail surfaces return a
controlled V2_LEDGER_NOT_DEPLOYED state instead of raising a user-visible 500 or
fabricating sample signals.

## V1 isolation

/analysis remains the V1 page. Its engine APIs and rendering logic are
unchanged apart from the navigation link added in Part 10.

/analysis-v2 remains a separate surface.

## Deployment status

All Part 11 changes are on GitHub preview only.

No Replit sync, main merge, Hetzner deployment or production database migration
is performed by this part.
