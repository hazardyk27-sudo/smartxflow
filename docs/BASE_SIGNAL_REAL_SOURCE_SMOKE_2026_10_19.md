# SXF Base — real source bounded read-only T-6 smoke (2026-10-19)

**Mode:** read-only live Supabase SELECT sampling, followed by an **offline GitHub CI** run of the actual frozen Base reader/scheduler/kernel on captured source rows. This is not a live worker, historical trading decision, database migration, or production rollout.

## Exact physical fixture and source

- Physical fixture: Degerfors – Kalmar FF.
- `fixture_uid`: `74acc8bd-665e-488c-b1e7-32f95674ccdd`.
- Kickoff UTC: `2026-10-19T17:00:00Z` (20:00 Europe/Istanbul).
- Original `match_id_hash`: `e961dfd96a25` (provenance only; not the identity key).
- Read-only T-8 observation: `2026-10-19T08:54:54Z`, seven complete source rows (1X2: 3, OU25: 2, BTTS: 2).
- Read-only T-6 observation: `2026-10-19T10:55:49Z`, seven complete source rows (1X2: 3, OU25: 2, BTTS: 2).
- A second T-6 observation at 10:50:28Z was independently observed but intentionally **not** mixed with the later 10:55:49Z market group. Exact market timestamps and side counts must remain coherent.
- The captured 14-row test fixture preserves the provider decimal odds, monetary volumes, shares, source ID, observation timestamp and market/side; source secrets are excluded.

## Executed smoke tests

`tests/test_base_signal_real_source_smoke.py`, included in the `preview` GitHub Actions suite, invokes the real `SupabaseMoneywayReader` plus `scheduler.evaluate_job` and `source_quality.source_coverage` against a deterministic **read-only PostgREST HTTP simulation** populated from the actual source rows.

Expected and CI-verified outcomes:

1. All three markets choose `AUTHORITATIVE_T6` with a complete T-6 source disposition; no source-incomplete flag. **Zero motor signals** met frozen thresholds. This is a legitimate NO_HIT, not an error or a bet.
2. If one required OU25 T-6 side is removed in the test, **OU25 alone** falls back to `FALLBACK_T8`; 1X2 and BTTS stay authoritative at T-6. Reconciliation is required for that missing T-6 market.
3. If all T-6 rows are removed, all markets are `FALLBACK_T8` and require reconciliation; there is no fabricated T-6 observation.

**Limit:** The SQL sampling actually read the live source, but the kernel execution happened in isolated CI against the captured rows. Live PostgREST access, long-running shadow, live scheduling and frontend integration are not proven by this test.

## Performance and activation boundary

Earlier real-source EXPLAIN confirmed no composite `(fixture_uid,scraped_at_utc,id)` index. The selected plans used a scraped-time index with a residual fixture UID filter. The snapshot table is approximately 5.9M rows by planner estimate; mass fixture polling is not approved without a scoped index and real load review. Time-index-only 5-minute manual source queries were sufficient for this bounded inspection, not proof of scalable production read latency.

**Next operational dependency:** obtain separate DBA/user approval before creating the gated composite index or activating broad read-only shadow on the production source. Phase 5A source-change triggers are deferred for first read-only Preview. Do not treat generic continuation as authorization for source schema writes or a main/Hetzner release.
