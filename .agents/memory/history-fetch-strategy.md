---
name: History table fetch strategy (SUPERSEDED)
description: Old two-phase history-table fetch approach for get_matches_paginated — replaced by main-table fetch. See main-table-vs-history-odds.md for the current approach.
---

**SUPERSEDED (2026-07-03):** `get_matches_paginated` and `get_all_matches_with_latest`
no longer fetch odds from `_history` tables at all — they read from the main market
tables via `_fetch_main_table_odds()` instead, which eliminates the starvation
problem described below entirely (no shared row-limit window, no missing matches).
See `main-table-vs-history-odds.md` for the current approach. This file is kept for
historical context only (e.g. if history-table fetching is ever needed again for a
single-match time series).

## The Problem
The old approach fetched the latest N rows globally (`ORDER BY scraped_at DESC LIMIT 15000`) and scanned for specific hashes. With ~552 active fixtures being scraped every 5 min, the 15k-row window only covered ~2.3 hours. Matches scraped before kickoff (e.g., matches starting 00:00–05:00 Istanbul) disappeared from the list hours after their last scrape.

## Root Cause
No index on `match_id_hash` in history tables → `IN (...)` queries timed out → fallback to global row scan → time-window problem.

## Fix Applied
1. **DB index (user must apply via Supabase SQL Editor):**
   ```sql
   CREATE INDEX ON moneyway_1x2_history (match_id_hash, scraped_at DESC);
   CREATE INDEX ON moneyway_ou25_history (match_id_hash, scraped_at DESC);
   CREATE INDEX ON moneyway_btts_history (match_id_hash, scraped_at DESC);
   CREATE INDEX ON dropping_1x2_history (match_id_hash, scraped_at DESC);
   CREATE INDEX ON dropping_ou25_history (match_id_hash, scraped_at DESC);
   CREATE INDEX ON dropping_btts_history (match_id_hash, scraped_at DESC);
   ```

2. **Two-phase fetch in `get_matches_paginated` (services/supabase_client.py):**
   - Phase 1: batch `IN (50 hashes)` with `limit=batch*10` → fast for recently-scraped active matches
   - Phase 2: individual `eq.{hash}&limit=1` for remaining hashes (20 parallel workers) → catches any match regardless of when it was last scraped
   - Total time: ~6-7s for 552 fixtures; acceptable since server caches for 100s

**Why:**
`IN (50 hashes) ORDER BY scraped_at DESC LIMIT 500` misses old matches when active matches dominate the top-N rows. Individual `eq.{hash}` queries use the composite index to jump directly to that hash's latest row regardless of age.

## Related
- fixture_date UTC/Istanbul mismatch: kickoff 00:00–03:00 Istanbul → fixture_date is UTC previous day → `date_gte = yesterday_str` buffer in get_matches_paginated (today_only=True path).
- Main market tables (moneyway_1x2 etc.) have no match_id_hash — only history and snapshot tables do.
