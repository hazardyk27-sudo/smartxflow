# SmartXFlow Predictor Orchestrator

This package is the mandatory publication gate for Predictor model output.

## Non-bypassable path

A model response is never a Predictor result by itself.

```text
trusted SmartXFlow/user input
        -> PredictorOrchestrator
        -> strict structured LLM output
        -> authoritative field injection
        -> predictor_policy.validate_and_advance
        -> FAIL: internal audit + bounded repair, never publish
        -> PASS: durable accepted-stage write
        -> deterministic renderer
        -> user-facing report
```

The LLM does **not** own or choose:

- workflow/stage run IDs;
- predecessor IDs;
- Stage 2/Stage 3 user authorization;
- frozen Stage 1 carry-forward state;
- decision timestamps / `prediction_at`;
- `grade -> BET/WATCH/PASS` mapping;
- counter-penalty arithmetic;
- `archive_intent`;
- trusted execution-price provenance;
- publication.

Those fields are injected or derived by the orchestrator and then checked by `predictor_policy`.

## Fail-closed behavior

`ValidationExhausted` means no accepted stage is written and workflow state is not advanced. Invalid LLM payloads are stored only in the internal audit table. The public HTTP API never returns raw invalid output.

A later retry is allowed after the caller fixes missing input/price/context; audit attempt numbers remain append-only and monotonic.

## State

The initial deployment uses one local SQLite WAL database owned by the independent orchestrator service. Accepted stage output and workflow state are committed transactionally. The service is configured as one Gunicorn worker with threads, so one process owns the state machine while still allowing concurrent HTTP I/O.

Production unit:

`deploy/systemd/smartxflow-predictor-orchestrator.service`

Default production bind:

`127.0.0.1:8011`

The orchestrator is intentionally local-only. `PREDICTOR_ORCHESTRATOR_SECRET` is a server-side credential and must never be embedded in browser JavaScript.

## Required environment

- `OPENAI_API_KEY`
- `PREDICTOR_ORCHESTRATOR_SECRET`
- `PREDICTOR_LLM_MODEL` (default currently `gpt-6.1-sol`)

Optional configuration is documented in `deploy/env.template`.

## API

All `/api/predictor/*` routes require:

`Authorization: Bearer <PREDICTOR_ORCHESTRATOR_SECRET>`

Routes:

- `POST /api/predictor/workflows` — create workflow and freeze source request metadata.
- `GET /api/predictor/workflows/<workflow_id>` — accepted state/reports only.
- `POST /api/predictor/workflows/<workflow_id>/prices` — record exact `USER_SUPPLIED` price evidence.
- `POST /api/predictor/workflows/<workflow_id>/stage1` — Stage 1.
- `POST /api/predictor/workflows/<workflow_id>/stage2` — Stage 2; requires `user_authorized=true`.
- `POST /api/predictor/workflows/<workflow_id>/stage3` — Stage 3; requires `user_authorized=true`.
- `GET /api/predictor/workflows/<workflow_id>/<stage>/attempts` — audit status/violations only; raw invalid payload is not exposed.

## Trust boundary

`trusted_context` is server-to-server input. It must be assembled by SmartXFlow backend/data adapters, not accepted directly from an untrusted browser. In particular:

- Stage 1 source fixture IDs/history must come from SmartXFlow data.
- `USER_SUPPLIED` prices must enter through the dedicated `/prices` endpoint and the orchestrator store.
- a caller cannot impersonate `USER_SUPPLIED` merely by putting that origin into `trusted_context`.
- Stage 3 exact alternative prices are accepted only from the authoritative price store or whitelisted trusted price evidence.

## OpenAI integration

The implementation uses the Responses API with strict JSON-schema Structured Outputs. Stage 2 may enable the Responses API web-search tool; Stage 1 never does.

The model receives the canonical policy plus trusted prior-stage data. Validation errors are returned to the model only inside a bounded repair loop. The previous invalid output remains internal.

## Tests

`tests/test_predictor_orchestrator.py` covers:

- invalid-first / valid-second repair;
- validation exhaustion with no state advance;
- safe retry after exhaustion;
- model-price stripping;
- direct-service Stage 2 authorization gate;
- exact stored `USER_SUPPLIED` non-native pricing;
- forged user-price provenance rejection;
- state recovery after store restart;
- HTTP secret enforcement;
- no raw invalid output in public error responses.

CI: `.github/workflows/predictor-policy-tests.yml`.

## Production activation

Source code on `preview` does not activate production. Production requires the normal SmartXFlow release contract and explicit user approval before `preview -> main` / Hetzner deployment.
