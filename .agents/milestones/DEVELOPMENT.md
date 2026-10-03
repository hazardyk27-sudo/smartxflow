# Development Current Milestone

MILESTONE_VERSION: 2
STATUS: ACTIVE

## Objective
Finish the minimum reliable selected-match Learning Archive pipeline before model training.

## Required now

1. Implement/validate final case export from existing SmartXFlow stored history; no second live collector.
2. Enforce immutable prediction cutoff and evidence timing.
3. Validate required case metadata, snapshot provenance, settlement and checksums.
4. Make the dedicated private GitHub archive repository the configurable destination.
5. Fail clearly on missing/inconsistent fields; never mutate history while validating.
6. Keep Poly/Polymarket outside the dataset.

## Acceptance

One settled selected prediction can be exported into a self-contained reproducible archive case, and the validator returns deterministic PASS/FAIL with reasons.

## Later, not now

PRE-only feature builder -> reproducible datasets -> baseline models -> walk-forward backtests -> candidate/shadow registry.
