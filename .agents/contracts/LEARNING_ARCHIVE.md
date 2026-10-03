# Learning Archive Contract

CONTRACT_VERSION: 2

## Purpose
The Learning Archive is the permanent historical evidence store for selected SmartXFlow prediction cases. It is not the live SmartXFlow database and it is not a second scraper.

Live/current market data continues to be collected by existing SmartXFlow systems. At end-of-day/settlement, only matches actually materially researched by the Predictor and recorded as formal `BET`, `WATCH`, or `PASS` cases are eligible for export into permanent archive packages. Do not archive the whole daily slate by default.

## Storage target
Canonical target: a dedicated private GitHub repository, intended name `smartxflow-learning-archive`.

The application/source repository must not become the bulk dataset store. Code and agent instructions stay in `hazardyk27-sudo/smartxflow`; finalized historical cases belong in the archive repository.

If storage volume later becomes unsuitable for normal Git, the archive backend may move to object storage without changing this logical contract.

## Canonical instruction source
For the active specialized learning workflow, `PREDICTOR` and `DEVELOPMENT` role instructions and Current Milestones are canonical on the `preview` branch. The root `main:/AGENTS.md` remains the repository/release/safety supplement and must also be respected.

## Package lifecycle
1. Predictor publishes a formal `BET`, `WATCH`, or `PASS` case with immutable `prediction_at`.
2. Existing SmartXFlow systems continue collecting data normally.
3. From the moment a case is selected for learning, the SXF history required to finalize that case must be protected from cleanup/retention until successful archive finalization is verified.
4. Result becomes available and Predictor performs settlement/postmortem where applicable.
5. Exporter reads the existing stored SXF history for that selected match.
6. Exporter builds one final archive package.
7. Validator checks completeness, timing, duplicate/idempotency conditions, secret exclusion and integrity.
8. Package is written to the private archive repository.
9. Manifest/checksums and durable archive path/reference are verified after write.
10. Only after steps 7-9 succeed may the case be marked `DONE`/finalized and any temporary retention protection be released.
11. Package becomes immutable. Corrections are append-only addenda/versioned metadata, never silent rewrites.

Do not continuously mirror all matches into the archive.

## Retention protection
A selected learning case must not lose source history before finalization. The implementation must provide an explicit technical mechanism that prevents cleanup/retention from deleting the required SXF prematch history while the case is pending archival.

- Development owns the technical mechanism and its tests.
- Predictor must surface any case that cannot be safely finalized because source history is incomplete or at risk.
- Retention protection may be released only after validator `PASS`, successful archive write, manifest/checksum verification and durable archive reference confirmation.
- Archive failure must leave the case explicitly pending/failed and retryable; never silently treat a failed export as complete.

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

One `case_id` represents one prediction/decision case. If the same match has multiple materially separate predictions/decisions, each gets its own case ID and references the same canonical match identity.

## Required case metadata
`case.json` must include at minimum:
- `archive_schema_version`
- `case_id`
- canonical `match_id_hash` or successor identity key
- league/home/away/kickoff
- `prediction_at` in UTC
- time-to-kickoff at prediction
- decision: `BET|WATCH|PASS`
- market and selection when applicable
- entry odds when applicable
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
`settlement.json` must include when applicable/available:
- final score,
- HT score if relevant,
- WIN/LOSS/VOID for bet cases,
- closing odds,
- CLV,
- P/L using declared stake convention,
- ROI,
- favorable/adverse post-entry price movement,
- postmortem classification,
- whether failure/success was attributed to process, execution/price, missing/stale data, or normal variance.

For `WATCH`/`PASS`, preserve the decision outcome and enough market/result context to evaluate whether rejecting or delaying the opportunity was justified, without retroactively converting the original decision into a bet.

## Idempotency and duplicate safety
Finalization must be idempotent and duplicate-safe.

- The same `case_id` must not create multiple finalized case directories/manifest entries.
- Re-running export for an already-finalized case with identical payload/checksums must return the existing archive identity/reference rather than create a duplicate.
- A finalized payload must never be overwritten in place.
- If new factual information requires correction, create append-only addenda/versioned metadata with explicit provenance.
- If a re-run produces materially different payload for an already-finalized `case_id`, validator/finalizer must fail closed and require explicit correction/version handling.

## Secret exclusion
No archive payload, evidence item, note, log, manifest or addendum may contain secrets or credentials.

Forbidden examples include:
- API keys,
- auth/access/refresh tokens,
- cookies or session identifiers,
- `Authorization` headers,
- passwords,
- private keys,
- `.env` values,
- database credentials,
- equivalent authentication material.

Keep only non-secret provenance needed for reproducibility. Secret detection/redaction checks should be enforced in exporter/validator tests where practical. If secret material is detected, finalization must fail before GitHub write.

## Integrity and finalization gate
Each finalized case must have deterministic checksums for its payload files. The manifest records case ID, date, match identity, prediction time, decision, settlement status, archive path, schema version and checksum summary.

The validator/finalization flow must fail a case if required fields are missing, prediction/evidence timing is inconsistent, payload checksums fail, PRE data contains evidence first observed after cutoff, duplicate/idempotency rules are violated, required source history is incomplete, or forbidden secret material is detected.

A case is not complete merely because settlement/postmortem exists. `DONE` requires all of the following:
1. deterministic validator `PASS`,
2. successful write to the dedicated archive repository,
3. manifest/checksum verification after write,
4. durable archive path/reference confirmation.

Until all four are true, status must remain explicit pending/failed/retryable.

## Immutability
Finalized archive cases are append-only historical evidence. Do not overwrite a finalized prediction, rationale, result, raw snapshot or evidence timestamp.

If a factual correction is required, add a dated addendum describing exactly what changed and why. Training code must be able to choose whether to use original or corrected metadata explicitly.

## Poly exclusion
Polymarket/Poly trader intelligence must not appear in Learning Archive training inputs, feature generation or model labels for this system. Keep Poly work separate.

## Access by role
- Predictor: creates prediction/evidence/settlement content, flags formal `BET|WATCH|PASS` cases, and triggers final archive export.
- Development: defines exporter/validator, retention protection, idempotency, secret checks and finalization integrity; reads finalized cases; builds datasets/features/models; never rewrites historical truth.
- No separate Collector Agent exists.
