# SmartXFlow — Part 4B2: append-only T-6 reconciliation RPC

**Status: SOURCE ONLY on GitHub preview. Live Supabase migration is NOT authorized.**

Migration: `migrations/2026_10_19_sxf_base_phase4b_reconciliation_rpc.sql`. Apply only after the previously proposed Phase 4 and 4A SQL, on an explicitly approved deployment; the optional composite snapshot index is separate.

The opt-in `sxf_base_append_reconciliation` RPC accepts a *pre-existing, completed* immutable Base event as an origin, a T-6 snapshot **row ID set**, and an evidence object. It looks up the actual source rows by primary key and verifies:

- Same `fixture_uid` and market as the origin; legacy `match_id_hash` is never authoritative.
- All market selections share one `scraped_at_utc`, with precisely 1/X/2, O/U or Y/N and total share 100±0.5.
- Captured timestamp is inside the **T-6 or earlier 30-minute checkpoint window**, even if the rows arrived in storage later. Source arrival time is not confused with scrape observation time.
- `CONFIRMED`/`INVALIDATED` can reference only a T-8 `PRELIMINARY_SIGNAL`; `CORRECTED` can reference only a T-6 `MARKET_DECISION`. Confirmed/invalidated signals preserve their original engine/selection; corrections validate a replacement engine/selection or an explicit no-hit.
- The server derives a stable event key from the origin, type, normalized evidence and validated source; identical replay returns false (already present). A different correction remains a new event. Conflicting identity/evidence is rejected.
- Signal/event rows remain append-only under existing trigger guard, with service-role-only EXECUTE grants, RLS and SECURITY INVOKER. No existing scraper or signal table is written.

**Not yet automatic:** `storage.append_reconciliation` is an RPC adapter, not the correction scheduler. Part 4C must add a periodic reconciliation dispatcher, compute replacement signals using frozen rules, capture source row IDs in the reader, implement source-arrival watermarks and safely present versioned projections. 4B2 does not claim to produce live corrections or ensure a correction means a valid betting preference. Before any migration application: prove real Postgres transaction rollback, duplicate behavior, permission and simultaneous worker claims using disposable test DB.
