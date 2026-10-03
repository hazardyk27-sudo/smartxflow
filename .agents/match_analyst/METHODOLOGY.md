# Match Analyst Methodology

Version: 1.0.0

## Objective

Build a repeatable daily football analysis process that can later be translated into deterministic SXF features and engines. The process must preserve the difference between market evidence, external football evidence, and post-result hindsight.

## Phase 1 — SXF-only market scan

Before reading news or external match previews, inspect every eligible football match available in SXF and capture, where available:

- fixture identity, league/competition, kickoff time
- current 1/X/2 odds
- opening/reference odds and intermediate odds
- total matched volume/liquidity
- selection money percentage
- selection absolute money amount
- new money delta over time
- money velocity/acceleration
- odds change percentage and direction
- price reaction after money enters
- 24h / 12h / 6h / 3h / 2h / 60m / 30m / current path when data exists
- O/U 2.5 and BTTS context when available
- dropping market context
- cross-market agreement/conflict
- Poly / tracked-wallet evidence when available
- time to kickoff

Do not fabricate missing windows or fields. Mark unavailable fields explicitly.

## Price-money interpretation

Classify the core relation:

- `MONEY_UP_PRICE_SHORTENS` — money and price confirm the same side.
- `MONEY_UP_PRICE_DRIFTS` — divergence; investigate why price resists the money.
- `MONEY_SPIKE_PRICE_FLAT` — absorption/anomaly; liquidity and opposing flow may matter.
- `PRICE_SHORTENS_WITHOUT_VISIBLE_MONEY` — external/hidden market information may be driving price.
- `LOW_LIQUIDITY_NOISE` — move is too thin to trust.
- `MIXED/UNKNOWN` — evidence is not coherent.

Always normalize interpretation by liquidity, league quality, market type, and time to kickoff. A £10k move can be enormous in one competition and irrelevant in another.

## Candidate screen

After the SXF-only read, assign exactly one pre-research state:

### RESEARCH
There is a coherent or unusual market pattern worth investigating.

### WATCH
Evidence exists but is incomplete, weak, conflicted, too early, or price-sensitive.

### REJECT
No meaningful edge, poor liquidity, stale/missing data, contradictory evidence, or price already appears exhausted.

For RESEARCH candidates, save the pre-research thesis before opening external sources.

## Phase 2 — Cause investigation

For each RESEARCH candidate, answer: **Why is this market moving?**

Research at minimum:

### Team availability
- injuries and return dates
- suspensions
- expected and confirmed lineups
- rotation risk
- national-team travel/returns
- goalkeeper and key-position changes

### Manager/team communication
- press conferences
- rotation comments
- fitness comments
- tactical comments
- stated priority of the match

### Motivation and competition context
- title/relegation/playoff/qualification pressure
- must-win versus low-stakes fixture
- first/second leg dynamics
- derby/rivalry context
- cup rotation
- friendly/preseason status
- schedule congestion and next fixture importance

### Performance and statistics
Do not reduce form to last-five W/D/L. Where available examine:
- xG / xGA
- shots and shots on target
- big chances
- shot quality
- home/away splits
- opponent strength
- set-piece threat/weakness
- finishing/goalkeeping overperformance or underperformance
- recent tactical/formation changes

### H2H
Use only as context. Weight recent and tactically relevant meetings more than old historical meetings. Explain when coaches, squads, venue, or competitive context make old H2H weak evidence.

### Extraordinary/contextual factors
- weather
- travel disruption
- pitch/stadium conditions
- disciplinary/internal club issues
- ownership/payment disputes where reliably reported
- unusual public or bookmaker reaction

## Active falsification

For every candidate, deliberately search for evidence that would invalidate the original SXF thesis. Do not research only confirming evidence.

Ask:
- What would make this money move misleading?
- Is the move public/recreational rather than informed?
- Is liquidity too low?
- Is the strongest news already fully priced?
- Is there opposing information from lineups, injuries, tactics, or schedule?
- Did the market reverse after the original move?

## Phase 3 — Evidence merge

Classify the relationship between SXF and external research:

- `CONFIRMED` — independent evidence supports the market thesis.
- `PARTIALLY_CONFIRMED` — some support, but meaningful uncertainty remains.
- `UNEXPLAINED_MARKET_MOVE` — the move is real/coherent but no reliable external cause is found.
- `CONFLICT` — independent evidence materially contradicts the SXF thesis.
- `NO_EDGE` — evidence may be correct but the current price no longer offers a useful proposition.

Unknown cause does not automatically mean bad signal. It must remain explicitly unknown.

## Phase 4 — Market selection

Choose the real market that best matches the thesis and risk profile. Evaluate, when actually available:
- 1X2
- Double Chance
- Draw No Bet
- O/U
- BTTS

Do not invent synthetic odds or synthetic DC/DNB prices. If the appropriate safer market is unavailable, say so.

Underdog direction does not automatically imply longshot moneyline. Strong favorite evidence does not automatically imply taking a very short price.

## Phase 5 — Final status

Assign one final state:

### FIRSAT
The combined evidence is coherent, price is still acceptable, major counterarguments are addressed, and data quality is sufficient.

### IZLE
Interesting evidence exists but timing, price, uncertainty, lineup/news confirmation, or conflict prevents a final selection now.

### UZAK DUR
Evidence is materially contradictory, low-quality, stale, distorted, or price/value conditions are poor.

No Bet is a valid and desirable outcome.

## Confidence

Confidence is evidence strength, not a promised win probability. It must reflect:
- data completeness/freshness
- price-money coherence
- liquidity quality
- timing
- cross-market confirmation
- independent news/statistical confirmation
- counter-signal severity
- price/value remaining

Never use confidence to imply certainty or guaranteed profit.

## Immutable prediction checkpoint

Before kickoff, every final FIRSAT prediction must preserve:
- prediction_id
- timestamp
- fixture/match identity
- kickoff
- market
- selection
- entry odds observed at publication
- SXF evidence snapshot
- external evidence summary
- cause classification
- confidence
- counterargument
- invalidation condition
- methodology version

After publication, do not overwrite these fields. Later updates must be appended as new observations.

## Evaluation metrics

Over time evaluate at least:
- sample size (N)
- hit rate
- average entry odds
- flat-stake ROI
- CLV where closing odds are available
- max drawdown
- calibration by confidence band
- performance by league/competition
- performance by market type
- performance by cause classification
- performance by price-money pattern

Raw hit rate alone is not sufficient.
