# SmartXFlow Base Signals — Part 4B1: durable missing-data routing (preview only)

NOT DEPLOYED. This commit introduces no changes to the frozen `rules.py`, `scheduler.py`, fixture identity, the original scraper or any production environment.

- `SupabaseCheckpointStore.wait_for_data` calls the Phase 4A fenced RPC with a fixed allowlist of reason codes, bounded 60–3600 second delays, and secret-safe errors.
- The durable worker captures source snapshots from its **existing** read and computes verifiable per-market, per-checkpoint coverage using the unchanged `select_snapshot` kernel. No additional Supabase read is needed.
- Base T-8 and T-6 with **no usable market** return to the database `WAITING_DATA` state, not `COMPLETED`. Partial market source evidence may complete with `requires_reconciliation=true` and named missing markets; valid T-6 still supersedes T-8 even if no motor hit.
- Early T-12, Early Core first-hit chronology and Early retention require complete 1X2 source coverage of the relevant checkpoints to avoid treating absence as a genuine no-hit.
- Lease is renewed immediately before completion. Until a periodic heartbeat is implemented, only **one** job can be claimed per execution cycle. DB fencing protects after expiry.
- A lost HTTP response during atomic completion is counted `commit_uncertain`, **not** a confirmed success or a sure failure. Existing database uniqueness + finality guarantee duplicates cannot be minted by replay.
- New tests use injected synthetic source records and simulated RPC transport; no production reads/writes.

**Outstanding**: SQL correction transaction and service-role permission tests, initial queue population watermark, source ingest-versus-scrape watermark, result settlement and two-worker Postgres concurrency/load integration. Correction event vocabulary exists but does not yet perform reconciliation; `requires_reconciliation=true` **must not** be hidden from operators. No automatic 7/24 claims without user approval and migration deployment.
