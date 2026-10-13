# SXF Four-Day Validation — 9–12 October 2026

Status: **RESEARCH_CANDIDATE / HISTORICAL_TEST REQUIRED**

Scope:
- Match dates: 2026-10-09 through 2026-10-12
- Local kickoff window: 16:30–23:30 Europe/Istanbul
- Source: native SmartXFlow stored prematch histories + stored FT results
- 12 October finalized with **106/106 FT**
- Leakage-safe checkpoints: T-6, T-5, T-4, T-3

## 12 October final validation

### 1X2 Concentration
Condition at checkpoint:
- top-money 1X2 selection is team side 1 or 2
- amount >= £1,000
- share >=80%
- odds 1.40–2.50

| Checkpoint | Wins / Sample | Hit | Avg odds | ROI |
|---|---:|---:|---:|---:|
| T-6 | 5/6 | 83.3% | 1.92 | +57.5% |
| T-5 | 7/8 | 87.5% | 1.81 | +55.1% |
| T-4 | 6/7 | 85.7% | 1.71 | +41.7% |
| T-3 | 6/8 | 75.0% | 1.76 | +24.0% |

Persistent 12 October examples: Atalanta, Oviedo, Goztepe, CD Gualberto Villarroel and Pyramids won. Fortaleza drew 2-2 and was the main persistent miss; Mohun Bagan also failed at T-3.

### Heavy 1X2
Condition:
- top-money team side
- amount >=£10,000
- share >=80%

| Checkpoint | Wins / Sample |
|---|---:|
| T-6 | 3/3 |
| T-5 | 3/3 |
| T-4 | 3/3 |
| T-3 | 3/4 |

The late T-3 miss was PAOK, which lost 1-3.

A research refinement worth wider testing is Heavy 1X2 plus odds 1.40–2.50. Across 9–12 pooled:
- T-6: 6/7 = 85.7%
- T-5: 7/8 = 87.5%
- T-4: 6/6 = 100%
- T-3: 6/7 = 85.7%
Small sample; do not hard-code.

## 9–12 pooled operational 1X2

### Concentration 1X2
| Checkpoint | Wins / Sample | Hit | Avg odds | ROI |
|---|---:|---:|---:|---:|
| T-6 | 31/39 | 79.5% | 1.78 | +40.9% |
| T-5 | 38/48 | 79.2% | 1.77 | +38.8% |
| T-4 | 39/50 | 78.0% | 1.74 | +34.3% |
| T-3 | 38/52 | 73.1% | 1.75 | +26.3% |

### Heavy 1X2
| Checkpoint | Wins / Sample | Hit | Avg odds | ROI |
|---|---:|---:|---:|---:|
| T-6 | 14/16 | 87.5% | 1.54 | +35.7% |
| T-5 | 16/19 | 84.2% | 1.51 | +29.9% |
| T-4 | 16/18 | 88.9% | 1.52 | +37.1% |
| T-3 | 17/22 | 77.3% | 1.50 | +18.5% |

## Retrospective final-state filters after adding 12 October
These remain diagnostics, not operational early inputs.
- Strong 1X2 final-state: **36/42 = 85.7%**
- Premium 1X2 final-state: **20/22 = 90.9%**

Major 12 October counterexample: Coventry–Newcastle.
- Newcastle T-6: odds 2.22, amount ~£123k
- final: odds 2.06, amount ~£827k, share 75.8%
- result: Coventry 4-1 Newcastle

## Early-money families

| Early signal | Wins / Sample | Hit | Avg odds | ROI |
|---|---:|---:|---:|---:|
| T-72 top-money team >=£5k, share >=50% | 8/10 | 80.0% | 1.84 | +43.6% |
| T-60 top-money team >=£5k, share >=50% | 11/13 | 84.6% | 1.77 | +45.9% |
| T-40 top-money team >=£10k, share >=50% | 10/13 | 76.9% | 1.89 | +46.6% |
| T-24 top-money team >=£10k, share >=50% | 17/21 | 81.0% | 1.73 | +39.5% |
| T-12 top-money team >=£1k, share >=80% | 34/44 | 77.3% | 1.57 | +22.3% |

12 October contributions:
- T-72: Newcastle fail
- T-60: Atalanta win, Newcastle fail
- T-40: Newcastle fail
- T-24: Atalanta win, Newcastle fail
- T-12: Atalanta, Goztepe, Elfsborg, Shamrock won; PAOK failed

### De-duplicated early-lock view
For T-72/T-60/T-40/T-24, keeping only the earliest qualifying signal per physical match:
- **18/22 wins = 81.8%**

Known failures:
- Dortmund–Werder 2-2
- West Ham–QPR 1-1
- Man Utd–Tottenham 1-1
- Coventry–Newcastle 4-1

### Early signal checkpoint interpretation
Newcastle showed that amount growth + shorter odds can still fail if concentration changes materially:
- T-72 share 72.7%
- T-60 share 75.0%
- T-6 share 55.5%
- T-3 share 62.8%
while amount grew from ~£9.6k to ~£204k and odds shortened 2.26 -> 2.18.

Atalanta retained >80% concentration and won.

Pooled checkpoint research for de-duplicated early locks:
- T-6 share >=60%: 16/19 = 84.2%
- T-3 share >=80%: 9/10 = 90.0%
- early share drop <=10pp by T-6: 15/18 = 83.3%
- early share drop >10pp by T-6: 3/4 = 75.0%
These are warning/retention features, not hard filters yet.

## Surprise-team family — odds 2.90–4.49 + >=50% team money

### Final-state pooled 9–12
- 41 cases
- 29 non-losses = **70.7%**
- 13 outright wins
- 12 October: 4 cases, 3 non-losses

### Leakage-safe checkpoint view
| Checkpoint | Non-losses / Sample | Non-loss rate |
|---|---:|---:|
| T-6 | 23/32 | 71.9% |
| T-5 | 27/38 | 71.1% |
| T-4 | 27/45 | 60.0% |
| T-3 | 30/46 | 65.2% |

T-6/T-5 remain the cleaner checkpoints.

## Over 2.5 filters after 12 October

### Stable Over 2.5
Condition:
- Over amount >=£1,500
- Over share >=65%
- Over odds 1.40–1.80

| Checkpoint | Wins / Sample | Hit | Avg odds | ROI |
|---|---:|---:|---:|---:|
| T-6 | 14/18 | 77.8% | 1.58 | +23.4% |
| T-5 | 15/20 | 75.0% | 1.59 | +19.7% |
| T-4 | 14/19 | 73.7% | 1.58 | +16.9% |
| T-3 | 16/23 | 69.6% | 1.60 | +11.3% |

On 12 October Atalanta–Venezia passed T-6/T-5/T-4/T-3 and won Over 2.5. Malmö–Kalmar entered at T-3 and failed 1-0.

### Premium Over 2.5
Condition:
- Over amount >=£2,500
- Over share >=75%
- Over odds 1.40–1.80

| Checkpoint | Wins / Sample | Hit | Avg odds | ROI |
|---|---:|---:|---:|---:|
| T-6 | 7/10 | 70.0% | 1.59 | +12.3% |
| T-5 | 9/11 | 81.8% | 1.61 | +32.2% |
| T-4 | 11/13 | 84.6% | 1.60 | +35.5% |
| T-3 | 12/15 | 80.0% | 1.62 | +29.1% |

12 October added a T-3 Premium failure: Malmö–Kalmar 1-0. Premium Over remains strongest around T-5/T-4 in this tiny sample.

## BTTS Yes filter after 12 October
Condition:
- BTTS Yes amount >=£750
- Yes share >=60%
- Yes odds 1.60–1.90

| Checkpoint | Wins / Sample | Hit | Avg odds | ROI |
|---|---:|---:|---:|---:|
| T-6 | 10/12 | 83.3% | 1.71 | +42.9% |
| T-5 | 14/17 | 82.4% | 1.70 | +40.4% |
| T-4 | 13/17 | 76.5% | 1.69 | +29.6% |
| T-3 | 14/18 | 77.8% | 1.68 | +31.1% |

12 October itself was perfect on observed qualifiers:
- T-6 2/2
- T-5 3/3
- T-4 2/2
- T-3 2/2
Examples included Coventry–Newcastle 4-1, Shamrock–Bohemians 2-1, Levante–Sevilla 3-3.

## Broad final top-money 1X2 after adding 12 October
Final top-money 1X2 selection:
- ALL: 354/681 = 52.0%
- >=£2.5k: 155/271 = 57.2%
- >=£5k: 107/185 = 57.8%
- >=£10k: 81/125 = 64.8%

12 October alone weakened the previous clean monotonic money-size pattern:
- >=£2.5k: 20/35
- >=£5k: 14/27
- >=£10k: 8/15
Therefore absolute final money alone should carry less weight than concentration, timing, price and market-specific filters.

## Current research hierarchy after four days
1. 1X2 Concentration is still the most stable operational family; T-6/T-5 strongest.
2. Heavy 1X2 remains strong, but late T-3 signals degrade and very short favorites can fail.
3. Early-lock signals remain useful, especially when concentration persists into the evening checkpoint. Treat share dilution as a warning feature.
4. Surprise-team 2.90–4.49 + >=50% remains around 70% non-loss and deserves continued tracking.
5. Stable Over remains >70% through T-4, falling just below 70 at T-3 after 12 October.
6. Premium Over remains promising at T-5/T-4 but sample is small and Malmö provides an important counterexample.
7. BTTS Yes filter strengthened materially after 12 October and is now a serious research candidate.
8. Final absolute-money thresholds alone weakened after 12 October; do not use them as a standalone engine.

All percentages are historical on four days only. Wider time-ordered testing is mandatory before production promotion.