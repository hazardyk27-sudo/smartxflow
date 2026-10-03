# Development Current Milestone

MILESTONE_VERSION: 1
STATUS: ACTIVE

## Current objective
Build the minimum reliable Learning Archive pipeline and validation layer before any ML work.

## Required now
1. Define and enforce the immutable Learning Archive package contract.
2. Build/export a final archive package only after the selected match is settled/end-of-day reviewed.
3. Export the full stored SXF prematch timeline for that match from existing SmartXFlow data; do not create a second live collector.
4. Preserve prediction cutoff and evidence timing exactly.
5. Validate archive completeness before marking a case usable for learning.
6. Keep Poly/Polymarket completely outside this Learning Engine dataset.
7. Make the archive destination configurable for the dedicated private GitHub Learning Archive repository.
8. Add integrity checks, deterministic IDs/checksums and clear failure reporting.

## Acceptance criteria
A selected historical prediction can be reproduced from one archive package containing:
- canonical match identity,
- complete available SXF prematch timeline,
- immutable prediction record,
- external evidence metadata,
- settlement/result,
- archive provenance/version/checksum.

A validator can answer PASS/FAIL and list missing/inconsistent fields without modifying the archive.

## Next milestones after this one
1. Feature builder from PRE-only data.
2. Reproducible dataset/version builder.
3. Baseline models and calibration.
4. Walk-forward backtest framework.
5. Candidate/shadow model registry.

Do not jump to later milestones until the archive contract and validator are reliable.
