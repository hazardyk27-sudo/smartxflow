# Learning Archive Contract

CONTRACT_VERSION: 3

## Purpose
The Learning Archive is the historical evidence store for selected SmartXFlow prediction cases. It is not the live SmartXFlow database and it is not a second scraper.

Live/current market data continues to be collected by existing SmartXFlow systems. Only matches actually materially researched by Predictor and recorded as formal `BET`, `WATCH`, or `PASS` cases are archived for learning. Do not archive the whole daily slate by default.

## Storage target
Canonical target: the existing `hazardyk27-sudo/smartxflow` repository, dedicated branch `learning-archive`, root folder `/learning_archive_data/`.

Do not create or require a separate archive repository. Do not require an extra archive GitHub token for the conversational Predictor/Development workflow. Archive writes never go to `main` or `preview` and never participate in deployment.

## Canonical instruction source
For the active specialized learning workflow, `PREDICTOR` and `DEVELOPMENT` role instructions and Current Milestones are canonical on the `preview` branch. The root `main:/AGENTS.md` remains the repository/release/safety supplement and must also be respected.

## Automatic case lifecycle
1. Predictor publishes a formal `BET`, `WATCH`, or `PASS` case with immutable `prediction_at`.
2. As part of completing that prediction task, Predictor immediately creates the case under `learning-archive:/learning_archive_data/cases/YYYY/MM/DD/<case_id>/` and writes the immutable prediction/evidence record.
3. Predictor also preserves a current capture of the already-stored SmartXFlow history for that selected match. This is a copy of existing stored data, not a second market-data collector.
4. If the selected case is materially revisited before kickoff, append a new timestamped history capture. Never overwrite an earlier capture.
5. At settlement/end-of-day, Predictor adds result/postmortem and a final full available prematch SXF history capture.
6. Validator/integrity checks confirm timing, secret exclusion, checksums and immutable history rules.
7. `manifest.jsonl` is updated with the final case identity/path/status.
8. Finalized payload becomes immutable. Corrections are append-only addenda/versioned metadata.

No separate user command should be required merely to remember/archive a formal selected case.

## Canonical archive layout

```text
learning_archive_data/
  README.md
  manifest.jsonl
  cases/
    2026/
      10/
        04/
          <case_id>/
            case.json
            evidence.json
            captures/
              <observed_at>.json.gz
            sxf_snapshots.json.gz
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

## Snapshot/capture archive
`captures/<observed_at>.json.gz` stores append-only SmartXFlow history as observed when the selected case was recorded or materially revisited.

`sxf_snapshots.json.gz` stores the final full available prematch SXF timeline for the selected match at settlement/finalization time.

Do not rewrite source snapshot timestamps or values. Keep source table/market identifiers or enough provenance to reconstruct origin.

The archive should support deriving, when source data exists:
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

For `WATCH`/`PASS`, preserve the original decision outcome and enough market/result context to evaluate whether rejecting or delaying the opportunity was justified, without retroactively converting the original decision into a bet.

## Idempotency and duplicate safety
- The same `case_id` must not create multiple case directories/manifest entries.
- Re-running an identical write must be safe/idempotent.
- Finalized prediction/evidence/history/settlement payloads are never overwritten in place.
- New factual corrections require append-only addenda/versioned metadata.
- A materially different rewrite for an existing finalized `case_id` must fail closed or be stored explicitly as an addendum/version.

## Secret exclusion
No archive payload, evidence item, note, log, manifest, capture or addendum may contain secrets or credentials.

Forbidden examples include API keys, auth/access/refresh tokens, cookies/session identifiers, Authorization headers, passwords, private keys, `.env` values, database credentials or equivalent authentication material.

## Integrity and finalization gate
Each finalized case must have deterministic checksums for its payload files. The manifest records case ID, date, match identity, prediction time, decision, settlement status, archive path, schema version and checksum summary.

A case is not `DONE` merely because settlement/postmortem exists. `DONE` requires:
1. immutable original prediction/evidence present,
2. required selected-match SmartXFlow history captures present,
3. final settlement/review when applicable,
4. validator/integrity checks pass,
5. manifest/checksum verification succeeds,
6. durable path on the `learning-archive` branch is confirmed.

## Immutability
Finalized archive cases are append-only historical evidence. Do not overwrite a finalized prediction, rationale, result, raw snapshot or evidence timestamp.

If a factual correction is required, add a dated addendum describing exactly what changed and why. Training code must be able to choose whether to use original or corrected metadata explicitly.

## Poly exclusion
Polymarket/Poly trader intelligence must not appear in Learning Archive training inputs, feature generation or model labels for this system. Keep Poly work separate.

## Access by role
- Predictor: creates prediction/evidence/settlement content and writes selected cases to `learning-archive:/learning_archive_data/` automatically as part of the workflow.
- Development: reads the same folder, validates integrity and builds datasets/features/models; never rewrites historical truth.
- No separate Collector Agent exists.
