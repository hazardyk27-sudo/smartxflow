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
- at the later evening checkpoint, do not require the odds to shorten;
- require the same side to still carry meaningful concentration, with **>=60% share as the current broad research candidate**;
- separately flag any case where the side had a strong early share but later fell below 60% as a `RETENTION_BREAK` warning;
- keep >=75% as an exploratory premium subgroup only, not a hard rule.

## Proposed live strength tiers — research only

The user's proposed live interpretation is directionally sensible, but four-day evidence does **not** yet support a clean monotonic rule where every higher 10-point share band must have a higher win rate. The operational research tiers should therefore be treated as **strength labels**, not proven probability buckets:

- **<60%:** `RETENTION_BREAK` — downgrade / warning. This is the clearest negative state in the current sample.
- **60–69.9%:** `EARLY MONEY — NORMAL` — the early signal is still alive; broad retained-share filtering around 60% consistently improves the base groups.
- **70–79.9%:** `EARLY MONEY — STRONG` — reasonable strength upgrade, but four-day data does not consistently outperform the 60–69 band in every early family.
- **>=80%:** `EARLY MONEY — HIGH CONCENTRATION` — serious alert / highest confidence label for monitoring, but the sample is still small and must not be assigned a guaranteed higher probability yet.

Important nuance: **share does not need to be higher than it was at the original early trigger.** Several winners lost some share while remaining highly concentrated (for example Barcelona, Betis and Atalanta in the T-60 set). Absolute retained concentration matters more than whether the share mathematically increased from the early snapshot.

For the T-60 set at T-5 specifically:
- baseline: 11/13 = 84.6%
- >=60%: 10/11 = 90.9%
- >=70%: 8/9 = 88.9%
- >=75%: 6/6 = 100% (tiny)

Therefore the current evidence strongly supports **<60 as a downgrade** and **>=60 as retained**, while 70/80 should be used as escalating signal-strength labels pending larger validation rather than hard probability claims.

Next test: combine this retention state with opponent/draw-side money acceleration and compare winners vs failures, then test over a larger archive.