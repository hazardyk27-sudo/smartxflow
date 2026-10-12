# SXF Operational Filter Research — 9–11 October 2026

Status: **RESEARCH_CANDIDATE / HISTORICAL_TEST REQUIRED**

Purpose: separate retrospective final-prematch findings from filters that are actually usable when SmartXFlow is scanned **3–6 hours before kickoff**.

Scope:
- Match dates: 2026-10-09, 2026-10-10, 2026-10-11
- Local kickoff window: 16:30–23:30 Europe/Istanbul
- Source: native SmartXFlow stored prematch history + stored FT results
- Operational cutoffs tested: T-6h, T-5h, T-4h (T-3h also inspected where noted)
- No snapshot after the tested cutoff is allowed into an operational feature.

## Critical distinction

The following previously liked filters are preserved because they are useful retrospective research findings, but they use final-prematch state and therefore must **NOT** be treated as operational T-4/T-5/T-6 rules:

### Retrospective FINAL-state filters — preserved, not operational

1. **Premium 1X2 (final-state)**
   - final top-money selection is a team side (1 or 2)
   - final-6h inflow >= £10k
   - odds shorten during the final 6h
   - final selection amount >= £20k
   - final share >= 60%
   - 18/19 wins = **94.7%** in the three-day sample

2. **Strong 1X2 (final-state)**
   - final top-money team side
   - final-6h inflow >= £10k
   - odds shorten during the final 6h
   - final share >= 60%
   - 33/38 wins = **86.8%** in the three-day sample

3. **Surprise-team final-state research band**
   - team side only, not Draw
   - odds 2.90–4.49
   - >=50% money share
   - 26/37 non-losses = **70.3%**

4. **O/U final-state money filter**
   - top-money O/U2.5 selection amount >= £1k
   - 98/160 wins = **61.3%**

These remain useful for understanding what a successful market eventually looked like, but they contain information unavailable 4–6 hours before kickoff. They must never be used to grade an operational early pick as if that later information had already existed.

---

# Leakage-safe operational research

## Snapshot coverage

For the 577 FT matches in scope:
- T-6h: 575 had a 1X2 snapshot, 575 O/U2.5, 557 BTTS
- T-5h: 576 had a 1X2 snapshot, 576 O/U2.5, 559 BTTS
- T-4h: 576 had a 1X2 snapshot, 576 O/U2.5, 559 BTTS

Operational features below use the latest stored snapshot at or before the stated cutoff and only earlier history.

---

## Operational Candidate A — concentrated 1X2 money, usable 4–6 hours before kickoff

Condition at the scan time:
- the highest-money 1X2 selection must be a **team side (1 or 2)**, not Draw;
- current selection amount >= **£1,000**;
- current selection share >= **80%**;
- current odds between **1.40 and 2.50**.

Results:

| Cutoff | Wins / Sample | Hit rate |
|---|---:|---:|
| T-6h | 26/33 | **78.8%** |
| T-5h | 31/40 | **77.5%** |
| T-4h | 33/43 | **76.7%** |

Across the three cutoff observations this was 90/116 = 77.6%, but those 116 observations are **not independent** because the same match can appear at multiple horizons.

Approximate average odds were around 1.7–1.8. This is currently the best balance found between usable lead time, hit rate, sample size and price.

Day-level variation remained material: 10 October was weaker than 9 and 11 October, so this is still a research candidate rather than a production rule.

**Research status:** strong candidate for wider historical testing.

---

## Operational Candidate B — very high concentration + meaningful money

Condition at scan time:
- highest-money 1X2 selection is a team side;
- current amount >= **£10,000**;
- current share >= **80%**.

Results:

| Cutoff | Wins / Sample | Hit rate |
|---|---:|---:|
| T-6h | 11/13 | **84.6%** |
| T-5h | 13/16 | **81.3%** |
| T-4h | 13/15 | **86.7%** |

This is a higher-hit-rate subgroup, but the sample is smaller and the average odds were short (roughly ~1.4 in this sample). It should therefore be evaluated on ROI/value as well as hit rate before promotion.

Important instability: the 9 October daily subgroup was weak while 10–11 October were excellent. Do not promote from three days.

**Research status:** high-hit-rate candidate, smaller sample / short-price caution.

---

## Prior-window money + price movement at an early cutoff

A key correction to the retrospective 94.7% result: when the same concept is frozen **4–6 hours before kickoff**, it is much weaker and horizon-dependent.

Example condition:
- current top-money team side;
- current amount >= £20k;
- current share >=60%;
- in the six hours *before the scan cutoff*, >=£10k new money arrived;
- odds shortened over that same pre-cutoff six-hour window.

Results:
- T-6h: 3/5 = **60.0%**
- T-5h: 5/8 = **62.5%**
- T-4h: 7/8 = **87.5%**

Therefore the retrospective final-six-hour pattern is **not interchangeable** with a T-6/T-5 scan. The market becomes more informative closer to kickoff. A universal 4–6h rule cannot use the 94.7% figure.

**Research implication:** price/money momentum must be calibrated by time-to-kickoff rather than one fixed threshold.

---

## Surprise-team operational test — 2.90–4.49 odds

Base condition at the tested cutoff:
- team side only;
- current odds 2.90–4.49;
- current money share >=50%.

Non-loss results:

| Cutoff | Non-losses / Sample | Non-loss rate |
|---|---:|---:|
| T-6h | 20/28 | **71.4%** |
| T-5h | 21/32 | **65.6%** |
| T-4h | 20/35 | **57.1%** |
| T-3h | 24/37 | **64.9%** |

The final-state version was 70.3% non-loss, but that final figure cannot be assumed at T-4/T-5/T-6.

Some horizon-specific refinements looked interesting:
- T-5h with share >=70%: 14/17 non-loss = **82.4%**;
- T-4h with share >=65% and amount >=£100: 10/14 non-loss = **71.4%**.

However these are small, horizon-specific subgroups and are at high risk of three-day overfitting. Do not hard-code them yet.

**Operational takeaway:** keep 2.90–4.49 as a useful surprise-team research band, but the required share/amount threshold probably needs to be time-to-kickoff specific.

---

## O/U2.5 operational correction

The final-state O/U rule (`top-money O/U side amount >= £1k`) does **not** transfer well to a 4–6h scan:

| Cutoff | Wins / Sample | Hit rate |
|---|---:|---:|
| T-6h | 25/51 | **49.0%** |
| T-5h | 30/59 | **50.8%** |
| T-4h | 34/68 | **50.0%** |

So the final 61.3% number should not be used operationally several hours before kickoff.

A tighter early O/U candidate emerged:
- top-money O/U2.5 selection;
- amount >=£2.5k;
- share >=70%;
- odds 1.40–1.90.

Across T-6/T-5/T-4 horizon-observations it was 31/43 = 72.1%, but day-level stability was poor: 9 October was weak while 10–11 October were strong. This is not robust enough yet for a live rule.

**Research status:** O/U early signal remains unresolved; do not elevate yet.

---

# Current operational hierarchy for further testing

The best leakage-safe candidates from this three-day sample are:

1. **1X2 Concentration Candidate** — at T-4/T-5/T-6: top-money team, amount >=£1k, share >=80%, odds 1.40–2.50. Approximately 77% hit at each tested horizon with reasonable sample sizes.
2. **1X2 Heavy Concentration Candidate** — at T-4/T-5/T-6: top-money team, amount >=£10k, share >=80%. Approximately 81–87% hit, but small sample and short average odds.
3. **Surprise-team family** — odds 2.90–4.49 remains promising, but the best share threshold appears horizon-dependent; freeze and test separately at T-6/T-5/T-4.
4. **O/U early family** — no stable rule yet; the final-state £1k rule should not be used 4–6h early.
5. **BTTS** — remains low priority until a clearly stable early filter appears.

## Mandatory methodology going forward

For evening predictions made several hours before kickoff:
- choose an explicit cutoff (`prediction_at` / T-minus horizon);
- use only snapshots with `observed_at <= prediction_at`;
- never use final-prematch amount, share, odds, alarm or movement to justify an earlier prediction;
- movement features may use only history that existed before the cutoff;
- evaluate T-6, T-5, T-4 and T-3 separately before combining them;
- report sample size, hit rate, ROI, average odds, daily stability and failure cases;
- final-prematch retrospective patterns may be retained as research diagnostics but not as PRE inputs.

Next validation target: expand these exact cutoff-frozen candidates over a substantially larger time-ordered historical sample before any production promotion.
