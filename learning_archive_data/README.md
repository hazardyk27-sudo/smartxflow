# SmartXFlow Learning Archive

Shared append-only evidence store for selected Predictor cases.

Storage lives inside the existing `hazardyk27-sudo/smartxflow` repository on the dedicated `learning-archive` data branch under `learning_archive_data/`. No separate repository and no archive-specific GitHub token are part of the architecture.

## Workflow

- Predictor archives only materially researched formal `BET`, `WATCH`, or `PASS` cases.
- First durable record writes immutable `case.json`, `evidence.json`, and `captures/<observed_at>.json.gz`, then appends a `RECORDED` manifest event.
- Prematch revisits append new captures plus `CAPTURED` events; older captures are never overwritten.
- Settlement adds `settlement.json`, final `sxf_snapshots.json.gz`, deterministic `checksums.sha256`, and a `FINALIZED` event.
- Existing SmartXFlow systems remain the market-data collector. This archive never runs a second scraper.
- Development reads this same folder for integrity checks, PRE-only datasets, features and model testing.
- Historical prediction truth is immutable. Corrections are append-only addenda/versioned records.
- Poly/Polymarket data and all secrets/credentials are excluded.
- A runtime/worktree-only file write is not durable. `DONE` requires a verified GitHub commit/reference on this data branch.

## Layout

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

`manifest.jsonl` is an append-only event index. Identical reruns are idempotent. A same case/event key with materially different historical content must fail closed.
