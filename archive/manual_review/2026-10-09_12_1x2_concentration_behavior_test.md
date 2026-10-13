# SXF 1X2 Concentration Behavior Test — 9–12 October 2026

Status: **RESEARCH_CANDIDATE / HISTORICAL_TEST REQUIRED**

Purpose: test whether the existing leakage-safe 1X2 Concentration signal can be strengthened by behavior before the observation checkpoint instead of narrowing the odds band.

Base signal at T-6/T-5/T-4/T-3 checkpoint:
- current top-money 1X2 selection is a TEAM side (HOME/AWAY)
- selected amount >= £1,000
- selected share >= 80%
- selected odds 1.40–2.50

Scope:
- Match dates: 2026-10-09 through 2026-10-12
- Local kickoff window: 16:30–23:30 Europe/Istanbul
- Source: native SmartXFlow stored 1X2 history + stored FT results
- Leakage-safe: all behavior features use only snapshots at or before each checkpoint.

## Base performance

- T-6: 31/39 = 79.5%
- T-5: 38/48 = 79.2%
- T-4: 39/50 = 78.0%
- T-3: 38/52 = 73.1%

## Money growth and leader persistence

These do not discriminate in this four-day sample:
- selected money amount grew in virtually every concentration case;
- selected side remained the money leader in virtually every case.

Therefore neither `amount still growing` nor `still leader` should be added as a standalone strengthening rule.

## Concentration persistence

Tested whether the same selected side had maintained elevated share during the previous three hours.

Minimum selected share across the prior 3 hourly checkpoints >=70%:
- T-6: 30/36 = 83.3%
- T-5: 37/44 = 84.1%
- T-4: 38/47 = 80.9%
- T-3: 37/49 = 75.5%

Minimum selected share across the prior 3 hourly checkpoints >=75%:
- T-6: 28/34 = 82.4%
- T-5: 33/39 = 84.6%
- T-4: 34/42 = 81.0%
- T-3: 33/44 = 75.0%

Strict >=80% persistence did not consistently outperform the 70–75 floor and removes more cases.

Interpretation: **persistence matters modestly**, especially around T-6/T-5. A side that is 80%+ only at one isolated snapshot is weaker evidence than one that has stayed at least ~70–75% concentrated over the prior hours.

## Odds behavior over prior 3 hours

A materially adverse odds move is the clearest negative behavior found in this test.

If selected odds had risen by >2% over the prior 3 hours:
- T-6: 6/9 = 66.7%
- T-5: 5/8 = 62.5%
- T-4: 2/3 = 66.7%
- T-3: 1/3 = 33.3%

If selected odds had NOT risen by >2%:
- T-6: 25/30 = 83.3%
- T-5: 33/40 = 82.5%
- T-4: 37/47 = 78.7%
- T-3: 37/49 = 75.5%

For a stricter >3% adverse move, T-6 and T-5 were each 3/6 = 50.0% in this small sample.

Interpretation: do **not** require odds to shorten, but a sufficiently sharp adverse move against an otherwise concentrated side is a useful warning candidate.

## Combined research candidate

Current 1X2 Concentration signal +:
- same selected side's share never below 70% across the previous 3 hourly checkpoints;
- selected odds have NOT risen by more than 3% over those 3 hours.

Results:
- T-6: 27/32 = 84.4% (base 79.5%)
- T-5: 34/40 = 85.0% (base 79.2%)
- T-4: 37/46 = 80.4% (base 78.0%)
- T-3: 37/47 = 78.7% (base 73.1%)

Day breakdown shows improvement on most days but not uniformly. 10 October remains the weakest regime, especially at T-6. Therefore this is promising but not production-ready.

## Current interpretation

1. Do not narrow the 1.40–2.50 odds band; the 2.21–2.50 segment was useful in the four-day sample.
2. Raw money growth adds no discrimination because almost all qualifying cases keep growing.
3. Remaining money leader adds almost no discrimination.
4. **Concentration persistence** over the prior 2–3 hours is useful and should stay in research.
5. **Sharp adverse odds movement** (>~2–3% over prior 3 hours) is the strongest negative behavior candidate found so far.
6. The combined candidate (`prior-3h share floor >=70%` + `no >3% adverse odds move`) improves every checkpoint in the pooled four-day sample, but requires larger time-ordered validation before any promotion.

No production rule was changed by this test.
