# SXF Base Signal Reader — Phase 2 (Preview Only)

Source: `public.fixtures` + `public.moneyway_snapshots`, **GET only**, with provider-authoritative `fixture_uid` identity. `match_id_hash` is audit context; no hash-only fallback. Independent of the existing Sinyal runtime, `predictor_policy`, or release/deploy machinery.

## API

`SupabaseMoneywayReader(base_url, service_key, session=...)`

- `load_fixture(fixture_uid)` resolves exactly one fixture with an aware UTC kickoff.
- `load_checkpoints(fixture, hours=[...], as_of_utc=..., expected_legacy_hash=...)` returns an immutable `SnapshotReadResult` containing complete `Snapshot` objects consumed directly by `base_signal_engine.rules`.
- The production credential must be supplied by the future server-side worker; never expose it in frontend code.
- Readers must select valid/available checkpoints via `choose_base_checkpoint` per market and then call `evaluate_base` at that checkpoint. Do **not** interpret an absent future T-6 as a fallback.
- T-6 / T-8 lookbacks expand to 3h preceding the checkpoint for V2 validation; requests are bounded by the earlier checkpoint cutoff, avoiding lookahead.
- Early Core uses T-72/T-60/T-40/T-24; Early T-12 separate; Early retention T-6/T-5/T-4/T-3.

## Integrity and explicit failure behavior

1. UUID-scoped requests; no match hash-only join or label-based fallback.
2. Each group must have exactly 3 (1X2) or exactly 2 (OU25/BTTS) different selections at the **same `scraped_at_utc`**, valid numeric odds/money/share, and summed share 100±0.5 pp.
3. Earliest/most recent selection is delegated to the frozen kernel; the adapter never fabricates a missing side, mixes timestamps, or lets later snapshots leak into earlier checkpoint evaluations.
4. Pagination runs to a short page. HTTP failures, duplicate IDs, impossible timestamps and pagination exhaustion raise `SnapshotReadError`; the caller must not produce signals from partial results.
5. Invalid *groups* are counted and skipped; a bad group never becomes a valid market snapshot. All such outcomes must be logged by the future worker.
6. Legacy hash drift is counted, not used for identity: valid UID proof takes precedence. Hash-only ambiguous data must be reported unresolved.
7. All computations remain read-only. No signal DB tables or systemd units have been added in Phase 2.

## Database reconnaissance (2026-10-18)

- Last 24h public `moneyway_snapshots`: **421,004** rows; **421,004 / 421,004** carry `fixture_uid`.
- Fixture window `now()-1d` to `now()+4d`: **737 / 737** with `fixture_uid`.
- Native snapshots are numeric and UTC (`odds`, `volume`, `share`, `scraped_at_utc`); older `moneyway_*_history` columns are text and are deliberately not used as the new canonical reader source.
- At reconnaissance time there was **no composite index** on `(fixture_uid, scraped_at_utc)`; this must be benchmarked, and a concurrently built index considered under separate approved migration/release. Do NOT run high fanout polling or historical full-universe scans against production with the current index layout.

## Next phase

Add read-batching/checkpoint scheduler, API pacing and telemetry, persistent signal-event storage, and isolated systemd worker. Add synthetic clock-driven incident tests (delayed ingest, malformed batches, database outages, restart/replay, retention and identity drift). Evaluate a sample of real fixtures read-only with controlled queries, then shadow-test before a production rollout. Main/Hetzner/Replit are out of scope for this phase.