# SXF Signal Engine Registry

Updated: 2026-10-15
Status: RESEARCH / SHADOW REGISTRY

This registry is separate from the Predictor Stage 1/2/3 workflow. It describes the SXF signal engines, strength tags, filters and research candidates used in signal-engine research. A research result does not automatically change production behavior.

## Global selection / validity rules

### SXF price floor
- `odds < 1.30` -> `PRICE_FILTER_REJECT`
- `odds >= 1.30` -> eligible for normal evaluation.
- Raw signals are still archived; the price floor acts at the selection layer.

### Snapshot freshness
- A checkpoint must use a genuinely current stored snapshot; an old row must not be treated as if it were current.
- Historical signal-engine samples have used a `<=30 min` freshness convention for comparable checkpoint analysis.
- A stricter operational freshness threshold remains a separate research/implementation decision and must not be silently changed.

## 1. EARLY_MONEY_CORE

Purpose: detect unusually strong team money well before kickoff.

Qualifying families:
- T-72: top-money HOME/AWAY team, amount `>= £5,000`, share `>=50%`.
- T-60: top-money HOME/AWAY team, amount `>= £5,000`, share `>=50%`.
- T-40: top-money HOME/AWAY team, amount `>= £10,000`, share `>=50%`.
- T-24: top-money HOME/AWAY team, amount `>= £10,000`, share `>=50%`.

Dedup rule:
- Core performance uses the first qualifying strong Early signal per fixture.

Retention 55:
- At T-6/T-5/T-4/T-3, if the selected team's money share falls below `55%` at any observed checkpoint, mark `RETENTION_BREAK`.
- Once broken, later recovery does not restore the Early signal.
- Retention is a validity guard, not a confidence bonus.

Current research note:
- T-24 is the weak cohort and is being investigated separately.
- Candidate improvements include T-24 money/share thresholds and extreme adverse price drift, but none is promoted yet.

## 2. EARLY_MONEY_T12

Purpose: track a later high-concentration Early observation separately from the strong Early core.

Criteria:
- T-12 checkpoint.
- top-money HOME/AWAY team.
- amount `>= £1,000`.
- share `>=80%`.

Rule:
- Do not silently pool T-12 into the T-72/T-60/T-40/T-24 core performance figure.

## 3. 1X2_CONCENTRATION_V1

Purpose: identify a team side with strong concentrated money at a live checkpoint.

Criteria:
- HOME/AWAY team only.
- top-money team.
- selected amount `>= £1,000`.
- selected money share `>=80%`.
- selected odds `1.40–2.50` inclusive.

Tracked checkpoints:
- T-6 / T-5 / T-4 / T-3.

## 4. 1X2_CONCENTRATION_V2

Status: challenger; V1 is not replaced.

Purpose: require persistence and limited adverse price movement in addition to V1.

Criteria:
- all V1 conditions, plus:
- during the previous 3 hours, selected-side money share never below `70%`;
- selected-side odds adverse rise over the previous 3 hours `<=3%`.

Interpretation:
- Concentration is stronger when money persists and the price does not move materially against the selected side.

## 5. HEAVY_1X2_CONCENTRATION

Status: strength tag within the Concentration family, not an independent confirmation engine.

Criteria:
- concentration side amount `>= £10,000`;
- money share `>=80%`.

Important:
- Historical archive replication should preserve the archived Heavy definition/tag and must not silently impose a new odds band.

## 6. SURPRISE_TEAM

Status: serious revision required.

Purpose: detect meaningful money concentration on a genuine underdog/surprise HOME/AWAY team.

Current criteria:
- HOME/AWAY team only;
- odds `2.90–4.49` inclusive;
- money share `>=50%`.

Important:
- There is currently no mandatory absolute-money or total-volume threshold in the canonical definition.
- Market volume is context only.
- A minimum absolute-money challenger may be tested, but is not yet an approved rule.

## 7. STABLE_OVER_2_5

Purpose: detect a well-supported Over 2.5 position with moderate-to-strong money concentration.

Criteria:
- market: Over 2.5;
- Over amount `>= £1,500`;
- Over money share `>=65%`;
- Over odds `1.40–1.80` inclusive.

Tracked checkpoints:
- T-6 / T-5 / T-4 / T-3.

## 8. PREMIUM_OVER_2_5

Status: redesign / timing research required.

Purpose: stronger-money subtype of Stable Over.

Criteria:
- market: Over 2.5;
- Over amount `>= £2,500`;
- Over money share `>=75%`;
- Over odds `1.40–1.80` inclusive.

Important:
- Premium is a stronger threshold set, but must not be assumed automatically superior to Stable Over.
- Timing/persistence by checkpoint is under research.

## 9. BTTS_YES

Purpose: detect concentrated money support on Both Teams To Score — Yes.

Criteria:
- market: BTTS Yes;
- Yes amount `>= £750`;
- Yes money share `>=60%`;
- Yes odds `1.60–1.90` inclusive.

Tracked checkpoints:
- T-6 / T-5 / T-4 / T-3.

## 10. DRAW_TRAP_V1

Status: `SHADOW / RESEARCH_CANDIDATE` — frozen prospectively from 2026-10-15. Not a production rule.

Purpose: detect matches where one side receives a sharp price shortening without dominant money support and the price structure clusters in a historically unusual draw zone.

Frozen criteria:
1. Compare the same HOME/AWAY side at T-6 and T-3.
2. Selected side odds fall by at least `5%` from T-6 to T-3.
3. Selected side T-3 money share is `40%–65%` inclusive.
4. Selected side T-3 odds are `2.00–2.40` inclusive.
5. Opponent T-3 odds are `>=2.75`.
6. Signal selection = `DRAW`, using the real T-3 draw odds for evaluation.

Discovery note:
- The 2.00–2.40 band was found post-hoc on the 2026-10-09 through 2026-10-14 research data.
- Exploratory discovery sample: 8 draws from 9 qualifying cases.
- Because the band was discovered on the same data used to evaluate it, 8/9 is not independent validation.

Shadow rule:
- Do not change thresholds while collecting prospective cases.
- Track every future qualifying case, draw odds, result, flat-1u P/L and cumulative ROI.
- Review after at least 10 new prospective cases, then 20, then 30.

## Research heuristics / context signals that are NOT standalone approved engines

### Gradual Odds Decline
- User methodology: a staircase-like, multi-step price decline is more meaningful than one sudden collapse, especially when money momentum/velocity and volume also grow.
- No final fixed thresholds are approved yet.

### Low-popularity / unusually high money
- Unusually high absolute money relative to the normal liquidity of a league/team can be meaningful even if price is flat or only slightly adverse.
- This is context/research logic, not a standalone fixed-threshold engine yet.

### Big Money all-three-sides condition
- When HOME/DRAW/AWAY all receive unusually large money, especially near kickoff, treat it as a special-state alarm requiring separate interpretation.
- It is not a direct team-selection engine by itself.

### Late Drift + Money Hold
- Research idea: between T-1 and kickoff, a team priced roughly 1.20–2.20 whose odds rise sharply while money share remains very high may behave differently from low-money adverse drift.
- Two-day exploratory evidence is interesting but insufficient; no frozen engine definition has been approved yet.

## Change-control rule

New or changed rules follow:
`CANDIDATE -> HISTORICAL_TEST -> SHADOW -> REVIEW -> PROMOTE / REJECT`

Do not silently rewrite historical samples, thresholds or production behavior. New versions must be explicit and time-ordered.

## 2026-10-23 prospective correction — HEAVY and V2 (V3 release candidate)

**Change provenance:** User-requested correction to two V2 signal-motor behaviors after
auditing Stuttgart–Mgladbach and Bochum–Wolfsburg. This section is a
forward-looking amendment; the 2026-10-15 research definitions above and
previously archived signals remain historically unchanged.

- **HEAVY:** Must meet **all** V1 conditions (top-money HOME/AWAY,
  amount >= £1,000, share >=80%, odds **1.40–2.50 inclusive**) **and**
  amount >= £10,000. It is a V1 strength tag, never an independent signal.
  A 1.38 quote fails HEAVY regardless of concentration.
- **V2:** Must meet all V1 conditions, retain four distinct hourly anchored
  snapshots spanning the prior three hours, and have no complete observation
  with share <70%. In time order, maintain the lowest odds observed **so far**
  (the running trough). If any **later** price exceeds that prior trough by
  more than 3%, reject V2. Exactly +3% is allowed. Do not use a future low
  to invalidate an earlier quote. Status code stays
  `THREE_HOUR_ADVERSE_ODDS` for clients that recognize it.
- Original archived ruleset `SXF_SIGNAL_MOTOR_V2_2026_10_22` events must
  **not** be overwritten or silently re-labeled. Full production rollout
  requires a separately verified, versioned cutover across queue, claim,
  worker, storage and feed (the SQL claims were V2-only at the 23 October audit).
- V1, Early Core, Early T12, Over, BTTS, Surprise and checkpoint scheduling
  rules are deliberately unchanged. The changes are tested on `preview`;
  they are not automatically released to production.


## 2026-10-24 prospective V3 release contract

- New live releases use `SXF_SIGNAL_MOTOR_V3_2026_10_24` in the
  scheduler, durable job key, claim RPCs, immutable evaluations/events and
  server-side feed.
- Database migrations:
  `migrations/2026_10_24_signal_motor_v3_versioned_cutover.sql` and
  `migrations/2026_10_24_signal_motor_v3_health_scope.sql`.
- Enqueue permits all audited V1/V2 identities but only V3 is claimable
  for new checkpoint evaluation or rule-dependent late-T6 reconciliation.
  In-flight V2 source-skip leases remain fenced and can settle.
- Previous V1/V2 jobs, attempts, evaluations and signals remain unchanged;
  historical V2 events continue to be available with explicit LEGACY
  release metadata. Worker backpressure is V3-scoped, and historical due
  debt is separately exposed as `historical_pending_due`.
- This contract does not declare complete fixture coverage, historical
  backlog clearance, or a production release. Exact SHA, CI, versioned DB
  readiness, Hetzner deploy and post-release checks remain required.
