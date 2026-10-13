# SXF 1X2 CONCENTRATION V2 — 9–12 October 2026

Status: **RESEARCH_CANDIDATE / HEAD-TO-HEAD VALIDATION REQUIRED**

Purpose: keep the existing **1X2 CONCENTRATION V1** completely unchanged and track a separate behavior-aware **V2** in parallel on future days.

## V1 — unchanged baseline

The existing 1X2 CONCENTRATION remains exactly as-is:

- current checkpoint top-money **TEAM** side (HOME/AWAY, not Draw)
- selected-side amount >= **£1,000**
- selected-side share >= **80%**
- selected-side decimal odds **1.40–2.50 inclusive**

9–12 October 2026 baseline results:

| Checkpoint | Wins / n | Hit rate |
|---|---:|---:|
| T-6 | 31 / 39 | 79.5% |
| T-5 | 38 / 48 | 79.2% |
| T-4 | 39 / 50 | 78.0% |
| T-3 | 38 / 52 | 73.1% |

T-6/T-5/T-4/T-3 are observation checkpoints, not different standalone signal definitions.

## V2 — behavior-aware candidate

V2 starts with the exact same current-snapshot V1 conditions, then adds two backward-looking checks using only snapshots available at or before the prediction checkpoint:

1. **3-hour share persistence**
   - during the prior 3 hours ending at the checkpoint, the selected side's 1X2 money share must **never fall below 70%**.

2. **Adverse odds ceiling**
   - over the same prior 3-hour window, the selected side's odds must **not rise by more than 3%** against the selection.
   - odds shortening is not required; the rule only rejects a material adverse move greater than 3%.

Therefore:

> **1X2 CONCENTRATION V2 = V1 + prior-3h share floor >=70% throughout + prior-3h adverse odds rise <=3%.**

All V2 calculations are leakage-safe: the 3-hour lookback ends at the actual T-minus checkpoint and never uses later snapshots.

## 9–12 October retrospective comparison

| Checkpoint | V1 | V2 |
|---|---:|---:|
| T-6 | 31/39 = 79.5% | 27/32 = **84.4%** |
| T-5 | 38/48 = 79.2% | 34/40 = **85.0%** |
| T-4 | 39/50 = 78.0% | 37/46 = **80.4%** |
| T-3 | 38/52 = 73.1% | 37/47 = **78.7%** |

V2 improved the four-day retrospective hit rate at every checkpoint, but this is **not enough to replace V1**. The same dates were used to discover and evaluate the extra conditions, so overfit risk exists.

## Important supporting observations

- Raw selected-side money growth was nearly universal and did not discriminate well.
- Remaining the 1X2 money leader was also nearly universal and did not discriminate well.
- A single >=80% snapshot was weaker than sustained concentration in several checkpoint comparisons.
- A >2–3% adverse odds rise was associated with weaker results in this four-day sample, but the subgroup is small.
- The 1.40–2.50 V1 odds band stays unchanged. Earlier testing of 1.40–2.20 reduced both hit rate and ROI, so V2 must not narrow the base odds range.

## Forward test policy

From the next matchdays onward, V1 and V2 must be logged **side by side** on the same eligible universe.

For every checkpoint, record separately:
- V1 qualifiers / wins / losses / average odds / 1-unit ROI;
- V2 qualifiers / wins / losses / average odds / 1-unit ROI;
- V1-only cases removed by V2 and their results;
- whether removal came from `SHARE_PERSISTENCE_FAIL`, `ADVERSE_ODDS_FAIL`, or both;
- daily and cumulative results.

Do **not** silently replace V1 with V2. Keep both versions visible until enough new out-of-sample cases exist to compare stability, hit rate, ROI, and the cost of removed winners.

## Current interpretation

- **1X2 CONCENTRATION V1** = canonical/current research signal; unchanged.
- **1X2 CONCENTRATION V2** = separate experimental candidate.
- V2 currently looks stronger retrospectively, especially around T-5/T-6, but requires prospective/out-of-sample validation before promotion.
