---
name: Polymarket tracked wallets architecture
description: Why per-wallet tracking uses /activity + /positions instead of market-wide /trades, and how the feature is deployed.
---

Polymarket's market-wide `/trades` endpoint undercounts a wallet's real activity because large trades get batch-settled and don't always surface individually per market. For accurate per-wallet trade history, avg bet size, win rate, and open positions, fetch directly from the per-user endpoints instead: `/activity?user=&type=TRADE` (paginated, newest-first) and `/positions?user=` (current open/resolved positions snapshot).

**Why:** confirmed by comparing wallet-specific activity counts against what market-level trade listings showed for the same wallet — the per-user endpoints are the source of truth for anything wallet-centric.

**How to apply:** any feature that reports on a specific wallet's behavior (not a specific match) should pull from `/activity` + `/positions`, not aggregate from per-match `/trades` calls.

Data flow: `services/polymarket_client.py` has the fetch/parse/CRUD/profile-stat functions; `polymarket_scraper.py::run_tracked_wallets()` runs the periodic sync and writes to Supabase (`tracked_wallets`, `tracked_wallet_activity`, `tracked_wallet_positions`). This only takes effect in production after a push to `main` triggers `deploy.yml` to the Hetzner box — the workspace's own "Scraper Engine" workflow is a no-op here (see deployment-architecture.md).

This was the one explicitly user-approved exception to the standing "don't touch the scraper" rule in replit.md — scoped narrowly to this new, isolated job; it did not touch existing Arbworld/Betwatch/Sofascore flows.

**Win-rate survivorship bias:** `/positions` only shows a wallet's *current* open/resolved snapshot — once a winning position is REDEEMed (cashed out), it disappears from `/positions` entirely and was never counted anywhere, making win-rate silently drift toward 0% over time. Fix: persist `/activity?type=REDEEM` events to a permanent table (`tracked_wallet_redeems`) and union those condition_ids with resolved-but-unredeemed positions when computing win rate — redeemed wins must never be inferred solely from the live positions snapshot.

**Price display convention:** every trade/position price surfaced for a tracked wallet (activity fills, avg-odds stat, open-position avg/current price) must be shown as decimal odds (1/price), never the raw 0–1 probability — check all render sites, not just the activity table, when adding a new price field. Guard price<=0 -> '-'.

**BUY/SELL vs outcome-polarity fields:** don't conflate them into one `side` column — for 1x2 markets `side` is naturally the raw action, but for OU25/BTTS markets a derived outcome-polarity label (Over/Under, Yes/No) needs to live in its own column separate from the raw BUY/SELL action, or one silently overwrites the other.
