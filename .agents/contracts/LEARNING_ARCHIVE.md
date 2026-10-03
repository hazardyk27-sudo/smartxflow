# Learning Archive Contract

CONTRACT_VERSION: 1

## Purpose
The Learning Archive is the permanent historical evidence store for selected SmartXFlow prediction cases. It is not the live SmartXFlow database and it is not a second scraper.

Live/current market data continues to be collected by existing SmartXFlow systems. At end-of-day/settlement, only matches actually researched/predicted by the Predictor are exported once into a permanent archive package.

## Storage target
Canonical target: a dedicated private GitHub repository, intended name `smartxflow-learning-archive`.

The application/source repository must not become the bulk dataset store. Code and agent instructions stay in `hazardyk27-sudo/smartxflow`; finalized historical cases belong in the archive repository.

If storage volume later becomes unsuitable for normal Git, the archive backend may move to object storage without changing this logical contract.

## Package lifecycle
1. Predictor publishes a prediction with immutable `prediction_at`.
2. Existing SmartXFlow systems continue collecting data normally.
3. Result becomes available and Predictor performs settlement/postmortem.
4. Exporter reads the existing stored SXF history for that selected match.
5. Exporter builds one final archive package.
6. Validator checks completeness, timing and integrity.
7. Package is written to the private archive repository.
8. Package becomes immutable. Corrections are append-only addenda/versioned metadata, never silent rewrites.

Do not continuously mirror all matches into the archive.

## Canonical archive layout
Recommended repository structure:

```text
smartxflow-learning-archive/
  README.md
  manifest.jsonl
  schema/
    match_case_v1.schema.json
  cases/
    2026/
      10/
        03/
          <case_id>/
            case.json
            sxf_snapshots.json.gz
            evidence.json
            settlement.json
            checksums.sha256
            addenda/
```

One `case_id` represents one prediction case. If the same match has multiple materially separate predictions, each prediction gets its own case ID and references the same canonical match identity.

## Required case metadata
`case.json` must include at minimum:
- `archive_schema_version`
- `case_id`
- canonical `match_id_hash` or successor identity key
- league/home/away/kickoff
- `prediction_at` in UTC
- time-to-kickoff at prediction
- decision: `BET|WATCH|PASS`
- market and selection
- entry odds
- confidence/calibration field if used
- original rationale
- counterargument/failure condition
- source SmartXFlow commit/version metadata when available
- archive created/finalized timestamps

## Snapshot archive
`sxf_snapshots.json.gz` contains the full available prematch SXF timeline for the selected match at export time, preserving original timestamps and values.

Do not rewrite snapshot timestamps or values for convenience. Keep source table/market identifiers or enough provenance to reconstruct their origin.

The archive must support deriving, when data exists:
- opening/current movement,
- 15m/30m/60m/180m money deltas,
- odds movement/velocity,
- money velocity/acceleration,
- price reaction after money flow,
- divergence,
- liquidity/volume path,
- reversal/momentum,
- cross-market relations.

## Evidence archive
`evidence.json` stores external research items actually used or considered.

Each item must include:
- source identity/name,
- URL or stable source reference when available,
- `published_at` when known,
- mandatory `observed_at`,
- evidence type/category,
- short factual note,
- whether it supported, contradicted or was neutral to the thesis.

For PRE/POST classification, `observed_at <= prediction_at` is PRE. Otherwise it is POST regardless of publication time.

## Settlement archive
`settlement.json` must include when available:
- final score,
- HT score if relevant,
- WIN/LOSS/VOID,
- closing odds,
- CLV,
- P/L using declared stake convention,
- ROI,
- favorable/adverse post-entry price movement,
- postmortem classification,
- whether failure/success was attributed to process, execution/price, missing/stale data, or normal variance.

## Integrity
Each finalized case must have deterministic checksums for its payload files. The manifest records case ID, date, match identity, prediction time, decision, settlement status, archive path, schema version and checksum summary.

The validator must fail a case if required fields are missing, prediction/evidence timing is inconsistent, payload checksums fail, or PRE data contains evidence first observed after cutoff.

## Immutability
Finalized archive cases are append-only historical evidence. Do not overwrite a finalized prediction, rationale, result, raw snapshot or evidence timestamp.

If a factual correction is required, add a dated addendum describing exactly what changed and why. Training code must be able to choose whether to use original or corrected metadata explicitly.

## Poly exclusion
Polymarket/Poly trader intelligence must not appear in Learning Archive training inputs, feature generation or model labels for this system. Keep Poly work separate.

## Access by role
- Predictor: creates prediction/evidence/settlement content and triggers final archive export.
- Development: defines exporter/validator, reads finalized cases, builds datasets/features/models, never rewrites historical truth.
- No separate Collector Agent exists.
