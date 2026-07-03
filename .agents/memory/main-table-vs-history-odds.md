---
name: Main table vs history table as odds source
description: Why match lists must read latest odds from main market tables, not history tables, to avoid matches silently dropping.
---

For "today"/"all" match list queries, always source the latest odds from the main
market tables (`moneyway_1x2`, `moneyway_ou25`, `moneyway_btts`, `dropping_1x2`,
`dropping_ou25`, `dropping_btts`) rather than the `_history` tables.

**Why:** The scraper upserts main tables on `(home, away, date)`, so each match
always has exactly one current row regardless of scrape frequency. History tables
are append-only and were being queried with a shared "top N rows by scraped_at"
window across a batch of matches — a match that stops being actively scraped
after kickoff gets starved out of that window by other matches in the same batch,
comes back with empty odds, and gets silently filtered out client-side
(`checkCompleteOdds` requires all odds fields present). This caused sporadic,
hard-to-reproduce "match missing from list" bug reports.

**How to apply:** Any new match-list/listing feature that needs "current odds for
all matches in a date range" should join fixtures against the main market tables
(bounded size, cleaned by the same D-8 cleanup job as everything else — safe to
fetch in full for a date range), not against `_history` tables. History tables
are only appropriate for querying a single match's time-series (e.g. for charts).
