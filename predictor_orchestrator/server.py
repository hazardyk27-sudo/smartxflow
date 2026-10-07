from __future__ import annotations

from functools import wraps
import hmac
import os
from typing import Any, Callable

from flask import Flask, jsonify, request

from .config import OrchestratorConfig, OrchestratorConfigError
from .llm_client import LLMClientError, OpenAIResponsesClient
from .service import (
    OrchestratorError,
    PredictorOrchestrator,
    ValidationExhausted,
)
from .store import SQLiteOrchestratorStore


def _workflow_public(record: Any) -> dict[str, Any]:
    return {
        "workflow_id": record.workflow_id,
        "status": record.status,
        "state": record.state.to_dict(),
        "scope": record.scope,
        "created_at": record.created_at,
        "updated_at": record.updated_at,
    }


def create_app(
    *,
    config: OrchestratorConfig | None = None,
    orchestrator: PredictorOrchestrator | None = None,
) -> Flask:
    cfg = config or OrchestratorConfig.from_env(require_secrets=True)
    if orchestrator is None:
        store = SQLiteOrchestratorStore(cfg.state_db_path)
        llm = OpenAIResponsesClient(cfg)
        orchestrator = PredictorOrchestrator(config=cfg, store=store, llm=llm)

    app = Flask(__name__)
    app.config["JSON_AS_ASCII"] = False

    def require_secret(fn: Callable[..., Any]):
        @wraps(fn)
        def wrapped(*args: Any, **kwargs: Any):
            auth = request.headers.get("Authorization", "")
            expected = f"Bearer {cfg.service_secret}"
            if not cfg.service_secret or not hmac.compare_digest(auth, expected):
                return jsonify({"ok": False, "error": {"code": "UNAUTHORIZED"}}), 401
            return fn(*args, **kwargs)
        return wrapped

    @app.get("/healthz")
    def healthz():
        return jsonify(
            {
                "ok": True,
                "service": "smartxflow-predictor-orchestrator",
                "model": cfg.model,
                "max_attempts": cfg.max_attempts,
            }
        )

    @app.post("/api/predictor/workflows")
    @require_secret
    def create_workflow():
        body = request.get_json(silent=True) or {}
        scope = body.get("scope")
        if not isinstance(scope, dict):
            return jsonify({"ok": False, "error": {"code": "BAD_REQUEST", "message": "scope object is required"}}), 400
        record = orchestrator.create_workflow(scope)
        return jsonify({"ok": True, "workflow": _workflow_public(record)}), 201

    @app.get("/api/predictor/workflows/<workflow_id>")
    @require_secret
    def get_workflow(workflow_id: str):
        record = orchestrator.get_workflow(workflow_id)
        result: dict[str, Any] = {"ok": True, "workflow": _workflow_public(record), "stages": {}}
        for stage in ("STAGE1", "STAGE2", "STAGE3"):
            accepted = orchestrator.store.get_stage_output(workflow_id, stage)
            if accepted:
                result["stages"][stage] = {
                    "stage_run_id": accepted["stage_run_id"],
                    "accepted_at": accepted["accepted_at"],
                    "model": accepted["model"],
                    "policy_version": accepted["policy_version"],
                    "report": accepted["rendered"],
                }
        return jsonify(result)

    @app.post("/api/predictor/workflows/<workflow_id>/prices")
    @require_secret
    def add_price(workflow_id: str):
        body = request.get_json(silent=True) or {}
        try:
            evidence = orchestrator.add_user_price(
                workflow_id=workflow_id,
                market=str(body.get("market") or ""),
                selection=str(body.get("selection") or ""),
                price=float(body.get("price")),
                observed_at=body.get("observed_at"),
                status=str(body.get("status") or "OBSERVED"),
            )
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": {"code": "BAD_REQUEST", "message": "numeric price is required"}}), 400
        return jsonify({"ok": True, "price_evidence": evidence}), 201

    @app.post("/api/predictor/workflows/<workflow_id>/<stage_name>")
    @require_secret
    def run_stage(workflow_id: str, stage_name: str):
        stage_aliases = {"stage1": "STAGE1", "stage2": "STAGE2", "stage3": "STAGE3"}
        stage = stage_aliases.get(stage_name.lower())
        if stage is None:
            return jsonify({"ok": False, "error": {"code": "BAD_STAGE"}}), 404
        body = request.get_json(silent=True) or {}
        if stage in {"STAGE2", "STAGE3"} and body.get("user_authorized") is not True:
            return jsonify(
                {
                    "ok": False,
                    "error": {
                        "code": "USER_AUTHORIZATION_REQUIRED",
                        "message": f"{stage} requires user_authorized=true from the calling UI/workflow",
                    },
                }
            ), 409
        context = body.get("trusted_context")
        if not isinstance(context, dict):
            return jsonify({"ok": False, "error": {"code": "BAD_REQUEST", "message": "trusted_context object is required"}}), 400
        result = orchestrator.run_stage(workflow_id=workflow_id, stage=stage, trusted_context=context)
        return jsonify({"ok": True, **result})

    @app.get("/api/predictor/workflows/<workflow_id>/<stage_name>/attempts")
    @require_secret
    def attempts(workflow_id: str, stage_name: str):
        stage_aliases = {"stage1": "STAGE1", "stage2": "STAGE2", "stage3": "STAGE3"}
        stage = stage_aliases.get(stage_name.lower())
        if stage is None:
            return jsonify({"ok": False, "error": {"code": "BAD_STAGE"}}), 404
        orchestrator.get_workflow(workflow_id)
        # Deliberately excludes raw model payloads. Invalid output never becomes a user-facing response.
        return jsonify({"ok": True, "attempts": orchestrator.store.list_attempts(workflow_id, stage)})

    @app.errorhandler(ValidationExhausted)
    def validation_failed(exc: ValidationExhausted):
        return jsonify(
            {
                "ok": False,
                "error": {
                    "code": exc.code,
                    "message": str(exc),
                    "violations": exc.violations,
                },
            }
        ), exc.status_code

    @app.errorhandler(OrchestratorError)
    def orchestrator_error(exc: OrchestratorError):
        return jsonify({"ok": False, "error": {"code": exc.code, "message": str(exc)}}), exc.status_code

    @app.errorhandler(LLMClientError)
    def llm_error(exc: LLMClientError):
        return jsonify({"ok": False, "error": {"code": "LLM_UPSTREAM_ERROR", "message": str(exc)}}), 502

    return app


def main() -> None:
    try:
        app = create_app()
    except OrchestratorConfigError as exc:
        raise SystemExit(f"predictor orchestrator configuration error: {exc}") from exc
    host = os.environ.get("PREDICTOR_BIND", "127.0.0.1")
    port = int(os.environ.get("PREDICTOR_PORT", "8011"))
    app.run(host=host, port=port, debug=False, threaded=True)


if __name__ == "__main__":
    main()
