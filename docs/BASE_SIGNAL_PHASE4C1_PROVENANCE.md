# Part 4C1 — Provenance / late T-6 read-only planner

**GitHub `preview` only; no CLI activation or Supabase writes.** The original
Base rules and checkpoint authority policies remain unchanged.

Verified complete market groups from `SupabaseMoneywayReader` now include a
sorted mapping `(market, scraped_at_utc) -> source_row_ids`. Malformed/partial
groups do not enter the map. The immutable `SnapshotReadResult` gains this
optional field without breaking Phase 1–4B consumers.

`plan_late_t6` resolves the fixture by UUID and exact kickoff, reads a
cutoff-bounded T-6 group including the 3-hour V2 anchors, and applies unchanged
`evaluate_base` rules. No snapshot => no plan. Missing/invalid snapshot IDs =>
fail closed. A genuine complete but no-hit market => empty replacement signals,
not a fabricated positive signal. No source table writes or old event mutation.

**Pending for 4C2:** lease-fenced *transactional* correction batch and durable
reconciliation queue, replacing manual individual correction RPC writes; test in
disposable CI Postgres. Historical ingestion receipt timestamp is not available
in the current source schema: never claim observed_at is ingestion time.
