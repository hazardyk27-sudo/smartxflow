# SXF Early-Signal Checkpoints + Over 2.5 Filters — 9–11 October 2026

Status: **RESEARCH_CANDIDATE / HISTORICAL_TEST REQUIRED**

Scope:
- Match dates: 2026-10-09, 2026-10-10, 2026-10-11
- Local kickoff window: 16:30–23:30 Europe/Istanbul
- Source: native SmartXFlow stored prematch history + stored FT results

## Critical methodology correction

**T-6 / T-5 / T-4 / T-3 are NOT separate filters by themselves.**

They are observation checkpoints used to answer: **if a signal had already appeared much earlier (for example T-72, T-60, T-40, T-24 or T-12), what did that same signal look like when SmartXFlow was scanned 6, 5, 4 or 3 hours before kickoff? Could the earlier signal still be recognized at the time an evening prediction would actually be made?**

Do not turn `T-6` or `T-3` into a feature merely because a retrospective table is reported at that checkpoint. The signal definition and the observation checkpoint are separate concepts.

---

## Early 1X2 signal families and how they look later

Early cohort definitions used in this three-day exploratory sample:
- T-72: top-money team side with at least **£5k** and at least **50%** share
- T-60: top-money team side with at least **£5k** and at least **50%** share
- T-40: top-money team side with at least **£10k** and at least **50%** share
- T-24: top-money team side with at least **£10k** and at least **50%** share
- T-12: top-money team side with at least **£1k** and at least **80%** share

These are research cohorts, not production thresholds.

### Money growth and odds evolution

| Early signal | Sample | Wins | Early avg odds | T-6 avg odds | T-3 avg odds | Avg new money by T-6 | Avg new money by T-3 |
|---|---:|---:|---:|---:|---:|---:|---:|
| T-72 >=£5k | 9 | 8/9 = 88.9% | 1.79 | 1.80 | 1.81 | +£94k | +£131k |
| T-60 >=£5k | 11 | 10/11 = 90.9% | 1.74 | 1.75 | 1.76 | +£81k | +£115k |
| T-40 >=£10k | 12 | 10/12 = 83.3% | 1.85 | 1.86 | 1.87 | +£90k | +£142k |
| T-24 >=£10k | 19 | 16/19 = 84.2% | 1.70 | 1.73 | 1.74 | +£57k | +£98k |
| T-12 >=£1k + >=80% | 38 with usable odds | 29/38 = 76.3% | 1.55 | 1.55 | 1.54 | +£11k | +£23k |

Note: the earlier money-only T-12 count was 39; the odds-evolution recomputation has 38 cases because one case did not have a usable selected-side odds observation for the complete odds comparison.

### Odds direction from the early signal to later checkpoints

Direction uses a +/-0.5% band: DOWN if later odds are below 99.5% of early odds, UP if above 100.5%, otherwise FLAT.

| Early signal | By T-6: DOWN / FLAT / UP | By T-3: DOWN / FLAT / UP |
|---|---:|---:|
| T-72 >=£5k | 4 / 1 / 4 | 1 / 2 / 6 |
| T-60 >=£5k | 4 / 2 / 5 | 2 / 0 / 9 |
| T-40 >=£10k | 5 / 1 / 6 | 4 / 2 / 6 |
| T-24 >=£10k | 4 / 2 / 13 | 6 / 0 / 13 |
| T-12 >=£1k + >=80% | 18 / 9 / 11 | 19 / 5 / 14 |

### Important interpretation

A strong early-money signal did **not** require the odds to keep shortening all the way to T-6 or T-3. In several early cohorts, odds were actually higher later while the team still won at a high rate.

Examples from the aggregate direction split:
- T-60 cohort at T-3: odds UP cases were **8/9 wins = 88.9%**.
- T-24 cohort at T-3: odds UP cases were **11/13 wins = 84.6%**.
- T-12 cohort at T-3: odds UP cases were **12/14 wins = 85.7%**.

Therefore do **not** cancel an already-identified strong early-money signal simply because its odds are mildly higher at T-6/T-3. At those checkpoints the operational question is primarily whether the same side is still strongly supported / remains relevant and whether the early-money thesis has materially broken, not whether odds must be lower than the original early price.

The three-day sample showed that these strong early cohorts retained the same selected side into the T-6/T-3 observation window; this persistence is promising but must be verified over a much larger history.

---

# Over 2.5 filters to preserve

The two filters below were explicitly selected for continued research. They are **single filter definitions evaluated at multiple scan checkpoints**; T-6/T-5/T-4/T-3 are not different rules.

## OVER 2.5 — STABLE MONEY FILTER

At the current scan snapshot:
- selection is **Over 2.5**;
- Over amount >= **£1,500**;
- Over money share >= **65%**;
- Over odds between **1.40 and 1.80**.

Three-day results when the same filter is evaluated at different available scan checkpoints:

| Observation checkpoint | Wins / Sample | Hit rate | Approx ROI |
|---|---:|---:|---:|
| T-6 | 13/17 | **76.5%** | +21.5% |
| T-5 | 14/19 | **73.7%** | +17.7% |
| T-4 | 13/18 | **72.2%** | +14.7% |
| T-3 | 15/21 | **71.4%** | +14.5% |

**Research interpretation:** this is currently the more stable Over candidate because it remains above 70% at every tested checkpoint and has more observations than the premium subgroup.

**Status:** preserve as a high-priority research candidate; wider time-ordered backtest required before production use.

---

## PREMIUM OVER 2.5

At the current scan snapshot:
- selection is **Over 2.5**;
- Over amount >= **£2,500**;
- Over money share >= **75%**;
- Over odds between **1.40 and 1.80**.

Three-day results:

| Observation checkpoint | Wins / Sample | Hit rate |
|---|---:|---:|
| T-6 | 7/10 | **70.0%** |
| T-5 | 9/11 | **81.8%** |
| T-4 | 11/13 | **84.6%** |
| T-3 | 12/14 | **85.7%** |

**Important stability warning:** 9 October was materially weaker than 10–11 October, so the impressive T-5 to T-3 percentages may be regime/day dependent. Do not promote this to production from three days alone.

**Status:** preserve as a premium/high-concentration Over research candidate and specifically test day-level stability on a larger history.

---

## Research rules going forward

- Early-signal time (`signal_at`) and later observation time (`prediction_scan_at`) must be stored separately.
- A T-72/T-60/T-40/T-24/T-12 signal may be recognized again at T-6/T-5/T-4/T-3, but later data must never be used to claim the signal existed earlier.
- Do not require early 1X2 odds to shorten continuously; track odds path, but treat persistence and money growth as separate dimensions.
- For Over filters, evaluate the exact same rule at each scan checkpoint rather than inventing a separate T-6 or T-3 rule.
- Always report sample size, daily breakdown, odds, hit rate, ROI and failure cases before promotion.
