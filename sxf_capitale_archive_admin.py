"""Admin-only CAPITALE SXF archive dispatch. No Supabase writes or GitHub tokens in HTML."""
from __future__ import annotations

import datetime as dt
import hmac
import json
import os
import re
import secrets
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import Request, urlopen
from zoneinfo import ZoneInfo

from flask import Blueprint, jsonify, render_template, request, session

blueprint = Blueprint("sxf_capitale_archive_admin", __name__)
REPO = "hazardyk27-sudo/capitale"
WORKFLOW = "sxf-admin-archive.yml"
BRANCH = "main"
KINDS = {"full_snapshots", "concentrated"}
MIN_DAY = dt.date(2026, 10, 9)


def _admin():
    return session.get("admin_authenticated") is True


def _unlocked():
    return _admin() and session.get("sxf_capitale_archive_unlocked") is True


def _same_origin():
    origin = request.headers.get("Origin")
    if not origin:
        # Browser same-origin JSON POSTs include an Origin header.
        return False
    parsed = urlparse(origin)
    return parsed.scheme in ("https", "http") and parsed.netloc == request.host


def _csrf_ok():
    supplied = request.headers.get("X-CSRF-Token", "")
    expected = session.get("sxf_capitale_archive_csrf", "")
    return bool(expected and supplied) and hmac.compare_digest(supplied, expected)


def _github_request(url: str, method: str = "GET", payload: dict | None = None):
    token = os.environ.get("CAPITALE_GITHUB_ACTIONS_TOKEN", "")
    if not token:
        raise RuntimeError("GITHUB_TOKEN_NOT_CONFIGURED")
    body = json.dumps(payload).encode("utf-8") if payload is not None else None
    headers = {
        "Authorization": "Bearer " + token,
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "SmartXFlow-CAPITALE-Archive-Admin",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    with urlopen(req, timeout=12) as response:
        if method == "POST":
            if response.status != 204:
                raise RuntimeError("UNEXPECTED_GITHUB_DISPATCH_STATUS")
            return {}
        return json.load(response)


@blueprint.route("/admin/sxf-archive", methods=["GET"])
def archive_page():
    if not _admin():
        return render_template("admin_login.html", error="Yönetici oturumu gerekli."), 403
    csrf = session.get("sxf_capitale_archive_csrf")
    if not csrf:
        csrf = secrets.token_urlsafe(32)
        session["sxf_capitale_archive_csrf"] = csrf
    return render_template(
        "admin_sxf_archive.html",
        csrf_token=csrf,
        is_unlocked=_unlocked(),
        authorization_configured=bool(os.environ.get("SXF_ARCHIVE_ADMIN_PIN")),
        github_configured=bool(os.environ.get("CAPITALE_GITHUB_ACTIONS_TOKEN")),
        initial_date="2026-10-09",
        max_date=dt.datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat(),
    )


@blueprint.route("/api/admin/sxf-archive/unlock", methods=["POST"])
def archive_unlock():
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 403
    if not _same_origin() or not _csrf_ok():
        return jsonify(error="CSRF_CHECK_FAILED"), 403
    pin = os.environ.get("SXF_ARCHIVE_ADMIN_PIN", "")
    supplied = (request.get_json(silent=True) or {}).get("pin", "")
    if not pin or len(pin) < 16 or not isinstance(supplied, str):
        return jsonify(error="ARCHIVE_ADMIN_PIN_NOT_CONFIGURED"), 503
    if not hmac.compare_digest(pin, supplied):
        return jsonify(error="INVALID_ARCHIVE_AUTHORIZATION"), 403
    session["sxf_capitale_archive_unlocked"] = True
    session["sxf_capitale_archive_csrf"] = secrets.token_urlsafe(32)
    return jsonify(status="AUTHORIZED", csrf_token=session["sxf_capitale_archive_csrf"])


@blueprint.route("/api/admin/sxf-archive/dispatch", methods=["POST"])
def archive_dispatch():
    if not _unlocked():
        return jsonify(error="ARCHIVE_AUTHORIZATION_REQUIRED"), 403
    if not _same_origin() or not _csrf_ok():
        return jsonify(error="CSRF_CHECK_FAILED"), 403
    data = request.get_json(silent=True) or {}
    day_str = data.get("day")
    kind = data.get("kind")
    if not isinstance(day_str, str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", day_str):
        return jsonify(error="INVALID_DATE"), 400
    try:
        day = dt.date.fromisoformat(day_str)
    except ValueError:
        return jsonify(error="INVALID_DATE"), 400
    if day < MIN_DAY or day > dt.datetime.now(ZoneInfo("Europe/Istanbul")).date():
        return jsonify(error="DATE_OUT_OF_RANGE"), 400
    if kind not in KINDS:
        return jsonify(error="INVALID_ARCHIVE_TYPE"), 400
    if not os.environ.get("CAPITALE_GITHUB_ACTIONS_TOKEN"):
        return jsonify(error="GITHUB_TOKEN_NOT_CONFIGURED"), 503

    # Best-effort duplicate-click protection; GitHub Release tags are the final idempotence guard.
    key = day_str + ":" + kind
    recently = session.get("sxf_capitale_archive_recent", {})
    now = int(time.time())
    if now - int(recently.get(key, 0)) < 120:
        return jsonify(error="ALREADY_REQUESTED_RECENTLY"), 409
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    try:
        _github_request(url, "POST", {
            "ref": BRANCH,
            "inputs": {"day": day_str, "archive_kind": kind},
        })
    except HTTPError as error:
        # Never echo body: GitHub errors may leak internal infrastructure metadata.
        return jsonify(error="GITHUB_DISPATCH_REJECTED", http_status=error.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="GITHUB_CONNECTION_FAILED"), 502
    except RuntimeError as error:
        return jsonify(error=str(error)), 503

    recently[key] = now
    session["sxf_capitale_archive_recent"] = recently
    return jsonify(
        status="QUEUED_NOT_ARCHIVED",
        day=day_str,
        kind=kind,
        actions_url=f"https://github.com/{REPO}/actions/workflows/{WORKFLOW}",
        note="Success requires full GitHub Actions source-to-Release download/hash/restore validation.",
    ), 202


@blueprint.route("/api/admin/sxf-archive/runs", methods=["GET"])
def archive_runs():
    if not _unlocked():
        return jsonify(error="ARCHIVE_AUTHORIZATION_REQUIRED"), 403
    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/runs?per_page=15"
    try:
        data = _github_request(url)
    except HTTPError as error:
        return jsonify(error="GITHUB_STATUS_REJECTED", http_status=error.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="GITHUB_CONNECTION_FAILED"), 502
    except RuntimeError as error:
        return jsonify(error=str(error)), 503
    runs = [
        {
            "title": r.get("display_title", ""),
            "status": r.get("status", ""),
            "conclusion": r.get("conclusion"),
            "created_at": r.get("created_at"),
            "url": r.get("html_url", ""),
        }
        for r in data.get("workflow_runs", [])[:15]
    ]
    return jsonify(runs=runs)
