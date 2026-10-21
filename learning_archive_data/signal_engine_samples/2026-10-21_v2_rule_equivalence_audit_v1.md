# V2 1X2 concentration — canonical vs provisional backfill rule audit
Status: **CONFIRMED NON-EQUIVALENCE**. 2026-10-21. Append-only, no prior CSV modified.

## Canonical source
`preview:base_signal_engine/rules.py` `_v2_valid()` and `select_snapshot()`.

For a 1X2 V1-qualified selected side at checkpoint T-h:
1. Four **complete and fresh (<=30m)** hourly anchor snapshots are mandatory: T-(h+3), T-(h+2), T-(h+1), T-h. Missing any anchor => `MISSING_THREE_HOUR_COVERAGE` (fail closed).
2. Inspect **all complete observed snapshots between the first and latest anchors** for the selected side: no share below 70%.
3. No selected-side quote can be greater than **first anchor odds × 1.03**. This is directional adverse-price rise relative to a frozen initial quote, not the whole-window max-min range.
4. Missing or incomplete evidence must never be interpreted as a pass.

## 14–20 Oct research CSV method
`YYYY-MM-DD_checkpoint_signal_observations.csv` V2 challenger rows were derived using a 3h window minimum selected share >=70% and (maximum odds / minimum odds - 1) <=3%, typically requiring at least two recorded samples. This **does not** enforce the four required fresh hourly anchors and computes odds deviation using minimum odds, rather than the first frozen anchor.

## Why results differ
- First anchor odds 2.00, later odds 1.90 and 1.92: directional canonical increase limit is 2.06, so this price pattern alone is acceptable. Provisional max/min = 2.00 / 1.90 - 1 = 5.26%, so the same pattern would be rejected.
- Conversely, provisional windows can claim a valid V2 result without four fresh anchors; canonical code would reject for insufficient coverage.
- Any original CSV-derived V2 aggregate mixed with the canonical 2026-10-18 rules would silently compare different algorithms.

## Decision / follow-up
1. Treat existing 14–20 Oct V2 rows as `V2_PROVISIONAL_MINMAX_RESEARCH`, not certified canonical V2 results. Keep original rows append-only.
2. In an **additional new dataset**, recover the four hourly anchors and every complete snapshot in the 3h window for each candidate; apply the canonical code's directional anchor and completeness semantics exactly.
3. Publish a per-fixture concordance table: canonical pass, provisional pass, four-anchor availability, share dips, directional adverse rises. Only then compute a comparable 9–20 Oct canonical V2 result.
4. **Do not** deploy altered V2 thresholds or rank V2 above V1 on the provisional daily counts.

This audit is about historical correctness, not live production status.
