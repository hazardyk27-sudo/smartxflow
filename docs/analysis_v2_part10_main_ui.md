# Analysis V2 Part 10 — Main Explainable UI

Part 10 introduces a separate Analysis V2 surface at `/analysis-v2`. The V1
analysis page and V1 signal engines remain intact.

## First-screen question

The page is designed around one beginner question:

> Piyasa ne söylüyor?

The top of the page explains the system before showing any signal:

- FIRSAT — core price/money movement and cross-market confirmation align.
- İZLE — a direction exists but confirmation is incomplete or a meaningful
  secondary risk remains.
- UZAK DUR — the core market structure contains a hard contradiction.

The central rule is displayed explicitly:

`Para geldi → oran düştü → piyasa teyit etti.`

The UI also states that a high money percentage alone is not a strong signal.

## Signal card hierarchy

Every V2 card is ordered for first-time comprehension:

1. user state badge,
2. match / league / kickoff,
3. selected market expression and frozen odds,
4. plain-language direction,
5. three-step price/money confirmation chain,
6. trigger-window numbers,
7. six explainable components,
8. expandable WHY / RISKS / DETAILS.

The card does not lead with engine names or internal thresholds.

## Numeric evidence

The compact evidence strip exposes:

- decision window,
- money added in that window,
- base odds → current odds,
- current money share and share change.

This makes labels such as “strong money flow” auditable from the same card.

## Six explainable components

The UI renders the Part 8 components independently:

- Fiyat Teyidi
- Para Akışı
- Zamanlama
- Cross-Market
- Poly
- Risk

There is no overall 0–10 score.

## Expandable details

### NEDEN?

Shows short human-readable reasons derived from immutable Part 8 reason codes.

### RİSKLER

Shows material risk items with severity. No-risk cards say so explicitly.

### DETAYLAR

Shows internal audit fields without forcing them into the main visual hierarchy:

- primary class
- decision window
- source market / selection
- engine key/version
- risk count
- immutable ledger state

## Stable presenter contract

`analysis_v2/presenter.py` converts raw immutable ledger rows into
`analysis-v2-ui-1.0.0`.

The browser therefore does not depend directly on nested engine JSON and can
remain stable while the internal V2 implementation evolves.

## Read-only data path

`GET /api/analysis-v2/signals` reads `analysis_v2_signal_current` and passes
the rows through the presenter.

The Part 10 endpoint performs no inserts, updates, deletes, settlement, or signal
generation.

## No fake/demo signals

The UI deliberately does not create sample cards when the V2 ledger is empty or
not deployed.

If the V2 ledger migration has not been applied, the endpoint returns a
controlled `V2_LEDGER_NOT_DEPLOYED` state and the page explains that it is
waiting for real immutable data.

## V1 isolation

Part 10 does not replace `/analysis`.

The existing page receives only a navigation link to `/analysis-v2`; its V1
signals, APIs and rendering behavior are unchanged.

## Responsive behavior

Desktop is designed for a wide analysis surface up to 1360px. The same card
hierarchy collapses progressively for tablet and mobile:

- 6 components → 3 columns → 2 columns
- 4 evidence cells → 2 columns
- WHY / RISKS / DETAILS → vertical accordion
- recommendation box becomes full-width on narrow screens

## Deployment status

Part 10 is committed to GitHub `preview` only. Replit, production `main`,
Hetzner and production database migrations are unchanged.
