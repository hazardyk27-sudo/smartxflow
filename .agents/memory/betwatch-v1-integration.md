---
name: Betwatch API v1 integration
description: Key facts about the Betwatch API v1 migration for prematch + live scrapers
---

## Secret name
`Betwach_api_key` — typo (missing 't'). Never use `Betwatch_api_key`.

## Auth
`Authorization: Token <key>` — NOT Bearer, NOT Cookie.

## Base URL
`https://api.betwatch.fr/api/v1`

## Rate limits
- `/football/prematch` → 1 req/40s (90/hr) — scraper runs every 9 min, safe
- `/football/live` → 1 req/10s (360/hr) — live scraper runs every 1 min, safe

## Data shape
Each match: `{match_id, teams:{v1(home), v2(away)}, league, country, kickoff(UTC ISO "Z"), markets:[{market_id, name, runners:[{runner_id, name, volume, odd}]}], live_info(live only)}`

`live_info`: `{time(minute int), is_ht, finished, goal_v1, goal_v2, red_v1, red_v2, yellow_v1, yellow_v2, extra_time}`

## Runner name mapping
- Match Odds: runners are team names + "The Draw". Use: detect "draw" in name → "X", first runner → "1", last → "2"
- Over/Under N.N Goals: "Over"→"O", "Under"→"U"
- Both teams to Score?: "Yes"→"Y", "No"→"N"

## File architecture
- `betwatch_client.py` (root) — shared client (fetch_prematch, fetch_live, map_market, normalize_kickoff, betwatch_live_minute/score)
- `betwatch_prematch.py` (root) — server-side prematch scraper; reads prev dropping odds from DB before writing
- `scheduled_scraper.py` — imports `run_scrape_betwatch` from betwatch_prematch (replaces Arbworld)
- `live_scraper.py` — uses `_fetch_betwatch_v1_live` + `_process_betwatch_v1_live`; Sofascore/APIFootball/league_mapping REMOVED (all data from Betwatch incl. live_info score+minute)

**Why:** Arbworld was 403-blocking Hetzner/Replit IPs; old betwatch used cookie auth (fragile). Betwatch v1 uses stable Token auth and provides live_info (minute+score) directly. Sofascore/APIFootball cleanup done when user confirmed single-source architecture.

## Single source confirmed
Betwatch v1 is the ONLY data source for both prematch and live. Sofascore, APIFootball, and league_mapping.json are all obsolete. Do NOT re-add them.
