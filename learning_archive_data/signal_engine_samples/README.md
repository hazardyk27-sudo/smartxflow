# SmartXFlow Signal Engine Samples

Append-only research sample ledger for the tested SXF signal engines. This dataset is separate from Predictor formal case archives and separate from production code.

Purpose: preserve the frozen match-level observations used to test signal engines so later comparisons do not depend on chat history or mutable dashboards.

Primary benchmark window: Europe/Istanbul local kickoff 16:30–23:30 unless a file explicitly states another scope.

Stored engine families:
- EARLY_MONEY (T-72/T-60/T-40/T-24/T-12 definitions as frozen in research)
- EARLY_MONEY_RETENTION_55 (T-6/T-5/T-4/T-3 validation checkpoints for the T-72/T-60/T-40/T-24 family)
- 1X2_CONCENTRATION_V1
- 1X2_CONCENTRATION_V2
- 1X2_CONCENTRATION_HEAVY
- SURPRISE_TEAM
- OVER_STABLE
- OVER_PREMIUM
- BTTS_YES

Important semantics:
- T-6/T-5/T-4/T-3 are observation checkpoints, not standalone signal definitions.
- Every row must use only data observed at or before its checkpoint.
- Same match appearing at multiple checkpoints is not multiple independent matches.
- Snapshot freshness is stored when available. Stale rows must not be silently treated as live-valid operational signals.
- Historical records are append-only. Do not rewrite past outcomes or thresholds; version new models instead.
- This folder preserves research samples, not every raw scraper tick. The production SXF history tables remain the raw collector source; this ledger preserves the frozen signal-relevant observations and outcomes needed to reproduce the tests.

Initial backfill covers 2026-10-09 through 2026-10-13. New days should be appended as new files.
