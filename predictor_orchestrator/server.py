from __future__ import annotations

from functools import wraps
import hmac
import os
from typing import Any, Callable

from flask import Flask, jsonify, request

from .config import OrchestratorConfig, OrchestratorConfigError
from .llm_client import LLMClientError, OpenAIResponsesClient
from .service import OrchestratorError, PredictorOrchestrator, ValidationExhausted
from .store import SQLiteOrchestratorStore
from .sxf_source import SXFSourceError, SXFStage1Source


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
    stage1_source: SXFStage1Source | None = None,
) -> Flask:
    cfg = config or OrchestratorConfig.from_env(require_secrets=True, require_api_key=False)
    if orchestrator is None:
        store = SQLiteOrchestratorStore(cfg.state_db_path)
        llm = OpenAIResponsesClient(cfg)
        orchestrator = PredictorOrchestrator(config=cfg, store=store, llm=llm)
    if stage1_source is None:
        stage1_source = SXFStage1Source.from_env_optional()

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
                "external_agent_submit": True,
                "internal_llm_enabled": bool(cfg.api_key),
                "stage1_source_enabled": stage1_source is not None,
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

    @app.post("/api/predictor/workflows/<workflow_id>/stage1/context")
    @require_secret
    def prepare_stage1_context(workflow_id: str):
        if stage1_source is None:
            return jsonify({"ok": False, "error": {"code": "SXF_SOURCE_UNAVAILABLE"}}), 503
        record = orchestrator.get_workflow(workflow_id)
        context = stage1_source.build_stage1_context(record.scope)
        meta = orchestrator.store.save_trusted_context(workflow_id, "STAGE1", context)
        return jsonify(
            {
                "ok": True,
                "stage": "STAGE1",
                "context_sha256": meta["context_sha256"],
                "created_at": meta["created_at"],
                "analysis_context": context,
            }
        )

    @app.get("/api/predictor/workflows/<workflow_id>/stage1/context")
    @require_secret
    def get_stage1_context(workflow_id: str):
        orchestrator.get_workflow(workflow_id)
        stored = orchestrator.store.get_trusted_context(workflow_id, "STAGE1")
        if stored is None:
            return jsonify({"ok": False, "error": {"code": "PREDICTOR_TRUSTED_CONTEXT_REQUIRED"}}), 404
        return jsonify(
            {
                "ok": True,
                "stage": "STAGE1",
                "context_sha256": stored["context_sha256"],
                "created_at": stored["created_at"],
                "analysis_context": stored["context"],
            }
        )

    @app.post("/api/predictor/workflows/<workflow_id>/prices")
    @require_secret
    def add_price(workflow_id: str):
        body = request.get_json(silent=True) or {}
        fixture_id = str(body.get("fixture_id") or "").strip()
        if not fixture_id:
            return jsonify({"ok": False, "error": {"code": "BAD_REQUEST", "message": "fixture_id is required"}}), 400
        try:
            evidence = orchestrator.add_user_price(
                workflow_id=workflow_id,
                fixture_id=fixture_id,
                market=str(body.get("market") or ""),
                selection=str(body.get("selection") or ""),
                price=float(body.get("price")),
                observed_at=body.get("observed_at"),
                status=str(body.get("status") or "OBSERVED"),
            )
        except (TypeError, ValueError):
            return jsonify({"ok": False, "error": {"code": "BAD_REQUEST", "message": "numeric price is required"}}), 400
        return jsonify({"ok": True, "price_evidence": evidence}), 201

    @app.post("/api/predictor/workflows/<workflow_id>/<stage_name>/submit")
    @require_secret
    def submit_generated_stage(workflow_id: str, stage_name: str):
        stage_aliases = {"stage1": "STAGE1", "stage2": "STAGE2", "stage3": "STAGE3"}
        stage = stage_aliases.get(stage_name.lower())
        if stage is None:
            return jsonify({"ok": False, "error": {"code": "BAD_STAGE"}}), 404
        body = request.get_json(silent=True) or {}
        user_authorized = body.get("user_authorized") is True
        if stage in {"STAGE2", "STAGE3"} and not user_authorized:
            return jsonify({"ok": False, "error": {"code": "USER_AUTHORIZATION_REQUIRED"}}), 409
        generated = body.get("generated")
        if not isinstance(generated, dict):
            return jsonify({"ok": False, "error": {"code": "BAD_REQUEST", "message": "generated object is required"}}), 400
        result = orchestrator.submit_generated_stage(
            workflow_id=workflow_id,
            stage=stage,
            generated=generated,
            user_authorized=user_authorized,
            agent_model=str(body.get("agent_model") or "chatgpt-agent-external"),
        )
        return jsonify({"ok": True, **result})

    @app.post("/api/predictor/workflows/<workflow_id>/<stage_name>")
    @require_secret
    def run_stage(workflow_id: str, stage_name: str):
        if not cfg.api_key:
            return jsonify({"ok": False, "error": {"code": "INTERNAL_LLM_DISABLED"}}), 503
        stage_aliases = {"stage1": "STAGE1", "stage2": "STAGE2", "stage3": "STAGE3"}
        stage = stage_aliases.get(stage_name.lower())
        if stage is None:
            return jsonify({"ok": False, "error": {"code": "BAD_STAGE"}}), 404
        body = request.get_json(silent=True) or {}
        user_authorized = body.get("user_authorized") is True
        if stage in {"STAGE2", "STAGE3"} and not user_authorized:
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
        result = orchestrator.run_stage(
            workflow_id=workflow_id,
            stage=stage,
            trusted_context=context,
            user_authorized=user_authorized,
        )
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

    @app.errorhandler(SXFSourceError)
    def sxf_source_error(exc: SXFSourceError):
        return jsonify({"ok": False, "error": {"code": "SXF_SOURCE_ERROR", "message": str(exc)}}), 502

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
