# Match Analyst Daily Journal Standard

## Purpose

The daily journal is the Match Analyst's longitudinal research memory. It records what happened during the day, what the analyst believed before results, how the slate actually finished, what was learned, and what must be tested next.

It is not a replacement for immutable prediction records or per-match postmortems. Those remain the detailed factual source. The journal is the daily synthesis layer that lets future sessions continue from the real state instead of starting from scratch.

## Location and naming

Create exactly one journal per analysis day:

`research/match_analyst/journal/YYYY-MM-DD.md`

Use the analysis date in Europe/Istanbul local date unless the user explicitly requests another convention.

## Lifecycle

A journal has three states:

- `OPEN` — created before the day's first substantive slate analysis.
- `LIVE` — predictions/research are in progress; append timestamped material as needed.
- `CLOSED` — the day's results/postmortem are sufficiently complete and next-day focus is recorded.

Once CLOSED, do not rewrite the historical narrative. If a factual correction is later required, append an `ADDENDUM` with its date/time and explain what changed and why.

## Opening section — written before outcomes

Every journal must begin with:

### Day metadata
- date
- journal status
- methodology version
- workflow version
- previous journal path
- previous day's carried focus

### Starting focus
State 1–5 concrete things the analyst will pay special attention to today because of prior evidence.

Examples:
- recheck official lineups for lineup-sensitive FIRSAT candidates
- penalize late price reversals more heavily
- distinguish low-liquidity money spikes from genuine confirmation

Do not add a focus merely because it sounds useful. It should come from the current methodology or an earlier observation/postmortem.

### Pre-result hypotheses
If the analyst is deliberately testing a pattern today, record it before results.

Example:
`OBSERVATION TO TEST: large money share without price shortening may be weaker than moderate money with clear price confirmation.`

This preserves chronology and prevents hindsight.

## During-day section

Append only meaningful events, not a transcript of every thought.

For each major entry include:
- timestamp
- fixture or slate context
- what changed in SXF data, external evidence, or market state
- whether the original thesis strengthened, weakened, reversed, or remained unchanged
- whether the event changed FIRSAT / IZLE / UZAK DUR status
- link/reference to the immutable prediction record when applicable

Do not silently rewrite earlier entries.

## Closing section — written after settlement/postmortem

Every closed journal must contain all of the following.

### 1. Daily scoreboard
Where available:
- FIRSAT count
- wins / losses / pushes / voids
- average entry odds
- flat-stake P/L and ROI
- CLV coverage and average CLV
- IZLE outcomes may be tracked separately for research, but never mixed into official FIRSAT performance

### 2. What happened today
Write a concise factual summary of the slate. Focus on the most decision-relevant events rather than retelling every match.

### 3. What worked
Identify specific process elements that were supported today.

Good examples:
- price-money confirmation remained stable through kickoff
- official lineup verification correctly downgraded a candidate
- choosing DNB/DC instead of ML matched the actual risk profile

Bad example:
- "we won, therefore the method works"

Winning alone is not proof of process quality.

### 4. What failed
Identify specific process elements that failed or looked weak.

Examples:
- late reversal was ignored
- predicted lineup was treated as confirmed
- money concentration was overweighted despite drifting odds
- H2H was given too much weight

A loss caused by ordinary variance should not be invented into a process failure.

### 5. Best decision of the day
Choose the prediction or no-bet decision with the strongest process quality, not necessarily the biggest winner.

Explain why the decision process was good.

### 6. Worst decision of the day
Choose the decision with the weakest process quality, even if it happened to win.

Explain the error chain.

### 7. Error diagnosis summary
Summarize postmortem categories and distinguish:
- process/model errors
- execution/price errors
- data failures
- normal variance

### 8. Important discoveries
Record anything genuinely learned today under exactly one of:

- `OBSERVATION`
- `PROCESS_FIX`
- `RESEARCH_CANDIDATE`

For each item include:
- evidence from today
- whether similar prior evidence exists
- confidence in the lesson
- what would falsify it

Do not promote a single-day result into a predictive rule.

### 9. What we now think is good
List patterns/processes that currently look promising, with their evidence level.

Use cautious language such as:
- `SUPPORTED TODAY`
- `REPEATED OBSERVATION`
- `RESEARCH CANDIDATE`

Never write `PROVEN` without formal validation outside the Match Analyst role.

### 10. What we now think is bad
List patterns/processes that currently look harmful or misleading, with the same evidence discipline.

Examples:
- extreme money share without price confirmation
- low-liquidity moves
- late price reversal against the selected side

Do not permanently ban a predictive pattern from one bad day unless it is an obvious operational/process defect.

### 11. Unresolved questions
Record evidence that remains ambiguous. Unknowns should survive into the next day rather than being forced into a story.

### 12. Tomorrow's focus
End with 1–5 explicit focus points for the next analysis day.

Each focus must be testable and linked to either:
- a process safeguard,
- an unresolved question,
- a repeated observation,
- or a research candidate.

## Journal quality rules

- Prefer causal statements over generic summaries.
- Separate evidence from interpretation.
- Preserve chronology: what was known before kickoff versus after the match.
- Do not judge process quality only by final score.
- Do not remove losses or no-bet decisions from the journal.
- Do not retroactively change confidence or entry odds.
- Avoid emotional language such as "unlucky" unless supported by measurable match evidence; use `NO_ERROR_VARIANCE` when appropriate.
- Keep the journal concise enough that a new agent can read the last 1–3 closed days quickly.

## Cross-day learning

The next Match Analyst session must read the latest closed journal before beginning the new slate.

If an observation repeats across multiple days, explicitly count/refer to the prior occurrences and consider promoting it from `OBSERVATION` to `RESEARCH_CANDIDATE`.

If a `PROCESS_FIX` was introduced, the next journal must state whether the safeguard was actually followed and whether it helped.

The journal may recommend research to the System Development Agent, but it cannot alter SXF production logic itself.
