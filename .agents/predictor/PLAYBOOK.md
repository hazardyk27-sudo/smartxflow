# Predictor Playbook

REFERENCE_VERSION: 1

Open this file only for substantive match-analysis/prediction work.

## Ordered workflow

1. **SXF first** — read the market without external-news contamination.
2. **Candidate filter** — decide whether the match deserves research.
3. **Cause research** — investigate injuries, lineups, suspensions, tactical/context factors, schedule, weather and reliable statistics/sources.
4. **Opposite case** — actively seek evidence that could invalidate the first thesis.
5. **Merge evidence** — label `CONFIRMED`, `PARTIALLY_CONFIRMED`, `UNEXPLAINED_MARKET_MOVE`, `CONFLICT`, or `NO_EDGE`.
6. **Choose market** — use an actually available market; prefer safer structures such as Double Chance/DNB when evidence supports them rather than blindly taking a high-odds underdog.
7. **Decision** — `BET`, `WATCH`, or `PASS`.
8. **Freeze prediction** — record cutoff, market, selection, entry odds, confidence, rationale, counterargument and evidence observed by cutoff.
9. **Settlement/postmortem** — after result, diagnose process separately from football variance.
10. **Archive** — finalize one selected-case package; do not recollect all market data.

## Market principles

- Money share alone is weak; price response to money is central.
- More money is not automatically stronger.
- A larger odds collapse is not automatically better value.
- Distinguish absolute money, money share, new-money delta, velocity, liquidity and timing.
- Use the full stored path where available: opening and successive time points, not only the latest snapshot.
- Look for price/money confirmation, divergence, reversal, momentum and cross-market relationships.
- 1X2 should be compared with Double Chance/DNB where available.
- Always state the failure condition/counterargument.

## External evidence

Prefer official team/competition sources for lineups, injuries/suspensions and announcements; then reliable reporters/data sources. Record source identity/reference, `published_at` when known, mandatory `observed_at`, factual note, evidence category and whether it supports/contradicts/is neutral.

## Output minimum

For every final view show:

- `SXF SAYS`
- `RESEARCH SAYS`
- `MERGED VIEW`
- decision (`BET | WATCH | PASS`)
- market + selection + entry odds
- confidence if used
- strongest supporting evidence
- strongest counterargument/failure condition
- `prediction_at`

## Postmortem

After settlement separate:

- process/model error,
- execution/price error,
- missing/stale data,
- normal football variance.

A win does not validate the method and a loss does not invalidate it. Predictive-method changes require repeated archived evidence and Development testing.
