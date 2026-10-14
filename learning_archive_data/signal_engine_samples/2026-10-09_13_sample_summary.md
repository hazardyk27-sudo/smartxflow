# SXF Signal Engine Sample — 2026-10-09 through 2026-10-13

Status: RESEARCH SAMPLE / APPEND-ONLY
Timezone: Europe/Istanbul
Primary comparable benchmark window: local kickoff 16:30–23:30
Source: SmartXFlow stored native SXF histories and live_fixtures results

## Why this file exists

This file extends the original 9–12 October research sample with 13 October and freezes the current aggregate results. Match-level Early Money first signals are stored in `2026-10-09_13_early_money_first_signals.csv`. Detailed 13 October T-6/T-5/T-4/T-3 observations for the tested checkpoint engines are stored in `2026-10-13_checkpoint_signal_observations.csv`.

Do not rewrite this historical sample when thresholds change. New thresholds/models must be versioned and compared prospectively.

## Early Money core family

Core Early Money = T-72/T-60/T-40/T-24 families, deduped to the first qualifying signal per match. T-12 is tracked separately and must not be silently pooled into this core figure.

- 9–12 October: 18/22 wins = 81.8%
- 13 October: 6/10 wins = 60.0%
- 9–13 October combined core: 24/32 wins = 75.0%

13 October core winners: Arsenal, Atletico Madrid, Birmingham, Barcelona, RB Leipzig, Villarreal.
13 October core losses: Slavia Prague, Bristol City, Inter, Bayern Munich.

## Retention 55

User-selected rule: for a qualifying T-72/T-60/T-40/T-24 Early Money side, if the selected team falls below 55% at any T-6/T-5/T-4/T-3 checkpoint, mark `RETENTION_BREAK`; later recovery does not restore the Early Money signal.

Important preserved note: 55% was NOT the statistically strongest cutoff in the original four-day historical test. 60% had stronger historical discrimination, but 55% was deliberately chosen as the looser operational research threshold to reduce false elimination of winners.

13 October supplied a concrete prospective example supporting that concern: Villarreal fell to 59.2% at T-3 and won 3-1. A 60% cutoff would have eliminated that winner; the 55% rule kept it alive.

13 October also showed the limitation of retention: Inter and Bayern both retained very high shares and still failed. Retention is a validity guard, not a guarantee.

## 1X2 Concentration V1 — five-day raw checkpoint aggregate

Definition: top-money TEAM, amount >= £1,000, share >= 80%, odds 1.40–2.50.

| Checkpoint | 9–12 | 13 Oct | 9–13 combined |
|---|---:|---:|---:|
| T-6 | 31/39 | 2/4 | 33/43 = 76.7% |
| T-5 | 38/48 | 2/3 | 40/51 = 78.4% |
| T-4 | 39/50 | 2/3 | 41/53 = 77.4% |
| T-3 | 38/52 | 2/4 | 40/56 = 71.4% |

13 October contains stale snapshots in some raw checkpoint rows because the feed had a long outage. Therefore raw totals above are preserved for historical continuity, but operational/live evaluation must apply a freshness guard. In particular, Bristol City and Burnley appeared as stale T-6 V1 rows; the fresh T-6 V1 cases were Birmingham and RB Leipzig, both winners.

## 1X2 Concentration V2 — five-day aggregate

Definition: V1 + previous 3h share never below 70% + selected-side odds did not rise more than 3% over the previous 3h.

| Checkpoint | 9–12 | 13 Oct | 9–13 combined |
|---|---:|---:|---:|
| T-6 | 27/32 | 2/2 | 29/34 = 85.3% |
| T-5 | 34/40 | 2/3 | 36/43 = 83.7% |
| T-4 | 37/46 | 2/3 | 39/49 = 79.6% |
| T-3 | 37/47 | 2/4 | 39/51 = 76.5% |

V2 remains a separate challenger. V1 is not replaced.

## Heavy 1X2 Concentration — five-day aggregate

Definition: Concentration side with amount >= £10,000 and share >= 80%; this is a strength tag within the Concentration family, not an independent confirmation engine.

| Checkpoint | 9–12 | 13 Oct | 9–13 combined |
|---|---:|---:|---:|
| T-6 | 14/16 | 2/3 | 16/19 = 84.2% |
| T-5 | 16/19 | 2/2 | 18/21 = 85.7% |
| T-4 | 16/18 | 2/3 | 18/21 = 85.7% |
| T-3 | 17/22 | 2/4 | 19/26 = 73.1% |

Again, 13 October T-6 includes a stale Bristol row. Fresh T-6 Heavy cases were Birmingham and RB Leipzig, both winners.

## Surprise Team — five-day aggregate

Definition: HOME/AWAY team only, odds 2.90–4.49 inclusive, money share >= 50%. Market volume is context, not a threshold.

| Checkpoint | 9–13 wins | Win rate | Non-loss | Non-loss rate |
|---|---:|---:|---:|---:|
| T-6 | 15/40 | 37.5% | 28/40 | 70.0% |
| T-5 | 16/45 | 35.6% | 31/45 | 68.9% |
| T-4 | 17/51 | 33.3% | 29/51 | 56.9% |
| T-3 | 20/51 | 39.2% | 31/51 | 60.8% |

13 October reinforced that a high share by itself is not enough. Fulham U21 had 95.7% and £3.36k at one stored checkpoint and still lost 3-2.

## Stable Over 2.5 — five-day aggregate

Definition: Over amount >= £1,500, share >= 65%, odds 1.40–1.80.

| Checkpoint | 9–12 | 13 Oct | 9–13 combined |
|---|---:|---:|---:|
| T-6 | 14/18 | 2/2 | 16/20 = 80.0% |
| T-5 | 15/20 | 2/3 | 17/23 = 73.9% |
| T-4 | 14/19 | 2/3 | 16/22 = 72.7% |
| T-3 | 16/23 | 2/4 | 18/27 = 66.7% |

## Premium Over 2.5 — five-day aggregate

Definition: Over amount >= £2,500, share >= 75%, odds 1.40–1.80.

| Checkpoint | 9–12 | 13 Oct | 9–13 combined |
|---|---:|---:|---:|
| T-6 | 7/10 | 0/0 | 7/10 = 70.0% |
| T-5 | 9/11 | 1/1 | 10/12 = 83.3% |
| T-4 | 11/13 | 1/1 | 12/14 = 85.7% |
| T-3 | 12/15 | 1/2 | 13/17 = 76.5% |

## BTTS Yes — five-day aggregate

Definition: Yes amount >= £750, share >= 60%, odds 1.60–1.90.

| Checkpoint | 9–12 | 13 Oct | 9–13 combined |
|---|---:|---:|---:|
| T-6 | 10/12 | 1/2 | 11/14 = 78.6% |
| T-5 | 14/17 | 0/2 | 14/19 = 73.7% |
| T-4 | 13/17 | 1/3 | 14/20 = 70.0% |
| T-3 | 14/18 | 2/4 | 16/22 = 72.7% |

13 October live-highlighted Inter–Club Brugge BTTS Yes won (3-4). Atletico–Man Utd touched the BTTS threshold earlier but failed (2-0), showing that a brief threshold touch may differ from a persistent signal.

## 13 October broader 17:00–24:00 outcome context

At the time of the postmortem query: 134 fixtures in scope, 119 FT, 2 live, 13 missing-result rows. Among the 119 finished matches: 53 home wins, 28 draws, 38 away wins; average goals 3.24; Over 2.5 = 79/119 (66.4%); BTTS Yes = 67/119 (56.3%).

## Data-quality lesson added on 13 October

A checkpoint engine must not treat an old stored row as if it were a current T-minus observation. Store and evaluate `snapshot_age_min`. Operational signal generation requires an explicit freshness guard. The historical archive keeps stale rows visible rather than deleting them, so future research can audit the outage and test alternative freshness limits without hindsight rewriting.
