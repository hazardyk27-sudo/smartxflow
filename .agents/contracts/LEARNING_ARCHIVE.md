# Learning Archive Contract

CONTRACT_VERSION: 8

## Purpose

The Learning Archive is the historical evidence store for selected SmartXFlow prediction cases. It is not the live database and not a second scraper.

Only materially researched Predictor cases formalized as `BET` or `WATCH` with a concrete non-empty market and selection are normal usable cases. Whole-market archiving, no-pick/PASS cases and Poly/Polymarket inputs are excluded from normal prediction datasets/diaries.

Historical legacy records remain immutable for audit.

## Native evidence vs execution market

A formal case may use a final **execution market** that is not natively stored by SmartXFlow, provided the prediction preserves the underlying native SXF evidence that generated the thesis.

Native SmartXFlow evidence markets currently are:
- 1X2
- Over/Under 2.5
- BTTS

Allowed final execution markets may include:
- those native markets;
- Double Chance (`1X`, `X2`, `12`);
- logical handicaps such as `+1.5`, `-1`, `-1.5`;
- nearby alternative total lines such as O/U `1.5`, `3.5` when justified by the prediction thesis.

Draw No Bet (DNB) remains forbidden for new Predictor cases. No DNB collector/history table may be introduced.

No internal/synthetic collector/history table is required for DC, handicap or alternative totals merely because Predictor can use them as execution markets.

## Price truth for non-native execution markets

- Never invent or mathematically synthesize an exact DC/handicap/alternative-total price from native SXF odds.
- If a real execution price was actually observed externally, preserve that real price, source and `observed_at`.
- If exact execution price is unavailable, Predictor may preserve a **minimum acceptable price threshold** as conditional metadata.
- A minimum threshold must never be stored as if it were actual `entry_odds`.
- A priced formal `BET` on a non-native execution market requires a real observed available price.
- Conditional/unverified-price views may remain WATCH/conditional unless the runtime schema explicitly supports a non-priced formal case without pretending an entry price exists.

## Storage target

Canonical storage:
- repository: `hazardyk27-sudo/smartxflow`
- data branch: `learning-archive`
- root: `/learning_archive_data/`

No second archive repository or archive-specific token. Durable completion requires a confirmed GitHub commit/reference on `learning-archive`.

`preview` is source development; `main` is production; `learning-archive` is data-only and never deployed.

## Automatic case lifecycle

1. Predictor publishes a formal `BET` or `WATCH` with immutable real `prediction_at`, concrete execution market/selection, confidence, rationale and counterargument; actual entry odds are included when genuinely available.
2. Preserve the frozen Stage 1 native SXF evidence and Stage 2 external evidence used for the thesis.
3. Read selected-match already-stored SXF history through the internal Learning Archive API.
4. First durable archive operation writes immutable `case.json`, `evidence.json`, `captures/<observed_at>.json.gz` and appends `RECORDED`.
5. Later substantive prematch revisits append captures; never overwrite prior captures.
6. Settlement/end-of-day adds settlement, final full available native SXF timeline, deterministic checksums and `FINALIZED`.
7. Every settled formal case gets a compact append-only postmatch learning addendum.
8. Identical retries are idempotent; historical conflicts fail closed.

## Canonical archive layout

```text
learning_archive_data/
  README.md
  manifest.jsonl
  schema/
    match_case_v1.schema.json
  cases/
    YYYY/MM/DD/<case_id>/
      case.json
      evidence.json
      captures/<observed_at>.json.gz
      sxf_snapshots.json.gz
      settlement.json
      checksums.sha256
      addenda/<observed_at>-postmatch-learning.json
```

## Required case metadata

`case.json` must preserve at minimum:
- `archive_schema_version`
- `case_id`
- real SmartXFlow match identity (`match_id_hash` and normal match fields)
- immutable real `prediction_at`
- decision `BET|WATCH`
- mandatory non-empty execution market and selection
- real `entry_odds` when actually observed/applicable
- confidence
- rationale
- counterargument/failure condition
- source SmartXFlow commit/version metadata
- archive creation timestamp

When final execution market is non-native, preserve additionally when schema/runtime allows:
- underlying native SXF thesis market(s)/selection(s);
- execution-market type/line;
- external execution-price source + `observed_at` when actual price is used;
- conditional `minimum_acceptable_price` when no real price was observed;
- explicit `native_execution_history_unavailable: true` or equivalent provenance note.

A user-scoped match without a defensible formal selection remains visible in the analytical Stage 3 report but is not represented by a fake PASS archive case.

## Snapshot/capture archive

`captures/<observed_at>.json.gz` and final `sxf_snapshots.json.gz` preserve SmartXFlow's actually stored history exactly.

Do not rewrite timestamps/values or relabel evidence:
- 1X2 history stays 1X2 history;
- O/U2.5 stays O/U2.5;
- BTTS stays BTTS.

For a DC/handicap/alternative-total final prediction:
- record the execution market/selection in prediction metadata;
- use underlying native SXF history only as evidence;
- explicitly mark native execution-line history unavailable when SmartXFlow does not store it;
- never fabricate or relabel native rows as execution-market history.

## Evidence archive and PRE/POST cutoff

`evidence.json` stores external research actually used/considered. Each item requires source identity, mandatory `observed_at`, factual note, relationship to thesis, and URL/publication time when available.

A real externally observed execution-market price is also evidence and must preserve source + observation time.

PRE iff `observed_at <= prediction_at`; otherwise POST. Publication time does not override actual observation time.

Original evidence is immutable after record. Corrections/later evidence are append-only.

## Settlement archive

`settlement.json` records result/review fields such as final score, HT score when relevant, WIN/LOSS/VOID, closing odds when available, CLV, P/L/ROI convention, price movement and postmortem classification.

For WATCH, preserve the original WATCH decision and evaluate any selection result hypothetically without retroactively converting it into BET.

For a conditional threshold that never received a verified qualifying price, settlement/postmortem must not pretend execution occurred.

## Postmatch learning-note standard

Every settled formal BET/WATCH receives a timestamped append-only learning note containing:
- `observed_at`, `case_id`, actual result/final score and type (`OBSERVATION` or `RESEARCH_CANDIDATE` only);
- WATCH outcomes labeled hypothetical;
- final available prematch native SXF state relevant to the thesis;
- for non-native execution markets, the real final execution price if actually observed, otherwise explicit `unavailable_reason`;
- prediction-time -> final-prematch comparison including late reversal/divergence;
- whether Stage 2 context remained supportive/contradictory/unexplained;
- lesson about the original thesis and strongest counterargument;
- any proposed new rule only as `RESEARCH_CANDIDATE`.

One case never promotes a production rule.

## Manifest / checksums / DONE

`manifest.jsonl` is append-only with current event types `RECORDED`, `CAPTURED`, `FINALIZED`.

A case is `DONE` only when immutable original prediction/evidence exist, required selected-match native SXF captures exist, settlement/review and standardized postmatch note exist as applicable, validator/checksums pass, and durable GitHub archive commit/reference is confirmed.

Anything less remains explicit pending/failed/retryable.

## Secret exclusion

No archive payload may contain API keys, auth/access/refresh tokens, cookies/session identifiers, Authorization headers, passwords, private keys, `.env` values, database credentials or equivalent secrets.

## Retention

Retention protection is separate from archive durability. Never claim retention is active unless its approved migration/configuration is actually active.

## Access by role

- Predictor creates/records/revisits/settles selected formal cases and preserves native thesis + final execution-market distinction.
- Development reads the same archive, validates integrity and builds PRE-only datasets/models without rewriting historical truth.
- No separate Collector Agent or Match Analyst Agent exists.
