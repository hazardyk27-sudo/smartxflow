# SmartXFlow — Supabase production optimization, 22 October 2026

## Scope and authorization

User requested removal of unnecessary database storage/performance overhead,
with a complete reset of **Poly / Polymarket** data. Operations below were
performed against production Supabase project `pswdvnmqjjnjodwzkmkp`.

**Poly data deletion is irreversible without an independently existing backup.**
The Poly ingestion service remains active on Hetzner: new trades and matches
are already being collected after the reset. Therefore this was a point-in-time
data reset, **NOT a permanent stop of Poly ingestion**.

These operations never targeted normal Moneyway/Dropping pre-match history,
fixture history, SXF signal-engine tables, Learning Archive tables, licenses
or user authentication.

## Measured storage

- Initial DB bytes (before Poly reset): **18,871,127,187**.
- Immediately after the 10-table Poly reset: **15,222,787,219**.
- After clearing five redundant indexes and tuning two snapshot tables:
  **14,869,703,827** bytes.
- Total observed decrease: **4,001,423,360 bytes** (~3.73 GiB).
- These are `pg_database_size(current_database())` measurements, not billing
  estimates. Other workloads may concurrently increase DB size.

## 10 Poly-only tables emptied via one transactional migration

Supabase migration `reset_poly_only_data_20261022` succeeded, executing
`TRUNCATE ... RESTART IDENTITY RESTRICT` with short timeouts on precisely:

```text
public.polymarket_trades
public.polymarket_matches
public.polymarket_price_snapshots
public.polymarket_sport_registry
public.tracked_wallet_activity
public.tracked_wallet_positions
public.tracked_wallet_redeems
public.tracked_wallet_bets
public.tracked_wallet_sport_quarantine
public.tracked_wallets
```

The tables, columns and schema constraints remain. Five inbound wallet FKs
all point from included tracked-wallet child tables to `tracked_wallets`.
`RESTRICT`, not `CASCADE`, was used so nonincluded referencing tables
would cause a failure instead of collateral truncation.

**Crucial runtime effect:** `smartxflow-poly.service` in production starts
`poly_runtime.py polymarket_scraper.py` and has `Restart=always`. It has NOT
been stopped or disabled. Read-only stats after the reset already found new
`polymarket_trades` and `polymarket_matches` rows. Re-enabling tracked
wallets will similarly create new data. If the desired outcome is **keep Poly
empty indefinitely**, stop/disable `smartxflow-poly.service` on authorized
Hetzner production first; this requires separate controlled runtime access.
Never use a broad repeating TRUNCATE while the collector is still running.

## Five duplicate indexes actually removed (production)

Each migration verified before DROP:
- identical indexed table/keys, opclass, collation, index options,
  predicate and expression;
- a valid, ready, actively used equivalent survivor;
- no constraint dependencies or external normal/auto dependencies;
- short `lock_timeout` and `statement_timeout` fail closed.

| Removed from `public` | Kept in `public` | Old index approximate size |
|---|---|---:|
| `idx_mw_snap_scraped` | `idx_mw_snap_scraped_utc` | 195 MB |
| `idx_live_snapshots_hash` | `idx_live_snap_hash` | 74 MB |
| `idx_drop_1x2_hash` | `idx_do_1x2_hist_hash` | 30 MB |
| `idx_do_ou25_hist_hash` | `idx_drop_ou25_hash` | 25 MB |
| `idx_drop_btts_hash` | `idx_do_btts_hist_hash` | 16 MB |

Migration names (all succeeded):
- `optimize_drop_redundant_mw_snap_scraped_20261022`
- `optimize_drop_redundant_live_snap_hash_20261022`
- `optimize_drop_redundant_drop1x2_hash_20261022`
- `optimize_drop_redundant_dropou25_hash_20261022`
- `optimize_drop_redundant_dropbtts_hash_20261022`

The exact five dropped indexes were rechecked with `to_regclass` as
absent; all five survivor indexes were checked as present. Supabase
performance-advisor duplicate-index warning count changed from 15 to 10.
Remaining warnings require a separate assessment and are not automatic
permission to drop more indexes.

## Autovacuum on append+delete snapshot tables

Migration `optimize_snapshot_autovacuum_thresholds_20261022` succeeded
for only `public.live_snapshots` and `public.moneyway_snapshots`.
Both have the following reloptions, verified after execution:

```text
autovacuum_vacuum_scale_factor=0.05
autovacuum_vacuum_threshold=10000
autovacuum_analyze_scale_factor=0.03
autovacuum_analyze_threshold=10000
```

Prior estimates were ~384,249 and ~312,409 dead tuples respectively.
Actual vacuum completion/performance effect is **NOT yet verified**.
Reversible with `ALTER TABLE ... RESET (autovacuum_vacuum_scale_factor,
autovacuum_vacuum_threshold,autovacuum_analyze_scale_factor,
autovacuum_analyze_threshold)` after separate production review.

## Important remaining production query optimization

`pg_stat_statements` (stats reset 2026-10-14 UTC) still shows:
- ~88k old `moneyway_1x2_history` first-odds queries using
  home/away/date, averaging ~471ms.
- ~35k 1X2 and ~32k O/U source history broad `LIMIT/OFFSET` scans,
  averaging ~540ms and ~483ms respectively.
- Past Poly wallet sorting queries accounted for tens of GB of cumulative
  **temporary** disk writes; the reset removes that accumulated dataset
  but does not intrinsically optimize future query plans.

The `preview` branch already contains a faster UID-first
`sinyal_first_snapshot_fetch.py`. At audit, `main` still used the
older composite lookup. **No GitHub production code promotion or Hetzner
deployment occurred.** Application-level reader optimization requires
canonical release flow and controlled promotion, not an untracked hot edit
on Hetzner.

Remaining expected work: review all remaining duplicate-index candidates,
audit heavy unfiltered history readers, verify runtime performance
before/after release, and decide separately whether Poly collection should
continue or be permanently paused.

## Validation summary

- Supabase migration responses: success for all seven changes.
- Removed indexes: absent; retained equivalents: present.
- Database size fell by ~4.0 GB.
- Non-Poly signal history and fixtures were still queryable after reset.
- No evidence of database lock waits or idle-in-transaction connections
  at spot checks. This does not substitute for 24-hour production monitoring.
