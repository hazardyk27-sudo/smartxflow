---
name: Supabase time-based cleanup deletes
description: How daily D-8 cleanup must delete old rows from Supabase via PostgREST (single-statement, time-based, orphan-inclusive) and why paged-by-id delete hangs.
---

# Supabase daily cleanup: delete by time, not by hash

The daily D-8 cleanup (`services/supabase_client.py:cleanup_old_matches`) must remove
ALL rows older than the cutoff regardless of whether a parent fixture still exists
("ne olursa olsun" — orphans included). Deleting children by a `match_id_hash` join to
surviving fixtures leaves orphaned snapshots behind forever when a fixture is deleted or
its row mutates — that was the root cause of Supabase storage bloat.

**Rule:** Every table is cleaned by its OWN date column with a single-statement PostgREST
DELETE (`?date_col=lt.YYYY-MM-DD`). No cross-table hash dependency.

**Why single-statement, not paged-by-id:** A paged helper that does
`GET ...?select=id&order=id.asc&limit=N` on a filter over a NON-indexed date column forces
a full scan + sort on every page and HANGS on big tables (e.g. `live_snapshots` ~340k rows,
`moneyway_snapshots` ~25M ids). A single DELETE statement is server-side, atomic, and fast
(deleted 17,265 rows in ~2.6s). Helpers: `_count_rows_before` (GET `Prefer:count=exact`,
returns -1 if table 404s) + `_delete_before_simple` (count, then one DELETE).

**How to apply / per-table date columns:**
- `live_snapshots` → `snapshot_at`
- `moneyway_snapshots`, `dropping_odds_snapshots` → `scraped_at_utc` (UTC ISO string)
- 6 `*_history` tables → `scraped_at` (Turkey +03:00 string; lex compare OK at day granularity)
- 6 main market tables (`moneyway_1x2/ou25/btts`, `dropping_1x2/ou25/btts`) → `date` (match
  date, ISO ts). **These tables have NO `match_id_hash` column** — only `id, league, date,
  home, away, odds*, volume…`. The old hash-based delete filtered a non-existent column, so
  they were never actually cleaned. They are current-state upsert tables (tiny, ~tens of rows).
- `fixtures`, `live_fixtures` → `fixture_date`
- `scraper_signal` → `created_at` (D-7); `telegram_sent_log` → `last_sent_at` (D-30)

**Transient SSL blips:** Under concurrent warmup load the shared httpx client sometimes
throws `[SSL] record layer failure`. `_count_rows_before` retries 3× (1.5s/3s backoff) so a
one-off blip doesn't skip a table's delete for the whole day. On persistent failure it
returns 0 (graceful skip) — next daily run retries.

**One-off backlog purge:** `scripts/one_off/purge_old_data_time_based.py` reports + runs the
same time-based cleanup. Note bloat was mostly RECENT in-retention data, not orphans
(`live_snapshots` had 340k total but only ~17k were actually D-8+).

## Large-backlog DELETE timeout: chunk from actual oldest row, not a fixed lookback

A single-statement `DELETE ... WHERE date_col < cutoff` can hit a PostgREST/Supabase statement
timeout (HTTP 500) when the backlog to delete is very large (millions of rows) — confirmed live.

**Fix pattern:** retry the single-statement delete a few times with backoff first (covers
transient failures, keeps normal small daily deletes fast); if it keeps failing, fall back to
deleting one calendar day at a time. The chunk fallback's start point must be the table's actual
oldest existing date value (queried live), NOT a fixed lookback window (e.g. "last 90 days") —
a fixed window silently ignores any backlog older than the window and the cleanup would report
"done" while leaving old data behind forever. A day that still fails after retries must be logged
as skipped/incomplete, not folded into a silent success count — the next run naturally retries it
since it starts from the same live oldest-date query.

**Why this matters:** multiple independent cleanup implementations exist for this project across
different deployment targets (web app, and separate long-running scraper services on Hetzner). A
robustness fix to one does not propagate to the others — apply the same fix everywhere cleanup
logic deletes by date range when touching this area.

**Side-effect to know about:** immediately after a very large purge, `SELECT count(*)` against
the purged table can itself time out (table/index bloat until autovacuum catches up) — expected
and unrelated to the DELETE logic itself.
