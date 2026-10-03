from __future__ import annotations

import hmac
import os
import re

from flask import jsonify, request

from .supabase_source import (
    LearningArchiveInvalidHash,
    LearningArchiveMatchNotFound,
    LearningArchiveSourceUnavailable,
    read_learning_archive_match_history,
)


_ENDPOINT_NAME = "learning_archive_internal_match_history"
_ROUTE = "/api/internal/learning-archive/match/<match_id_hash>/history"
_HASH_RE = re.compile(r"^[0-9a-fA-F]{12}$")


def _configured_secret() -> str:
    return os.environ.get("LEARNING_ARCHIVE_ACCESS_SECRET", "").strip()


def _authorize_request() -> tuple[bool, int, str | None]:
    secret = _configured_secret()
    if len(secret) < 32:
        return False, 503, "learning archive access is not configured"

    header = request.headers.get("Authorization", "")
    prefix = "Bearer "
    if not header.startswith(prefix):
        return False, 401, "unauthorized"
    supplied = header[len(prefix):].strip()
    if not supplied or not hmac.compare_digest(supplied, secret):
        return False, 401, "unauthorized"
    return True, 200, None


def register_learning_archive_routes(app) -> bool:
    """Register the read-only server-to-server Learning Archive API once."""
    if _ENDPOINT_NAME in app.view_functions:
        return False

    def learning_archive_match_history(match_id_hash: str):
        authorized, status, error = _authorize_request()
        if not authorized:
            response = jsonify({"error": error})
            response.headers["Cache-Control"] = "no-store"
            return response, status

        match_hash = str(match_id_hash or "").strip().lower()
        if not _HASH_RE.fullmatch(match_hash):
            response = jsonify({"error": "invalid_match_id_hash"})
            response.headers["Cache-Control"] = "no-store"
            return response, 400

        try:
            payload = read_learning_archive_match_history(match_hash)
        except LearningArchiveInvalidHash:
            response = jsonify({"error": "invalid_match_id_hash"})
            response.headers["Cache-Control"] = "no-store"
            return response, 400
        except LearningArchiveMatchNotFound:
            response = jsonify({"error": "match_not_found", "match_id_hash": match_hash})
            response.headers["Cache-Control"] = "no-store"
            return response, 404
        except LearningArchiveSourceUnavailable:
            response = jsonify({"error": "source_unavailable"})
            response.headers["Cache-Control"] = "no-store"
            return response, 503
        except Exception:
            # Fail closed and never expose database/client internals in the response.
            response = jsonify({"error": "source_unavailable"})
            response.headers["Cache-Control"] = "no-store"
            return response, 503

        response = jsonify(payload.as_dict())
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Content-Type-Options"] = "nosniff"
        return response, 200

    app.add_url_rule(
        _ROUTE,
        endpoint=_ENDPOINT_NAME,
        view_func=learning_archive_match_history,
        methods=["GET"],
    )
    return True
