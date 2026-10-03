# Match Analyst Source Policy

## Purpose

Use a stable source hierarchy so daily research is reproducible and does not depend on random search results.

## Priority order

### Tier 1 — Official / primary
Highest priority for factual team news:
- official club website and official club social channels
- league / federation / competition official sources
- official squad lists and matchday lineups
- manager press conferences and direct verified quotes
- verified player statements

When a reliable official source conflicts with an aggregator, prefer the official source and note the conflict.

### Tier 2 — Core football data hubs

#### Flashscore — primary match research hub
Use as the default football research starting point for:
- fixture status and kickoff context
- form and recent results
- H2H
- lineups / expected lineups where available
- injuries/suspensions where shown
- tables and competition context
- match statistics and xG where available
- odds comparison/context
- previews, reports, and linked news where available

Flashscore is a strong aggregator, not a substitute for an official confirmed lineup or direct club statement.

#### FotMob — secondary statistical verification
Prefer for:
- xG and shot-based match data
- big chances / shot maps where available
- lineup and formation context
- injury/suspension context
- team/player form and match stats

#### Sofascore — secondary cross-check
Prefer for:
- detailed match stats
- lineups/formations
- player/team comparison
- form and H2H cross-check

Do not count Flashscore, FotMob and Sofascore as three independent confirmations if they are repeating the same underlying fact.

### Tier 3 — Squad / transfer context
Use Transfermarkt and official squad registration sources for:
- squad composition
- positions
- transfer/availability context
- historical player absences

Do not use Transfermarkt market values as a direct prediction signal.

### Tier 4 — Reputable news
Use high-quality national/international reporting and credible local football journalism. Prefer, when relevant:
- Reuters
- AP
- BBC Sport
- Sky Sports
- ESPN
- The Athletic
- strong national/local sports desks and established beat reporters

For smaller leagues, credible local reporting can be more useful than global media; identify the outlet and distinguish report from official confirmation.

### Tier 5 — Social/community discovery only
Examples: X/Twitter posts, Reddit, fan forums, Telegram/community chatter.

Rules:
- use to discover a lead, not to establish a critical fact alone
- seek confirmation from Tier 1–4 before changing the final thesis
- clearly mark unverified claims as unverified

## Search protocol

For each RESEARCH candidate:
1. Search official club/competition sources for availability and manager comments.
2. Open Flashscore match context.
3. Cross-check important statistical/lineup claims with FotMob or Sofascore when available.
4. Search reputable news for recent developments in the last relevant time window.
5. Use local reporting when global sources lack coverage.
6. Search specifically for counterevidence against the SXF thesis.

## Freshness rules

- For lineup, injury, suspension, manager comment, weather, and late team news, prioritize the newest reliable source.
- Record publication/update time when timing is material to the odds move.
- Do not use an old injury article as proof of current absence without current confirmation.
- Distinguish predicted lineup from confirmed lineup.

## Causal timing

To claim that a news event plausibly explains a market move, compare timestamps:
- When did the odds/money movement start?
- When did the information become public?
- Was the move before or after publication?

If timing does not fit, do not assert causality. Use `UNKNOWN` or another better-supported cause.

## Statistical discipline

- Prefer comparable competition and home/away samples.
- Note small samples.
- Avoid treating last-five results as sufficient form evidence.
- Separate results from underlying performance (xG, chances, shots, opponent strength).
- H2H is low-weight context unless there is a current tactical/recurrent matchup reason.

## Citation / evidence rule

Every external factual claim that materially affects the final prediction should be traceable to its source. Distinguish clearly between:
- confirmed fact
- reported claim
- predicted lineup
- statistical observation
- analyst inference

Never present analyst inference as sourced fact.
