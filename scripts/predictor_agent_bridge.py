#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import sys
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener


DEFAULT_ENV_FILE = Path("/var/lib/smartxflow-predictor/predictor-orchestrator.env")
DEFAULT_BASE_URL = "http://127.0.0.1:8011"
MAX_REQUEST_BYTES = 8 * 1024 * 1024
MAX_RESPONSE_BYTES = 32 * 1024 * 1024
WORKFLOW_RE = re.compile(r"^pred_[0-9]{8}T[0-9]{6}_[0-9a-f]{10}$")
STAGE_ALIASES = {"STAGE1": "stage1", "STAGE2": "stage2", "STAGE3": "stage3"}


class BridgeError(RuntimeError):
    pass


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: ANN001
        return None


_OPENER = build_opener(NoRedirect)


def _read_secret(env_file: Path | None = None) -> str:
    direct = os.environ.get("PREDICTOR_ORCHESTRATOR_SECRET", "").strip()
    if direct:
        return direct

    path = env_file or Path(os.environ.get("PREDICTOR_BRIDGE_ENV_FILE", str(DEFAULT_ENV_FILE)))
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise BridgeError(f"orchestrator credential file is unavailable: {path}") from exc

    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        if key.strip() == "PREDICTOR_ORCHESTRATOR_SECRET":
            secret = value.strip().strip('"').strip("'")
            if secret:
                return secret
    raise BridgeError("PREDICTOR_ORCHESTRATOR_SECRET is missing from the server-side credential file")


def _base_url() -> str:
    raw = os.environ.get("PREDICTOR_BRIDGE_ORCHESTRATOR_URL", DEFAULT_BASE_URL).strip().rstrip("/")
    parsed = urlparse(raw)
    if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise BridgeError("bridge target must be an HTTP loopback orchestrator URL")
    if parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise BridgeError("bridge target URL may not contain credentials, query or fragment")
    return raw


def _safe_workflow_id(value: Any) -> str:
    workflow_id = str(value or "").strip()
    if not WORKFLOW_RE.fullmatch(workflow_id):
        raise BridgeError("invalid workflow_id")
    return workflow_id


def _read_json_response(response) -> dict[str, Any]:  # noqa: ANN001
    data = response.read(MAX_RESPONSE_BYTES + 1)
    if len(data) > MAX_RESPONSE_BYTES:
        raise BridgeError("orchestrator response exceeded the bridge size limit")
    try:
        parsed = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("orchestrator returned non-JSON data") from exc
    if not isinstance(parsed, dict):
        raise BridgeError("orchestrator response must be a JSON object")
    return parsed


def _request_json(method: str, path: str, *, secret: str, body: dict[str, Any] | None = None) -> dict[str, Any]:
    url = f"{_base_url()}{path}"
    data = None if body is None else json.dumps(body, separators=(",", ":"), ensure_ascii=False).encode("utf-8")
    if data is not None and len(data) > MAX_REQUEST_BYTES:
        raise BridgeError("bridge request exceeded the size limit")
    headers = {"Accept": "application/json", "Authorization": f"Bearer {secret}"}
    if data is not None:
        headers["Content-Type"] = "application/json"
    request = Request(url, data=data, headers=headers, method=method)
    try:
        with _OPENER.open(request, timeout=60) as response:
            return _read_json_response(response)
    except HTTPError as exc:
        try:
            payload = _read_json_response(exc)
        except BridgeError:
            payload = {}
        error = payload.get("error") if isinstance(payload.get("error"), dict) else {}
        code = str(error.get("code") or f"HTTP_{exc.code}")
        message = str(error.get("message") or "orchestrator request failed")
        raise BridgeError(f"{code}: {message}") from exc
    except URLError as exc:
        raise BridgeError("production orchestrator is unreachable on loopback") from exc


def _stage_name(value: Any) -> tuple[str, str]:
    stage = str(value or "").upper().strip()
    alias = STAGE_ALIASES.get(stage)
    if alias is None:
        raise BridgeError("stage must be STAGE1, STAGE2 or STAGE3")
    return stage, alias


def _verified_submit(request_body: dict[str, Any], *, secret: str) -> dict[str, Any]:
    workflow_id = _safe_workflow_id(request_body.get("workflow_id"))
    stage, alias = _stage_name(request_body.get("stage"))
    generated = request_body.get("generated")
    if not isinstance(generated, dict):
        raise BridgeError("generated must be an object")
    user_authorized = request_body.get("user_authorized") is True
    if stage in {"STAGE2", "STAGE3"} and not user_authorized:
        raise BridgeError(f"{stage} requires explicit user_authorized=true")

    submitted = _request_json(
        "POST",
        f"/api/predictor/workflows/{workflow_id}/{alias}/submit",
        secret=secret,
        body={
            "generated": generated,
            "user_authorized": user_authorized,
            "agent_model": str(request_body.get("agent_model") or "chatgpt-agent-bridge")[:128],
        },
    )
    if submitted.get("ok") is not True:
        raise BridgeError("orchestrator submit returned ok=false")
    stage_run_id = str(submitted.get("stage_run_id") or "").strip()
    if not stage_run_id:
        raise BridgeError("orchestrator submit returned no stage_run_id")

    readback = _request_json("GET", f"/api/predictor/workflows/{workflow_id}", secret=secret)
    stages = readback.get("stages") if isinstance(readback.get("stages"), dict) else {}
    accepted = stages.get(stage) if isinstance(stages.get(stage), dict) else {}
    accepted_run_id = str(accepted.get("stage_run_id") or "").strip()
    accepted_at = str(accepted.get("accepted_at") or "").strip()
    if accepted_run_id != stage_run_id or not accepted_at:
        raise BridgeError("production store readback did not confirm the accepted stage")

    result = dict(submitted)
    result["bridge_receipt"] = {
        "status": "ACCEPTED_PERSISTED",
        "workflow_id": workflow_id,
        "stage": stage,
        "stage_run_id": stage_run_id,
        "accepted_at": accepted_at,
        "policy_version": accepted.get("policy_version"),
        "verification": "PRODUCTION_STORE_READBACK",
        "transport": "HETZNER_LOCAL_AGENT_BRIDGE",
    }
    return result


def dispatch(request_body: dict[str, Any], *, secret: str | None = None) -> dict[str, Any]:
    if not isinstance(request_body, dict):
        raise BridgeError("request must be a JSON object")
    action = str(request_body.get("action") or "").strip().lower()
    if not action:
        raise BridgeError("action is required")

    secret = secret or _read_secret()

    if action == "health":
        return _request_json("GET", "/healthz", secret=secret)
    if action == "create_workflow":
        scope = request_body.get("scope")
        if not isinstance(scope, dict):
            raise BridgeError("scope must be an object")
        return _request_json("POST", "/api/predictor/workflows", secret=secret, body={"scope": scope})

    workflow_id = _safe_workflow_id(request_body.get("workflow_id"))
    if action == "get_workflow":
        return _request_json("GET", f"/api/predictor/workflows/{workflow_id}", secret=secret)
    if action == "prepare_stage1_context":
        return _request_json("POST", f"/api/predictor/workflows/{workflow_id}/stage1/context", secret=secret, body={})
    if action == "get_stage1_context":
        return _request_json("GET", f"/api/predictor/workflows/{workflow_id}/stage1/context", secret=secret)
    if action == "add_price":
        body = {
            "fixture_id": str(request_body.get("fixture_id") or "").strip(),
            "market": str(request_body.get("market") or "").strip(),
            "selection": str(request_body.get("selection") or "").strip(),
            "price": request_body.get("price"),
            "observed_at": request_body.get("observed_at"),
            "status": str(request_body.get("status") or "OBSERVED"),
        }
        if not body["fixture_id"] or not body["market"] or not body["selection"]:
            raise BridgeError("fixture_id, market and selection are required for add_price")
        if not isinstance(body["price"], (int, float)) or isinstance(body["price"], bool):
            raise BridgeError("numeric price is required for add_price")
        return _request_json("POST", f"/api/predictor/workflows/{workflow_id}/prices", secret=secret, body=body)
    if action == "submit_stage":
        return _verified_submit(request_body, secret=secret)

    raise BridgeError(f"unsupported bridge action: {action}")


def _load_request(path: str) -> dict[str, Any]:
    if path == "-":
        raw = sys.stdin.buffer.read(MAX_REQUEST_BYTES + 1)
    else:
        try:
            with open(path, "rb") as handle:
                raw = handle.read(MAX_REQUEST_BYTES + 1)
        except OSError as exc:
            raise BridgeError(f"request file is unavailable: {path}") from exc
    if len(raw) > MAX_REQUEST_BYTES:
        raise BridgeError("bridge input exceeded the size limit")
    try:
        payload = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise BridgeError("request input must be valid UTF-8 JSON") from exc
    if not isinstance(payload, dict):
        raise BridgeError("request input must be a JSON object")
    return payload


def main() -> int:
    parser = argparse.ArgumentParser(description="Secure local bridge for production Predictor external-agent submissions")
    parser.add_argument("--request-file", default="-", help="JSON request file or '-' for stdin")
    parser.add_argument("--pretty", action="store_true")
    args = parser.parse_args()
    try:
        result = dispatch(_load_request(args.request_file))
    except BridgeError as exc:
        print(json.dumps({"ok": False, "error": {"code": "PREDICTOR_AGENT_BRIDGE_ERROR", "message": str(exc)}}, ensure_ascii=False))
        return 1
    print(json.dumps(result, ensure_ascii=False, indent=2 if args.pretty else None, sort_keys=args.pretty))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
