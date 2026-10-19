# SmartXFlow Base — source change capture decision (2026-10-19)

**State:** technical evaluation in GitHub `preview`; **no live source
trigger or writer change approved/installed**. The one-fixture Base
checkpoint and durable event store have passed a real Hetzner smoke,
but full ingestion change completeness has **not** been demonstrated.

## Findings from live read-only SQL and canonical writer source

- `public.moneyway_snapshots` has roughly 6 million live rows
  (Postgres planner estimates), with primary `id integer`,
  `fixture_uid uuid NULLABLE` and nullable `scraped_at_utc`.
- `pg_stat_user_tables` at this review showed roughly **83.55 million
  cumulative DELETE rows** for `public.moneyway_snapshots` and
  **zero UPDATE rows** in that statistic snapshot. These are
  cumulative PostgreSQL statistics, **not daily counts**; do not
  infer a precise delete rate from them.
- A separate table with the same name exists in
  `research_archive.moneyway_snapshots`. Stats and triggers
  must be explicitly schema-qualified; the two must never be
  confused.
- The last 500 rows by descending `id` at observation time
  included no NULL `fixture_uid` but that does **not**
  invalidate historical NULL source UID values.
- The canonical writer currently has
  `desktop/scraper_standalone/standalone_scraper.py:
  SupabaseWriter.insert_snapshots`, which POSTs snapshot rows
  directly into the REST table (not through an atomic outbox RPC).
  This writer is called by both `run_scrape_arbworld` and
  `run_scrape_betwatch_v1`; cleanup also issues separate
  DELETE requests. Source writes may come from other modules.
- Under an ordinary `INSERT` followed by separate `POST
  /source_change`, an interruption between two HTTP requests
  would silently lose the event. A separate publisher is therefore
  insufficient for **complete** source-change capture.

## Options and assurance

| Strategy | Operational impact | Can detect inserts? | Exact UPDATE/DELETE? | Complete, atomic source watermark? |
| --- | --- | --- | --- | --- |
| Phase 5A per-row SQL trigger | High potential overhead during snapshots and purge; requires live load benchmark | Yes | Yes if correctly scoped | Not by itself: trigger-time `captured_at` is not commit watermark |
| Recent-ID bounded GET sampling | Very small, read-only, no source-writer change | Sampled only | Only when an ID remains in consecutive overlapping pages | **No** |
| Bounded fixture rediscovery and checkpoint retries | Compatible with existing source index | Finds visible fixtures in scanned window | Cannot prove all historic row mutations | **No** |
| Writer-side **transactional batch RPC** (candidate) | Requires new versioned ingest endpoint, tests, release approval; fewer ledger rows than per-row triggers | Could capture **all batch inserts** if source rows and receipt share one SQL transaction | Must incorporate retention DELETE and all other writer paths | **Only after** enforcing complete source-writer coverage and a verified database commit-consistent protocol |
| PostgreSQL WAL/logical CDC (candidate) | Replication-slot capacity, operations and hosted Postgres settings require DBA evaluation | Potentially | Potentially | Depends on slot/offset semantics, publication scope, replay and retention handling |

## Implemented safe sample probe (preview only)

`base_signal_engine/source_tail_probe.py` reads a strictly bounded
`ORDER BY id DESC LIMIT N` page, N <= 500. It stores only row
IDs and SHA-256 digests in a `0600` local evidence file;
no odds, volumes, team names or credentials leave the source
request in the saved state. On successive reads it can flag
content changes or potential missing rows **only within the overlap
of sampled ID pages**. It reports `NO_OVERLAP_UNVERIFIED`,
`HEAD_REGRESSION_REVIEW`, `MUTATION_SUSPECTED` or
`OVERLAP_SAMPLED`, always with
`source_mutation_capture_verified=false` and release gate
`BLOCKED_NO_COMPLETE_CHANGE_CAPTURE`. A normal sampled
overlap is never proof of a complete source watermark.

Before running the probe, check live GitHub CI. If the Hetzner
bridge responds, stage the *exact tested preview SHA* into an
isolated clean checkout and issue one authorized one-shot using
existing server-only credentials; local state belongs under the
restricted `/var/tmp/sxf-base-shadow` directory. The probe
makes **zero Supabase writes**. If connection is lost,
**do not claim this one-shot ran**.

## Decision / next development

1. Keep the proposed Phase 5A snapshot triggers **disabled**.
   They would potentially produce enormous DELETE outbox traffic
   during historical retention cleanup. A load benchmark and
   rollback plan are mandatory before any source-table trigger DDL.
2. Continue the already-running temporary read-only 120s diagnostic
   observer. It is limited to 24h, explicitly reports
   `source_capture_verified=false`, and cannot satisfy full release.
3. Use bounded cursor checkpoint discovery as the interim mechanism
   for queued work, but do not claim it captures late-added fixtures
   past the cursor or historic row mutations without a supplementary
   catch-up strategy. Its cursor has **not been initialized**.
4. Prototype **atomic batch source ingestion + one batch receipt per
   transaction** against a disposable DB and mocked writer; include
   fixture-change and retention/delete semantics. Existing writer
   must stay unchanged until the implementation passes a full source
   traceability matrix and exact-SHA release review.
5. Only then consider a low-rate shadow worker with independent
   source coverage attestation. Do not promote to `main`,
   deploy to Hetzner production, enable new signal delivery, or
   mark 24h shadow green from sample-only metrics.

**Current conclusion:** a trigger-free **sampled integrity observer**
is safe and useful diagnostically; it does **not** fulfill the
full correctness requirement by itself.
