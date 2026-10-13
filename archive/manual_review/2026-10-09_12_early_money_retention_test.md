# SXF Early Money Retention Test — 9–12 October 2026

Status: **RESEARCH_CANDIDATE / HISTORICAL_TEST REQUIRED**

Purpose: test whether previously identified strong early-money signals can be improved by checking whether the same team still retains meaningful 1X2 money concentration several hours before kickoff. T-6/T-5/T-4/T-3 are checkpoints, not separate signal definitions.

Scope:
- Match dates: 2026-10-09 through 2026-10-12
- Local kickoff window: 16:30–23:30 Europe/Istanbul
- Source: native SmartXFlow stored 1X2 history + stored FT results
- Leakage-safe: every checkpoint uses the latest snapshot available at or before that cutoff.

## Early signal families tested

- T-72: top-money team side, selected amount >= £5k, selected share >=50%
- T-60: top-money team side, selected amount >= £5k, selected share >=50%
- T-40: top-money team side, selected amount >= £10k, selected share >=50%
- T-24: top-money team side, selected amount >= £10k, selected share >=50%
- T-12: top-money team side, selected amount >= £1k, selected share >=80%

## Core finding: leader status and amount growth are not discriminators in this sample

For every tested early-signal family, the selected side remained the 1X2 money leader at all T-6/T-5/T-4/T-3 checkpoints, and its absolute amount had increased. Therefore:

- `still money leader` alone does not separate winners from losers;
- `money amount kept growing` alone does not separate winners from losers.

The useful extra variable is **share retention / concentration**.

## T-60 early signal — strongest clean retention improvement

Baseline: 11/13 wins = **84.6%**.

At T-5:
- share >=60%: 10/11 = **90.9%**
- share >=65%: 9/10 = **90.0%**
- share >=70%: 8/9 = **88.9%**
- share >=75%: 6/6 = **100%** (tiny subgroup)
- share had not fallen by more than 10 percentage points: 9/10 = **90.0%**

The >=60% rule removes two cases from the baseline set, one winner and one loser, improving hit rate from 84.6% to 90.9%.

Important counterexamples:
- Coventry–Newcastle: Newcastle T-60 share 75.0%, then T-40 54.9%, T-24 51.5%, T-6 55.5%, T-5 58.3%, T-4 59.4%, T-3 62.8%; Newcastle money amount kept growing but concentration collapsed. Result: Coventry 4–1 Newcastle. This is the clearest retention-failure example.
- Man Utd–Tottenham: Man Utd T-60 share 66.2%, T-5 share 72.2%; retention remained healthy but result was 1–1. Share retention cannot remove every failure.

## T-72 early signal

Baseline: 8/10 wins = **80.0%**.

Checkpoint performance:
- T-6 share >=60%: 7/8 = **87.5%**
- T-6 share >=65%: 6/7 = **85.7%**
- T-5 share >=60%: 7/8 = **87.5%**
- T-5 share >=65%: 6/7 = **85.7%**
- T-4 share >=60%: 7/8 = **87.5%**
- T-3 share >=65%: 6/7 = **85.7%**

A 60% retained-share floor improved the baseline modestly; pushing to 65/70 did not consistently improve further.

## T-40 early signal

Baseline: 10/13 wins = **76.9%**.

Checkpoint performance:
- T-6 share >=60%: 9/11 = **81.8%**
- T-5 share >=60%: 9/11 = **81.8%**
- T-4 share >=60%: 9/11 = **81.8%**
- T-3 share >=65%: 8/10 = **80.0%**
- share >=75% produced ~83–86% but only 6–7 cases.

Again, a modest absolute retained-share floor helped more consistently than a strict relative-drop rule.

## T-24 early signal

Baseline: 17/21 wins = **81.0%**.

Checkpoint performance:
- T-6 share >=60%: 16/19 = **84.2%**
- T-5 share >=60%: 16/19 = **84.2%**
- T-4 share >=65%: 15/18 = **83.3%**
- T-3 share >=75%: 11/12 = **91.7%** (small subgroup)

The broad 60–65% retention floor gives a modest improvement. The 75% subgroup is interesting but too small to hard-code.

## T-12 concentration signal

Baseline in this exact query: 33/43 wins = **76.7%**.

Because this family already starts with >=80% share, later share-retention filters added little:
- T-6 share >=80%: 27/35 = **77.1%**
- T-4 share >=75%: 31/40 = **77.5%**
- T-3 share >=75%: 29/37 = **78.4%**

Conclusion: share retention is more useful for the earlier T-72/T-60/T-40/T-24 money signals than for the already-concentrated T-12 family.

## Current research interpretation

1. **Absolute retained share is more useful than simple leader status or raw amount growth.**
2. A broad retained-share floor around **60%** is the most consistent four-day improvement across T-72/T-60/T-40/T-24.
3. Raising the floor to 65–70% does not consistently improve results and can remove good winners.
4. >=75% retention often looks excellent but sample sizes are too small and overfit risk is high.
5. Relative share-drop rules (`no more than -5pp/-10pp`) are less consistent than the absolute retained-share floor.
6. The strongest practical warning pattern is: **early strong money + selected amount keeps growing + selected share falls into the 50s**. Newcastle is the clearest observed failure.
7. This is not production-ready. The candidate should be expanded over a larger time-ordered sample before promotion.

## Candidate for next validation

**EARLY MONEY + SHARE RETENTION**

- detect the original early-money signal at T-72/T-60/T-40/T-24;
- at each later checkpoint (T-6/T-5/T-4/T-3), do not require the odds to shorten;
- require the same side to still carry meaningful concentration, with **>=60% share as the current broad research candidate**;
- separately flag any case where the side had a strong early share but later fell below 60% as a `RETENTION_BREAK` warning;
- keep >=75% as an exploratory premium subgroup only, not a hard rule.

## Proposed live strength tiers — research only

The current absolute-share tiers are:
- **<60%:** `RETENTION_BREAK` — downgrade / warning.
- **60–69.9%:** `EARLY MONEY — NORMAL`.
- **70–79.9%:** `EARLY MONEY — STRONG`.
- **>=80%:** `EARLY MONEY — HIGH CONCENTRATION`.

These are strength labels, not proven probability buckets.

## Clarification: checkpoint, not “evening”

Earlier wording used “evening checkpoint”. That is imprecise. The intended meaning is simply the later **T-6/T-5/T-4/T-3 checkpoint relative to kickoff**, regardless of clock time.

## Share trajectory test: raw percentage-point change alone is not enough

The proposed idea was to compare the selected side's share at the **first qualifying early signal** with its share at T-6/T-5/T-4/T-3 and score an increase positively, a decrease negatively, and no change neutrally.

This is intuitive, but the four-day sample shows that raw direction alone should **not** be the primary score:

- T-6: share DOWN 13/15 = **86.7%**; share UP 5/7 = **71.4%**
- T-5: share DOWN 14/16 = **87.5%**; share UP 4/6 = **66.7%**
- T-4: share DOWN 10/12 = **83.3%**; share UP 8/10 = **80.0%**
- T-3: share DOWN 11/13 = **84.6%**; share UP 7/9 = **77.8%**

Reason: many strong winners started with extremely high shares. A move from 98% to 86% is mathematically negative but still represents very strong retained concentration. Conversely, moving from 58% to 66% is positive trajectory but only moderate absolute concentration.

A practical ±2 percentage-point neutral zone was also tested. At T-5, for example:
- neutral ±2pp: 8/8 wins = **100%**
- +2 to +10pp: 2/4 = **50%**
- -10 to -2pp: 5/6 = **83.3%**
- <=-10pp: 3/4 = **75%**

These groups are small, but they reinforce that raw `share up = automatically better` is not supported yet.

## Better trajectory model: concentration-band transition

Instead of scoring every percentage-point move, track whether the selected side stays in, rises into, or falls out of a concentration band:

- Band 0: <60%
- Band 1: 60–69.9%
- Band 2: 70–79.9%
- Band 3: >=80%

Using the **first qualifying early signal** as the starting band, then comparing to the later checkpoint:

| Checkpoint | Band down | Same band | Band up |
|---|---:|---:|---:|
| T-6 | 3/4 = 75.0% | 13/15 = **86.7%** | 2/3 = 66.7% |
| T-5 | 2/3 = 66.7% | 13/15 = **86.7%** | 3/4 = 75.0% |
| T-4 | 3/5 = 60.0% | 12/13 = **92.3%** | 3/4 = 75.0% |
| T-3 | 3/5 = 60.0% | 11/12 = **91.7%** | 4/5 = 80.0% |

This is more promising than raw percentage-point direction. The strongest observed state is **staying in the same concentration band**, especially by T-4/T-3. A band drop is the clearest negative transition. A band rise is positive conceptually, but in this tiny sample it did not outperform stable high concentration because many band-up cases started from lower shares.

### Current candidate scoring logic

Use **absolute current band as the primary score** and **band transition as the modifier**:

- current <60%: strong negative / `RETENTION_BREAK`
- current 60–69.9%: normal
- current 70–79.9%: strong
- current >=80%: high concentration
- band down since first early signal: subtract confidence
- same band: neutral-to-positive confirmation
- band up: add a modest positive modifier, but do not automatically rank it above a side that has stayed >=80% throughout

Example:
- Betis 98% -> 86%: raw delta is negative, but it remains in the >=80% band, so it should remain a high-concentration signal rather than be penalized simply for falling 12pp.
- Newcastle 75% -> 55%: it drops from the 70–79.9% band to <60%, so this is a major negative transition / retention break.

Next test: combine this retention state with opponent/draw-side money acceleration and compare winners vs failures, then test over a larger archive.