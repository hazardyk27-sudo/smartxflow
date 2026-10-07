from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path


class OrchestratorConfigError(RuntimeError):
    pass


def _bool_env(name: str, default: bool) -> bool:
    raw = os.environ.get(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _int_env(name: str, default: int, minimum: int, maximum: int) -> int:
    raw = os.environ.get(name)
    if raw is None:
        return default
    try:
        value = int(raw)
    except ValueError as exc:
        raise OrchestratorConfigError(f"{name} must be an integer") from exc
    if value < minimum or value > maximum:
        raise OrchestratorConfigError(f"{name} must be between {minimum} and {maximum}")
    return value


@dataclass(frozen=True)
class OrchestratorConfig:
    api_key: str
    api_base: str
    model: str
    state_db_path: str
    service_secret: str
    max_attempts: int = 3
    request_timeout_seconds: int = 120
    stage2_web_search: bool = True
    max_output_tokens: int = 12000

    @classmethod
    def from_env(cls, *, require_secrets: bool = True) -> "OrchestratorConfig":
        api_key = os.environ.get("OPENAI_API_KEY", "").strip()
        service_secret = os.environ.get("PREDICTOR_ORCHESTRATOR_SECRET", "").strip()
        if require_secrets and not api_key:
            raise OrchestratorConfigError("OPENAI_API_KEY is required")
        if require_secrets and not service_secret:
            raise OrchestratorConfigError("PREDICTOR_ORCHESTRATOR_SECRET is required")

        db_path = os.environ.get(
            "PREDICTOR_STATE_DB",
            str(Path("data") / "predictor_orchestrator.sqlite3"),
        ).strip()
        if not db_path:
            raise OrchestratorConfigError("PREDICTOR_STATE_DB must not be empty")

        model = os.environ.get("PREDICTOR_LLM_MODEL", "gpt-6.1-sol").strip()
        if not model:
            raise OrchestratorConfigError("PREDICTOR_LLM_MODEL must not be empty")

        return cls(
            api_key=api_key,
            api_base=os.environ.get("OPENAI_API_BASE", "https://api.openai.com/v1").rstrip("/"),
            model=model,
            state_db_path=db_path,
            service_secret=service_secret,
            max_attempts=_int_env("PREDICTOR_MAX_ATTEMPTS", 3, 1, 5),
            request_timeout_seconds=_int_env("PREDICTOR_REQUEST_TIMEOUT", 120, 10, 600),
            stage2_web_search=_bool_env("PREDICTOR_STAGE2_WEB_SEARCH", True),
            max_output_tokens=_int_env("PREDICTOR_MAX_OUTPUT_TOKENS", 12000, 1000, 50000),
        )
