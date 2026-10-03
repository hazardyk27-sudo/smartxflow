# SmartXFlow Learning Archive

This folder is the shared evidence store for selected Predictor cases.

Storage lives in the existing `hazardyk27-sudo/smartxflow` repository on the dedicated `learning-archive` branch. No separate repository and no extra GitHub token are required for the conversational Predictor/Development workflow.

## Workflow

- Predictor writes only materially researched formal `BET`, `WATCH`, or `PASS` cases.
- A case is created immediately when the formal decision is published so the original `prediction_at`, market/selection/odds, rationale, counterargument and observed evidence are preserved.
- Existing SmartXFlow systems remain the market-data collector. Do not build a second scraper for this archive.
- When Predictor revisits or settles a selected case, the case record is updated by append-only additions. At settlement/finalization the full available stored prematch SXF history is copied into that case folder.
- Development reads finalized and pending cases from this branch/folder for datasets, feature work and model testing.
- Historical prediction truth is never silently rewritten. Corrections go under `addenda/`.
- Poly/Polymarket data is excluded.
- Secrets, credentials, cookies, auth headers and `.env` values must never be stored here.

## Layout

```text
learning_archive_data/
  manifest.jsonl
  cases/
    YYYY/
      MM/
        DD/
          <case_id>/
            case.json
            evidence.json
            sxf_snapshots.json.gz
            settlement.json
            checksums.sha256
            addenda/
```

`manifest.jsonl` is the case index. Each `case_id` is unique and finalized payloads are immutable/idempotent.
