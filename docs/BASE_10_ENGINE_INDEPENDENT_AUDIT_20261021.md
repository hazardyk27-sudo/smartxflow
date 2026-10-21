# SmartXFlow 10-engine independent production audit — 21 October 2026

Source: read-only live Supabase SQL against canonical `sxf_base_signal_events`,
`sxf_base_checkpoint_jobs`, `sxf_base_checkpoint_evaluations`, and real,
UID-scoped, timestamped `moneyway_snapshots`. This report is an immutable
observation from 21 October, not a claim of future/perpetual full coverage.

## Live independent evidence

- All **10** frozen Base engine names have persisted events.
- **149/149** signal-event selections/odds/amounts/shares matched *exactly*
  against the original `moneyway_snapshots` row by physical fixture UID,
  market, selection and immutable `observed_at`.
- **149/149** signal observations were inside the frozen
  `[checkpoint-30min, checkpoint]` observation windows.
- Across all 10 families, **zero** elementary threshold violations and
  **zero** inconsistent `PRICE_FILTER_REJECT`/eligible price flags were found.
- V2: **22/22** events had all four independently verified T-(h+3),
  T-(h+2), T-(h+1), T-h complete 1X2 anchor snapshots. Full complete
  snapshots between the earliest and latest actual anchors showed
  **zero share dips below 70%**, **zero adverse odds increases above 3%**.
  Lowest verified share **72.20%**; largest observed increase
  **1.0265486726x** (2.65%).
- These checks validate *stored events*, not whether every fixture had enough
  source to be evaluated, nor whether the worker produced its event on time.

## Important presentation and timing findings

Live event chronology before this presentation correction:
- `EARLY_SIGNAL`: 49 events; **22** recorded after kickoff.
- `FINAL_SIGNAL`: 48 events; **5** recorded after kickoff.
- `PRELIMINARY_SIGNAL`: 44 events; **8** recorded after kickoff.

The frozen pre-match `observed_at` of a delayed evaluation remains valid
historical evidence, but `recorded_at > kickoff_utc` is not a timely
notification and must never be counted as one.
The ledger legitimately archives both:
1. engine-rule matches with `PRICE_FILTER_REJECT` (including Heavy)
   which fail the source registry's 1.30 selection floor;
2. late/replayed or superseded T-8 evaluations.

The previous Analizler feed labelled late rows but counted all archived
events as 'signals', and did not mark the price rejected rows clearly.

## Fix (presentation projection only)

`base_signal_engine/feed.py` now emits:
- `selection_status`: only ELIGIBLE / PRICE_FILTER_REJECT / UNKNOWN,
  with the 1.30 floor **rechecked** against the event's recorded real odds;
- `review_state`: VALID_PREMATCH_RECORD, PRICE_REJECTED,
  LATE_HISTORY, RECONCILED_HISTORY, T8_SUPERSEDED, or UNVERIFIED_STATUS;
- `valid_on_time` boolean: eligible signal event recorded no later
  than 20 minutes after its checkpoint (10-minute ingestion grace before
  claiming plus a bounded 10-minute processing allowance), before kickoff,
  and not superseded by T-6. This threshold classifies actual delivery
  time; it does not change the snapshot's 30-minute historical freshness,
  frozen engine criteria, or original job checkpoint schedule.

`static/js/base-signals.js` continues showing the immutable archived
events with explicit warnings, but **counts only valid_on_time events**
as timely eligible signals. Shows separate total archived record count.
Seven `static/i18n` locales have all new strings.

No motor thresholds, snapshot records, journal event rows, fixture identities,
or outcomes were modified. No reinterpretation of old price quotes as new
betting opportunities is allowed.

## Unresolved

- The realtime deadline compliance percentage remains low due to old backlog,
  after-the-fact replays and historical source gaps. Display correction is
  **not a cure for retrospective work**.
- Source unavailable at T-72 and incomplete Base/BTTS/OU25 market groups
  remain real non-events, not silently 'no signal'.
- `sxf_base_reconcile_jobs` at audit time: 113 PENDING and 24 WAITING_DATA,
  no completed reconciliation; T-8 fallbacks must not be called fully
  authoritative until reconciliation is implemented and verified.
- This report does not declare automatic full 10/10 timely fixture coverage.

No Replit or user-PC access.

## Independent delivery-lag distribution

A subsequent production SQL aggregate found that some valid rule matches were
recorded only after a lengthy backlog recovery. For example, V1 and V2
both had median checkpoint-to-event lag about 429.7 minutes (7h 10m), whereas
the fastest actual records arrived around 10 minutes after checkpoint due.
A strict *10-minute* publication cutoff would therefore incorrectly mark even
a healthy worker's just-completed 10-minute-ingestion-grace cycle as late.
The revised **20-minute delivery threshold** counts genuine timely production
while retaining multi-hour replays strictly historical. This remains an
operational classification and should be reviewed against future uptime data.
