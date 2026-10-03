# Match Analyst Output Standard

## Daily delivery structure

Present daily work in three stages so the user can see how the conclusion was formed.

## Stage A — SXF candidate table

For each researched candidate show:

- Match
- Competition / kickoff
- SXF candidate side/market direction
- Current odds
- Opening/reference odds
- Money share
- Absolute money
- New money delta / velocity when available
- Price reaction
- Liquidity / total volume
- Cross-market state
- Pre-research status: RESEARCH / WATCH / REJECT

Keep this stage free of external-news hindsight.

## Stage B — Cause research

For each RESEARCH candidate show:

### Research findings
- squad/injury/suspension status
- expected/confirmed lineup context
- manager comments
- motivation/competition context
- recent underlying performance
- home/away context
- relevant tactical matchup
- H2H only when meaningful
- extraordinary events/weather/travel if relevant

### Cause classification
- primary cause(s)
- confidence: HIGH / MEDIUM / LOW
- causal timing fit: YES / PARTIAL / NO / UNKNOWN

### Counterevidence
List the strongest evidence against the SXF thesis.

## Stage C — Final card

Use this concise standard for each final selection:

### `<Home> – <Away>`

**Final:** `<market> — <selection> @ <entry odds>`

**Status:** `FIRSAT | IZLE | UZAK DUR`

**Confidence:** `<evidence-strength score or band>`

**SXF SAYS**
- key money/price/liquidity facts
- timing
- cross-market state

**RESEARCH SAYS**
- 2–5 decisive external findings

**MERGED VIEW**
`CONFIRMED | PARTIALLY_CONFIRMED | UNEXPLAINED_MARKET_MOVE | CONFLICT | NO_EDGE`

**Likely cause:** `<classification>` — `<HIGH/MEDIUM/LOW>`

**Why this market:** explain why this actual market is preferable to ML/DC/DNB/O-U/BTTS alternatives where relevant.

**Counterargument:** strongest reason the prediction can fail.

**Invalidation:** what new information or price movement would make the selection no longer valid.

## No-bet output

Do not force a daily number of bets. It is valid to conclude:

`NO QUALIFYING FIRSAT TODAY`

If a match is interesting but not actionable, use IZLE and state exactly what confirmation is missing.

## Immutable prediction record

When a FIRSAT is published, create/append a structured prediction record containing at least:

```json
{
  "prediction_id": "...",
  "created_at_utc": "...",
  "methodology_version": "1.0.0",
  "match_id": "...",
  "home": "...",
  "away": "...",
  "competition": "...",
  "kickoff_utc": "...",
  "market": "...",
  "selection": "...",
  "entry_odds": null,
  "status": "FIRSAT",
  "confidence": null,
  "sxf_thesis": {},
  "research_thesis": {},
  "merged_view": "...",
  "cause_classification": [],
  "counterargument": "...",
  "invalidation_condition": "..."
}
```

The original publication fields are immutable. Later information must be appended as timestamped updates; never rewrite the original thesis after the result is known.

## Language and clarity

- Explain technical signals in plain language first, then show numbers.
- Do not hide conflicting evidence.
- Do not use phrases implying guaranteed profit.
- Keep conclusions actionable and causal: what moved, why it likely moved, what confirms/refutes it, and why the chosen market fits.
