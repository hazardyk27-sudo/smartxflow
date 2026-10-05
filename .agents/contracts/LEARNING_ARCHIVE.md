# Learning Archive Contract

CONTRACT_VERSION: 5

## Purpose

The Learning Archive is the historical evidence store for selected SmartXFlow prediction cases. It is not the live database and is not a second scraper.

Only matches materially researched by Predictor and formalized as `BET` or `WATCH` with a concrete non-empty market and selection are archived as usable prediction cases. Whole-market archiving, no-pick/PASS cases and Poly/Polymarket inputs are excluded from normal prediction datasets/diaries.

Historical legacy `PASS` records may remain physically present for audit/immutability. They must not be silently rewritten or deleted, but default archive iteration/dataset use excludes them.

## Storage target

Canonical storage is inside the existing repository:

- repository: `hazardyk27-sudo/smartxflow`
- data branch: `learning-archive`
- root folder: `/learning_archive_data/`

Do not create or require another repository. Do not require `SMARTXFLOW_LEARNING_ARCHIVE_REPO` or an archive-specific GitHub token. Durable programmatic writes may reuse normal SmartXFlow repository GitHub credentials (`GITHUB_TOKEN`/`GH_TOKEN`) or the authorized GitHub connector.

`preview` remains source development. `main` remains user-approved production. `learning-archive` contains archive data only and is never deployed/promoted.

A file written only to a runtime/worktree is not durable archive truth. Final `DONE` requires a confirmed GitHub commit/reference on the archive data branch.

## Automatic case lifecycle

1. Predictor publishes a formal `BET` or `WATCH` case with immutable `prediction_at`, concrete market/selection, confidence, rationale and counterargument; entry odds are included when applicable.
2. Predictor immediately reads that selected match's already-stored SmartXFlow history through the internal Learning Archive API.
3. The first durable archive operation writes immutable `case.json`, `evidence.json`, and `captures/<observed_at>.json.gz`, then appends a `RECORDED` manifest event.
4. If materially revisited before kickoff, a new deterministic capture is appended with a `CAPTURED` manifest event. Earlier captures are never overwritten.
5. At settlement/end-of-day, Predictor adds `settlement.json`, final full prematch `sxf_snapshots.json.gz`, deterministic `checksums.sha256`, and appends `FINALIZED`.
6. Validator/integrity checks confirm decision/selection policy, timing, secret exclusion, Poly exclusion, checksums and immutable-history rules.
7. Identical retries are idempotent. A same case/event key with different historical content fails closed. Corrections are append-only addenda/versioned records.

No separate user command is required merely to remember/archive a formal selected case.

## Canonical archive layout

```text
learning_archive_data/
  README.md
  manifest.jsonl
  schema/
    match_case_v1.schema.json
  cases/
    YYYY/
      MM/
        DD/
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

One `case_id` represents one prediction/decision case. Separate materially distinct decisions for the same match use separate case IDs but the same canonical match identity.

## Required case metadata

`case.json` must preserve at minimum:
- `archive_schema_version`
- `case_id`
- `match_id_hash`
- league/home/away/kickoff
- immutable `prediction_at` in UTC/offset-aware ISO-8601
- decision `BET|WATCH`
- mandatory non-empty market and selection
- entry odds when applicable
- confidence
- rationale
- counterargument/failure condition
- source SmartXFlow commit/version metadata
- archive creation timestamp

A match with no defensible market/selection is omitted from the final prediction diary/archive rather than represented by `PASS`.

The v1 schema may still recognize historical `PASS` payloads for backward-compatible audit reading; runtime validation for new formal writes is intentionally stricter and accepts only concrete `BET`/`WATCH` prediction cases.

## Snapshot/capture archive

`captures/<observed_at>.json.gz` is append-only SmartXFlow stored history as observed when the case was recorded or materially revisited.

`sxf_snapshots.json.gz` is the final full available prematch SXF timeline at settlement/finalization.

Do not rewrite source snapshot timestamps or values. Preserve source table/market provenance. Existing SmartXFlow systems remain the collector; Learning Archive only copies selected-case stored history.

Double Chance and Draw No Bet history may remain explicitly unavailable until their optional history tables are implemented; absence must be recorded, never fabricated.

## Evidence archive and PRE/POST cutoff

`evidence.json` stores external research actually used/considered. Each item requires source identity, mandatory `observed_at`, factual note, relationship to thesis, and URL/publication time when available.

PRE iff `observed_at <= prediction_at`; otherwise POST. Publication time does not override actual observation time.

Original evidence is immutable after record. Later evidence/corrections must be append-only rather than rewriting historical evidence timing.

## Settlement archive

`settlement.json` records result/review fields such as final score, HT score when relevant, WIN/LOSS/VOID for bet cases, closing odds, CLV, P/L/ROI convention when available, price movement and postmortem classification.

For `WATCH`, preserve the original decision and evaluate the watched selection without retroactively converting it into a bet. Legacy historical `PASS` settlements remain audit-only and are excluded from default usable prediction iteration.

Finalization with settlement status `PENDING` is forbidden.

## Manifest semantics

`manifest.jsonl` is append-only event history, not an in-place mutable row table.

Current event types:
- `RECORDED` — first immutable case + capture
- `CAPTURED` — later append-only prematch capture
- `FINALIZED` — settled/reviewed final package

Each event carries case identity, archive path, prediction/decision identity and deterministic checksum/fingerprint metadata. Identical event reruns are idempotent. Same event key with materially different content is a conflict and fails closed.

## Checksums and DONE gate

Finalized core payloads use deterministic SHA-256 checksums. Development must verify checksums before using a finalized case in a dataset.

A case is not `DONE` merely because files exist locally or settlement was reviewed. `DONE` requires:
1. immutable original case/evidence present,
2. a concrete `BET` or `WATCH` prediction with non-empty market/selection for usable prediction cases,
3. required selected-match history captures present,
4. final settlement/review present,
5. validator PASS,
6. checksum and manifest verification PASS,
7. durable GitHub commit/reference on `learning-archive` confirmed,
8. retention hold release when retention protection is enabled.

Failure remains explicit and retryable.

## Secret exclusion

No payload, manifest event, evidence item, note, capture, log or addendum may contain API keys, auth/access/refresh tokens, cookies/session identifiers, Authorization headers, passwords, private keys, `.env` values, database credentials or equivalent secrets.

## Retention

The retention-hold code/migration may exist, but production migration must not be applied without explicit user permission. Until approved/applied, do not pretend retention protection is active. Archive durability and retention migration are separate gates.

## Access by role

- Predictor creates/records/revisits/settles selected concrete prediction cases automatically as part of its workflow.
- Development reads the same archive, validates integrity and builds PRE-only features/datasets/models; default iteration excludes legacy no-pick/PASS cases and it never rewrites historical truth.
- No separate Collector Agent or Match Analyst Agent exists.
