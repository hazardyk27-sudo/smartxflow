from __future__ import annotations

import json
from typing import Any, Protocol

import requests

from .config import OrchestratorConfig


class LLMClientError(RuntimeError):
    pass


class LLMClient(Protocol):
    model: str

    def generate(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]: ...


class OpenAIResponsesClient:
    """Minimal Responses API client with strict Structured Outputs.

    Invalid model output is never returned directly to a user. The orchestrator
    consumes this payload, validates it, and only then renders a public result.
    """

    def __init__(self, config: OrchestratorConfig):
        self.config = config
        self.model = config.model
        self._session = requests.Session()

    @staticmethod
    def _extract_text(body: dict[str, Any]) -> str:
        pieces: list[str] = []
        for item in body.get("output") or []:
            if not isinstance(item, dict) or item.get("type") != "message":
                continue
            for content in item.get("content") or []:
                if not isinstance(content, dict):
                    continue
                if content.get("type") == "refusal":
                    raise LLMClientError("model refused to produce Predictor output")
                if content.get("type") == "output_text" and isinstance(content.get("text"), str):
                    pieces.append(content["text"])
        if not pieces:
            raise LLMClientError("Responses API returned no output_text")
        return "\n".join(pieces).strip()

    def generate(
        self,
        *,
        stage: str,
        system_prompt: str,
        user_prompt: str,
        schema: dict[str, Any],
    ) -> tuple[dict[str, Any], str | None]:
        format_name = f"smartxflow_{stage.lower()}_output"
        request_body: dict[str, Any] = {
            "model": self.model,
            "store": False,
            "max_output_tokens": self.config.max_output_tokens,
            "input": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt},
            ],
            "text": {
                "format": {
                    "type": "json_schema",
                    "name": format_name,
                    "strict": True,
                    "schema": schema,
                }
            },
        }
        if stage.upper() == "STAGE2" and self.config.stage2_web_search:
            request_body["tools"] = [{"type": "web_search"}]
            request_body["tool_choice"] = "auto"

        try:
            response = self._session.post(
                f"{self.config.api_base}/responses",
                headers={
                    "Authorization": f"Bearer {self.config.api_key}",
                    "Content-Type": "application/json",
                },
                json=request_body,
                timeout=self.config.request_timeout_seconds,
            )
        except requests.RequestException as exc:
            raise LLMClientError(f"Responses API request failed: {type(exc).__name__}") from exc

        if response.status_code >= 400:
            request_id = response.headers.get("x-request-id")
            suffix = f" request_id={request_id}" if request_id else ""
            raise LLMClientError(f"Responses API HTTP {response.status_code}{suffix}")

        try:
            body = response.json()
        except ValueError as exc:
            raise LLMClientError("Responses API returned non-JSON body") from exc
        if body.get("status") not in {None, "completed"}:
            raise LLMClientError(f"Responses API status is {body.get('status')!r}")

        text = self._extract_text(body)
        try:
            payload = json.loads(text)
        except json.JSONDecodeError as exc:
            raise LLMClientError("structured model output was not valid JSON") from exc
        if not isinstance(payload, dict):
            raise LLMClientError("structured model output must be a JSON object")
        return payload, body.get("id")
