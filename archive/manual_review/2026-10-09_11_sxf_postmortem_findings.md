# SXF Postmatch Findings — 9–11 October 2026

Status: **RESEARCH_CANDIDATE / HISTORICAL_TEST REQUIRED**

Scope:
- Match dates: 2026-10-09, 2026-10-10, 2026-10-11
- Local kickoff window: 16:30–23:30 Europe/Istanbul
- Source: native SmartXFlow stored prematch data + stored FT results
- Native markets reviewed: 1X2, O/U 2.5, BTTS
- This document records postmatch research observations only. It does **not** promote production Predictor rules.

## Executive findings

### 1. Absolute 1X2 money size is a useful first-stage filter

Across the three-day sample, the final top-money 1X2 side improved as absolute money increased:

| Filter | Sample | Wins | Hit rate |
|---|---:|---:|---:|
| All top-money 1X2 sides | 575 | 298 | 51.8% |
| Top-money amount >= £2.5k | 226 | 132 | 58.4% |
| Top-money amount >= £5k | 148 | 92 | 62.2% |
| Top-money amount >= £10k | 104 | 72 | 69.2% |

**Research implication:** high absolute money deserves more weight, but it must not be used alone. League/match popularity should later normalize what counts as “large”.

---

### 2. Early meaningful money was one of the strongest repeating observations

Combined three-day results for top-money sides observed well before kickoff:

| Prematch horizon | Filter | Wins / Sample | Hit rate |
|---|---|---:|---:|
| T-72h | amount >= £2.5k | 13/17 | 76.5% |
| T-72h | amount >= £5k | 9/11 | 81.8% |
| T-48h | amount >= £5k | 15/19 | 78.9% |
| T-24h | amount >= £10k | 16/20 | 80.0% |

Strong examples included Betis, Manchester City and Real Sociedad on 11 October.

**Important limitation:** Dortmund and West Ham on 9 October received very large early money and still drew. Therefore the useful concept is not “early money = bet”; it is **early money that is abnormal relative to that league/team/match’s normal activity**.

**Candidate:** build a league/popularity-normalized early-money anomaly feature rather than fixed absolute thresholds alone.

---

### 3. Late money is stronger when the price confirms it

The most useful late-window pattern was substantial new money combined with price shortening in the same direction.

Three-day combined result for the final hour with >= £2.5k new money:

| Final-hour price direction | Wins / Sample | Hit rate |
|---|---:|---:|
| Odds DOWN | 54/82 | 65.9% |
| Odds FLAT | 18/30 | 60.0% |
| Odds UP | 31/61 | 50.8% |

Additional combined observations:
- Last 3h, >= £5k new money + odds DOWN: **45/66 = 68.2%**
- Last 6h, >= £5k new money + odds DOWN: **49/69 = 71.0%**

**Research implication:** the best late confirmation seen in this sample is not merely “money arrived”, but **money continued to arrive while price shortened**.

---

### 4. Long-horizon odds rising is NOT an automatic negative signal

Several high-money winners had higher final odds than their first recorded odds. Examples:
- Lens: 2.36 -> 2.70, won
- Sporting Lisbon at Braga: 2.12 -> 2.56, won
- Marseille at Troyes: 1.96 -> 2.16, won
- Almeria: 1.68 -> 1.82, won
- Atletico MG: 2.10 -> 2.58, won

Therefore:
- Do **not** reject a side simply because first-to-final odds rose.
- Price reaction becomes more informative in the **late 3–6h / 1h windows**, especially when read against new money arriving in that same window.

---

### 5. High money share alone is insufficient

Very high shares produced both winners and failures. Examples of failures despite heavy concentration included Dortmund, Juventus, Milan, Union SG and Roda.

**Research implication:** money share should be a context feature, not a standalone trigger. Absolute amount, timing, price behavior and league norm matter more when combined.

---

### 6. The “3.00+ team with >50% money” rule was weak as a standalone filter

Across the three days, the 3.00+ Home/Away side with >=50% money had only about **24/43 = 55.8% non-loss** in the pooled sample.

This is not strong enough to be a standalone selection rule.

**Candidate:** only retain this as a secondary anomaly flag when supported by one or more of:
- abnormal absolute/relative money,
- early money anomaly,
- late price confirmation,
- alarm combination,
- market-specific contextual evidence.

---

### 7. Single alarm types were unstable; alarm combinations matter more

Three-day pooled 1X2 single-alarm results:

| Alarm | Wins / Sample | Hit rate |
|---|---:|---:|
| Big Money | 21/37 | 56.8% |
| MIM | 73/136 | 53.7% |
| Sharp | 9/17 | 52.9% |
| Volume Shock | 31/62 | 50.0% |

Sharp looked excellent on 9–10 October but fell sharply on 11 October. Volume Shock alone was near coin-flip.

**Research implication:** no single existing alarm should be treated as a high-confidence betting rule from this sample.

**Promising research candidate:** MIM + Volume Shock on the same selection repeatedly performed better than either single alarm in daily samples, but the sample is still small and must be deduplicated/retested over a much larger history before any promotion.

---

### 8. Three-way Big Money is a “special match” flag, not a draw prediction

Observed examples:
- Malaga – Espanyol: Big Money on 1, X and 2; result 1-1.
- Liverpool – Manchester City: Big Money on 1, X and 2; result 0-3.

Therefore:
- All three 1X2 outcomes receiving large money should mark the match as **unusual / high-information / contested**.
- It must **not** be converted into “bet draw”.
- Direction should be chosen only if another side-specific structure clearly dominates (e.g. City’s early money + sustained price drop + late inflow).

---

### 9. O/U 2.5 money flow was more useful than BTTS over the three-day sample

Combined three-day top-money performance:
- O/U 2.5: **324/563 = 57.5%**
- BTTS: **279/554 = 50.4%**
- O/U 2.5 with >= £1k on the top-money selection: **91/151 = 60.3%**

**Research implication:** O/U 2.5 deserves more research weight than BTTS at this stage, but daily variance was large, so this remains a candidate rather than a production rule.

---

### 10. Betis-type “staircase decline” must be detected structurally, not by net drop or tick count

Betis – Osasuna was the canonical successful example:
- early substantial Betis money,
- money persisted and expanded,
- price established progressively lower levels,
- final large late inflow,
- final result 5-2.

A simple test based on “number of down ticks > number of up ticks” performed poorly in the 9 October review. Therefore a true staircase detector should model things such as:
- progressively lower plateaus,
- lower highs / lower accepted levels,
- retention at new lower price bands,
- money growth while those lower levels hold.

It should **not** equate noisy oscillation with a staircase move.

---

## Best combined pattern observed so far

The most promising multi-factor sequence from 9–11 October is:

1. meaningful money is already present well before kickoff;
2. the amount continues to grow rather than disappearing;
3. the size is abnormal for the league/team/match context;
4. another meaningful inflow appears in the final 3–6 hours;
5. the price in that late window shortens or at least does not materially reject the incoming money;
6. optional supporting evidence comes from a useful alarm combination or a confirming O/U market.

Betis and Manchester City on 11 October were the cleanest successful examples of this structure.

---

## Important failure examples to preserve

These cases prevent overfitting:
- Dortmund – Werder: enormous early/final Dortmund money, result draw.
- West Ham – QPR: major early/final West Ham money, result draw.
- Juventus at Cagliari: very large money and high share, result draw.
- AC Milan at Sassuolo: very large money and high share, result draw.
- Start – Ham-Kam: high money plus major price shortening, Start still lost 2-4.
- Roda – Jong PSV: strong Sharp/MIM-style movement and high concentration, result draw.

Any future model must be able to explain or at least identify risk in these counterexamples rather than fitting only successful cases.

---

## Candidate lifecycle

These findings are **not production rules**.

Recommended next state:

`CANDIDATE -> HISTORICAL_TEST`

Next validation should:
- expand from 3 days to a materially larger time-ordered sample;
- normalize money by league/match popularity;
- avoid hindsight leakage by freezing features at T-72/T-48/T-24/T-6/T-3/T-1;
- report hit rate, ROI, sample size, subgroup stability and drawdown;
- test combinations rather than single alarms;
- keep 1X2, O/U2.5 and BTTS results separate;
- explicitly test failure cases and regime changes.
