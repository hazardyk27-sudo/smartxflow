---
name: Polymarket public API integration
description: How to query Polymarket's Gamma/Data APIs for real football match events and their executed trades, without auth.
---

Gamma API (`gamma-api.polymarket.com/events`) and Data API (`data-api.polymarket.com/trades`) require no authentication for public read access.

- Soccer tag_id is `100350`.
- `events` endpoint silently caps `limit` at 100 per page regardless of the requested value — must paginate with `offset` in increments of 100 and stop on an empty page, not on `len(page) < requested_limit`.
- Real head-to-head match events are distinguished from variant/futures events (More Markets, Player Props, Halftime Result, Exact Score, Total Corners, etc.) purely by title pattern: a real match title has no " - " suffix (e.g. "Portugal vs. Spain"); variants append a suffix after " - ".
- `endDate` on the event is the actual kickoff time; `startDate` is unreliable (looks like event-creation time), so always sort/filter by `endDate`.
- Each event has `markets[]`; each market has `conditionId` (used to query `/trades?market={conditionId}` on the Data API) and `groupItemTitle`/`outcomes`/`outcomePrices`.
- `/trades` returns `proxyWallet, timestamp, price, side, size, usdcSize, outcome, outcomeIndex` — wallet address there is authoritative/exact. `/public-profile?address=` resolves a wallet's pseudonym (display name only, not identity) but 404s for wallets with no profile — handle gracefully.
- A football match event does NOT have native 1X2/Over-Under/BTTS markets. It has exactly 3 binary sub-markets (home win, draw, away win), each phrased as generic Yes/No with `groupItemTitle` giving the real selection label (team name or "Draw (A vs B)"). Any "why only Yes/No" complaint is a labeling issue, not missing data — derive a `selection` (team/draw name) + `side` (Yes/No) pair from `groupItemTitle`/`outcome` instead of expecting separate market types. Each sub-market's own `volume` field gives per-selection volume; the event's `volume` field gives total match volume.
- `/public-profile` 404s are expected/normal for most wallets (no profile set) — do not treat as an error condition, just fall back to showing the raw wallet address.
- Over/Under and BTTS submarkets for a match live on a *separate sibling event* whose slug is `<main-slug>-more-markets`, not on the main event. Fetch it as its own Gamma API event lookup. These binary markets also expose no per-outcome volume field, unlike the main 1X2 markets.
- To get an exact (not sampled) per-outcome volume split for a single-market Over/Under or BTTS question, fully paginate `/trades?market={conditionId}&limit=500&offset=N` until a short page is returned, and sum `size` per `outcome` — summing ALL matched trades this way reproduces the market's official total `volume` within ~0.2%, whereas summing only the first N (e.g. 200) trades is a biased sample that can be off by a large margin. Cap pagination (e.g. ~12 pages/6000 trades) as a latency safety net for extreme-volume markets.

**Why:** these are non-obvious API quirks (silent pagination cap, unreliable startDate, title-based real-match filtering, Yes/No-only market structure, split-event submarkets) discovered through trial and error; getting them wrong silently drops most events, returns futures markets mixed with real matches, or causes users to think market data is missing when it's just mislabeled or split across events.

**How to apply:** any future work querying Polymarket for match listings or trade data (see `services/polymarket_client.py`) should reuse this filtering/pagination logic rather than re-deriving it.

- `/trades` is returned **newest-first** (verified empirically, no explicit `order` param needed/available) — this makes incremental "only fetch new trades since checkpoint" scraping cheap: page forward and stop as soon as a row's `timestamp` <= the last-known checkpoint, instead of re-fetching full history every run.
- Each trade row already includes `transactionHash` (globally unique per trade) and `pseudonym`/`name` directly — no need to call `/public-profile` per wallet when ingesting a trade ledger; that endpoint is only useful for enriching an already-known wallet later.
- When reading stored trades from `polymarket_trades` (populated by the scraper, with a precomputed `match_phase` prematch/live column) for a high-volume/long-running match, do NOT fetch with a single `order=traded_at.desc&limit=N` query — recent LIVE trades can fill the entire row cap and silently push all PREMATCH trades out of the result. Query each phase separately (own limit) and merge, so both phases are always represented.
