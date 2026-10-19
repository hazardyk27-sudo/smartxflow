# SmartXFlow Base Signals — Part 5C shadow validation & synthetic load
**SOURCE-ONLY `preview`. No production deployment, live SQL, external worker or actual 24-hour run.**

## Implemented

- `base_signal_engine/shadow_evidence.py`: local no-secret JSONL evidence with monotonically numbered samples, UTC timestamps, SHA-256 linked hashes, POSIX exclusive append lock and fsync. Unexpected metric names, negative counts and invalid error codes are rejected. A broken final line or altered hash fails closed. The hash chain protects against accidental changes but **is not authenticated or tamper-proof**.
- `base_signal_engine/shadow_observer.py`: `record_shadow_once(...)` is an explicitly invoked function; it uses the existing read-only shadow scan, the previously proposed server-only health RPCs and local journals. It starts **no loop**. If the scan or health RPC fails, the local record contains a failed cycle rather than invented zero queues. This function is only usable after source/index/credential preflight and explicit operator approval.
- `base_signal_engine/shadow_report.py`: OFFLINE report, no credentials or network access. Example command:
  `python -m base_signal_engine.shadow_report --evidence path/to/approved-run.jsonl --min-hours 24 --max-gap-seconds 180`
  Exit 2 means corrupted/invalid file, 1 means unmet observation gate, and 0 means only that the **provided file's observations** meet the configured thresholds. All outputs retain `real_24h_verified=false`, `production_approved=false`, and independent-attestation-required.
- Part 5C2 adds a PostgreSQL CI-only insert fanout test using **240 synthetic** Moneyway rows and four concurrent workers claiming 25 source deliveries each. The outbox must produce exactly 240 associated snapshot events; no duplicate claim and no loss of pending work. Timing, where reported, is **not** a production SLA/benchmark.

## Minimum gate semantics

The default offline assessment requires:
- Evidence for **at least 24 hours** and at least two observations from one consistently identified run and mode.
- Gap between adjacent samples at most **180 seconds**. The intended approved cadence should be 60 seconds; stricter thresholds may be chosen.
- Zero `failed` scan cycles, `uncertain_commits`, and expired checkpoint/reconciliation/source leases.
- Checkpoint and source `pending_due` each at most **250** per sample; no source mutation manual-review backlog (default zero).
- A full health sample at each observation. Missing RPCs or missing metrics cannot be reported as healthy.
- Mode `SYNTHETIC` is always rejected as evidence of a real 24-hour run. Mode `OPERATOR_READ_ONLY` is **self-declared by the recording program**, NOT an authenticated attestation; even a clean 24-hour file requires a separate human/operator review of actual timestamps, source server identity, read-only permissions, query samples and logs.

The default threshold values are **engineering preflight settings**, not measured production capacity estimates. Do not adjust them to make failing evidence appear successful.

## Operator production-read preflight — NOT EXECUTED

1. Confirm the real `fixtures` and `moneyway_snapshots` table schemas and constraints, sources' exact ID and history retention semantics, RLS/function owner roles, volume and current source load using separately authorized **read-only** access.
2. Use `EXPLAIN (FORMAT JSON)` for representative UID/time bounded queries, with timeouts. Validate index usage and plan stability under multiple fixture/time samples. Do not run `EXPLAIN ANALYZE` or add production indexes without separate approval.
3. Obtain explicit permission to activate the read-only shadow process, including the source, intended time interval, dedicated server-side credentials, bounded polling and local disk path. Source tables must not receive any new migrations/triggers merely to run a shadow scan.
4. Record at least 24 hours of *actual elapsed wall-clock execution* with local evidence and independent system logs; ensure health RPC coverage is available and distinguish source observation timestamps from transaction capture and commit timestamps.
5. Validate all metrics, completeness, lease fencing, rate/impact, source backlog behavior and real prediction evidence before any frontend integration. An offline file or CI synthetic clock advancing across 24 hours is **never** proof of 24 hours of actual running.
6. Separately obtain permission and an operator-reviewed rollback plan before altering `main`, Hetzner, Replit or live Supabase.

## Fail-closed rollback plan — NOT EXECUTED

- First stop only the newly authorized Base shadow/observer, retaining local evidence and logs. Never suppress errors by deleting history.
- If a *separately approved later* source trigger rollout impairs ingestion, pause the new consumer, then remove only the two proposed source-change triggers under DBA oversight. Preserve immutable source changes and deliveries for replay.
- Record any data capture gap and re-bootstrap explicitly; resuming with the latest change_id can skip out-of-order COMMITs and is prohibited.
- Do not silently turn existing `WAITING_DATA`, `RETRY`, `SUPERSEDED` or `CORRECTED` statuses into successful final signals.

## Pending blockers

No actual 24h shadow, no read-only live source schema verification, no p95/p99 live trigger/write impact or production source index plan, no automatic policy for edited/deleted snapshot evidence, and no user approval for deployment. The frozen SXF Base rule thresholds/checkpoint clocks are unchanged.
