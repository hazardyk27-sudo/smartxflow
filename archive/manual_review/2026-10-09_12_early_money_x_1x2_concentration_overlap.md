# SXF Early Money × 1X2 Concentration overlap — 9–12 October 2026

Status: **RESEARCH_CANDIDATE / HISTORICAL_TEST REQUIRED**

Purpose: test whether an earlier 1X2 Early Money signal gains additional predictive value when the later 1X2 Concentration model points to the same team at T-6/T-5/T-4/T-3.

Scope:
- Match dates: 2026-10-09 through 2026-10-12
- Local kickoff window: 16:30–23:30 Europe/Istanbul
- Source: native SmartXFlow stored 1X2 history + stored FT results
- Leakage-safe: every early/checkpoint snapshot is latest available at or before the relevant cutoff

## Definitions

Early Money: first qualifying signal among:
- T-72: top-money team, amount >= £5k, share >=50%
- T-60: top-money team, amount >= £5k, share >=50%
- T-40: top-money team, amount >= £10k, share >=50%
- T-24: top-money team, amount >= £10k, share >=50%

1X2 Concentration V1 at checkpoint:
- top-money side is a TEAM side
- amount >= £1,000
- share >=80%
- odds 1.40–2.50

Overlap requires the Early Money selected team and the Concentration selected team to be the same side.

Current Early Money retention rule (<55% at later checkpoints => RETENTION_BREAK) was checked separately; it did not remove any overlap cases in this sample.

## Results

| Checkpoint | Overlap n | Wins | Hit rate | Avg odds | ROI |
|---|---:|---:|---:|---:|---:|
| T-6 | 5 | 4 | 80.0% | 1.76 | +45.4% |
| T-5 | 5 | 4 | 80.0% | 1.76 | +46.2% |
| T-4 | 4 | 4 | 100.0% | 1.82 | +82.3% |
| T-3 | 4 | 4 | 100.0% | 1.82 | +82.3% |

Important: the same matches repeat across checkpoints, so T-4/T-3 observations are not independent samples. There are only **5 unique overlap matches** in the four-day sample, with **4/5 wins = 80.0%** overall.

Unique overlap matches:
- West Ham – QPR: Early Money West Ham, later Concentration West Ham; result 1–1 — FAIL
- AD Ceuta FC – Sabadell: Early Money Sabadell, later Concentration Sabadell; result 1–2 — WIN
- Betis – Osasuna: Early Money Betis, later Concentration Betis; result 5–2 — WIN
- Real Sociedad – Deportivo: Early Money Real Sociedad, later Concentration Real Sociedad; result 3–2 — WIN
- Atalanta – Venezia: Early Money Atalanta, later Concentration Atalanta; result 3–1 — WIN

West Ham qualified at T-6/T-5 but no longer qualified for Concentration at T-4/T-3, which explains the apparent 4/4 later-checkpoint result. This is not evidence that waiting until T-4/T-3 guarantees better performance; it is one failing case dropping out of a very small sample.

## Comparison with standalone models

Standalone 1X2 Concentration V1 in the same four-day scope:
- T-6: 31/39 = 79.5%
- T-5: 38/48 = 79.2%
- T-4: 39/50 = 78.0%
- T-3: 38/52 = 73.1%

Overlap:
- T-6: 4/5 = 80.0%
- T-5: 4/5 = 80.0%
- T-4: 4/4 = 100.0%
- T-3: 4/4 = 100.0%

At T-6/T-5, overlap is essentially no better than standalone Concentration. T-4/T-3 looks much stronger but the sample collapses to four matches and is dominated by survivorship of the West Ham failure dropping out.

The deduplicated first-Early-Money sample previously measured 18/22 = 81.8% wins. Therefore 4/5 = 80.0% does not improve on Early Money either in this tiny historical sample.

## V2 cross-check

Applying 1X2 Concentration V2 requirements to the overlap set did not change the sample:
- T-6: 4/5 = 80.0%
- T-5: 4/5 = 80.0%
- T-4: 4/4 = 100.0%
- T-3: 4/4 = 100.0%

All five V1 overlap cases already satisfied the V2 persistence/adverse-odds conditions at the checkpoints where they overlapped.

## Current interpretation

**Do not promote Early Money + Concentration overlap as a stronger signal yet.**

The logic is attractive, but the observed evidence is too small and does not improve the hit rate at the operationally important T-6/T-5 checkpoints. Treat it as a separate research tag only:

`EARLY_MONEY_X_CONCENTRATION`

Track prospectively on new days and compare against:
1. Early Money alone,
2. 1X2 Concentration V1 alone,
3. 1X2 Concentration V2 alone,
4. overlap same-team cases.

Required next evidence: larger time-ordered sample of unique matches, with hit rate, ROI, excluded winners, and checkpoint stability reported separately.
