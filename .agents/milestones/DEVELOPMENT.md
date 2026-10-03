# Development Current Milestone

MILESTONE_VERSION: 3
STATUS: ACTIVE

## Objective
Finish the minimum reliable selected-match Learning Archive pipeline before model training.

## Required now

1. Implement/validate final case export from existing SmartXFlow stored history; no second live collector.
2. Enforce immutable prediction cutoff and evidence timing.
3. Add explicit retention protection so source SXF history required by a selected learning case cannot be removed before verified archive finalization.
4. Validate required case metadata, snapshot provenance, settlement/decision outcome, checksums and post-write manifest integrity.
5. Make the dedicated private GitHub archive repository the configurable destination.
6. Make finalization idempotent and duplicate-safe: same `case_id` must not duplicate or overwrite finalized payloads; identical re-runs return the existing archive identity; materially different re-runs fail closed into explicit correction/version handling.
7. Add secret exclusion checks so API keys, tokens, cookies, auth headers, passwords, private keys, `.env` values and equivalent credentials cannot enter archive payloads or logs.
8. A case is not complete until validator `PASS`, archive write success, post-write manifest/checksum verification and durable archive path/reference confirmation all succeed.
9. Fail clearly on missing/inconsistent fields or incomplete source history; never mutate history while validating. Failed finalization remains explicit and retryable.
10. Keep Poly/Polymarket outside the dataset.

## Acceptance

One settled/reviewed selected `BET|WATCH|PASS` case can be exported into a self-contained reproducible archive case, and:
- retention protection preserves required source history until finalization,
- validator returns deterministic PASS/FAIL with reasons,
- duplicate/idempotent re-run behavior is deterministic,
- secret material is rejected before write,
- successful write is verified by manifest/checksums and returns a durable archive reference,
- failure never produces a false `DONE` state.

## Later, not now

PRE-only feature builder -> reproducible datasets -> baseline models -> walk-forward backtests -> candidate/shadow registry.
