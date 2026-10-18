# SmartXFlow Base Signals — Part 4A checkpoint persistence hardening

**Source branch:** GitHub \`preview\` only. **Deployment:** NOT APPROVED, NOT EXECUTED.  
**Order:** \`2026_10_18_sxf_base_durable_queue.sql\` then \`2026_10_19_sxf_base_phase4a_waiting_data_hardening.sql\`. Do **not** apply either migration to live Supabase without explicit approval. The missing snapshot composite index remains a separate nontransactional, separately approved operation.

## Why this addendum exists

Phase 4's initial SQL / RPC / adapter appeared on \`preview\` before the handoff indicated; it already had DB job claims, immutable final evaluations, event records and retries for transport errors. However, it allowed a Base checkpoint with **zero usable market snapshots** to commit a final evaluation, and had no first-class \`WAITING_DATA\` state or append-only record of unsuccessful attempts.

This Part 4A adds:
- \`WAITING_DATA\` as a claimable nonterminal state, with \`next_attempt_at\` and optional \`waiting_since\`.
- \`sxf_base_wait_for_data(job_id, lease_token, reason, retry_seconds)\`; returns false for expired/foreign leases and accepts only safe enumerated reasons. Adapter wiring is Part 4B.
- Immutable \`sxf_base_checkpoint_attempts\` diagnostic ledger. Trigger records RETRY, WAITING_DATA, COMPLETED and expired-lease reclamation **in the same transaction** as queue state changes. One event per job attempt; prior audit is never deleted.
- \`sxf_base_require_base_evidence\` refuses to insert a completed Base evaluation if no market has a usable T-6/T-8 snapshot (not merely because no signal hit).
- A DB no-lookahead check on emitted signal \`observed_at\` relative to its **source** checkpoint. Replayed \`recorded_at\` can be later.
- Event vocabulary for future \`CONFIRMED\`, \`INVALIDATED\`, \`CORRECTED\` and \`SETTLED\`. These are **schema capabilities, not a claim of implemented correction processing**.

## Unchanged frozen motor/checkpoint decisions

Existing Phase 1 \`rules.py\` and Phase 3 scheduler are **untouched**. The same 11 checkpoint jobs remain; T-8 preliminary / T-6 authoritative, market-scoped fallback, Early T-72/T-60/T-40/T-24, T-12 and Early retention T-6/5/4/3. Existing SHA-safe fixture identity key, service-role-only database API and immutable event history remain in effect. New migration writes no rows to \`fixtures\`, \`moneyway_snapshots\` or legacy signal tables.

## Important gaps before running any worker

1. The Phase 3 \`evaluate_job\` response does **not** distinguish missing Early market snapshots from legitimate Early no-hits; the 4A trigger protects only an entirely absent **Base** market selection. A Base T-6 with some missing markets can still contain a provisional fallback. Part 4B must define per-market source quality and invoke \`wait_for_data\` where appropriate.
2. The \`WAITING_DATA\` SQL RPC is intentionally **not** wired into \`storage.py\` or \`durable_runtime.py\` in 4A. As-is, a zero-evidence Base commit raises and existing worker would retry via generic \`RETRY\`; no accidental success. Part 4B must explicitly route to \`WAITING_DATA\` and enforce a bounded reconciliation policy.
3. Adding correction event kinds does **not** implement T-6 late-arrival reconciliation. Part 4B/4C must add immutable correction commits with lineage/unique keys, source watermarks and tests; never overwrite a previous preliminary/final event.
4. 4A tests are **static contracts only**. Before DB migration approval, exercise transactional rollback, concurrent two-worker claims, old lease token fencing, Postgres grants/RLS, trigger order, repeated migration in a disposable Postgres clone, delayed/partial source data and index latency. Never use live Supabase as a testbed.
5. The queue persists jobs that were discovered/enqueued. Missed fixture discovery and kickoff rescheduling still require dedicated reconciliation and historical bootstrap. Production remains blocked.

## Part 4B next

Extend the RPC client with \`wait_for_data\`, add explicit source completeness/lag classification to scheduling without modifying signal **rules**, add deterministic correction transaction APIs and multiworker/replay tests; then integrate in Part 4C behind an opt-in runtime gate. Keep \`main\`, Hetzner, Replit and live Supabase untouched until separate approval.
