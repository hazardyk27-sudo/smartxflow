"""Admin-only PRATİK archive dispatch and GitHub Actions status."""
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
MIN_DAY = dt.date(2026, 10, 9)
ISTANBUL = ZoneInfo("Europe/Istanbul")


def _admin():
    return session.get("admin_authenticated") is True


def _same_origin():
    origin = request.headers.get("Origin", "")
    if not origin:
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
        "User-Agent": "SmartXFlow-PRATIK-Archive-Admin",
    }
    if body is not None:
        headers["Content-Type"] = "application/json"
    req = Request(url, data=body, headers=headers, method=method)
    with urlopen(req, timeout=15) as response:
        if method == "POST":
            if response.status != 204:
                raise RuntimeError("UNEXPECTED_GITHUB_DISPATCH_STATUS")
            return {}
        return json.load(response)


def _runs():
    url = (f"https://api.github.com/repos/{REPO}/actions/workflows/"
           f"{WORKFLOW}/runs?per_page=30")
    payload = _github_request(url)
    return payload.get("workflow_runs", []) if isinstance(payload, dict) else []

def _archive_index():
    """Read the public archive index without widening the admin token scope."""
    url = f"https://raw.githubusercontent.com/{REPO}/main/archive/pratik_arsiv/index.json"
    req = Request(url, headers={"User-Agent": "SmartXFlow-PRATIK-Archive-Admin"})
    with urlopen(req, timeout=12) as response:
        return json.load(response)


def _sha256(value):
    return isinstance(value, str) and re.fullmatch(r"[a-f0-9]{64}", value) is not None


def _parse_day(value):
    if not isinstance(value, str) or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", value):
        return None
    try:
        return dt.date.fromisoformat(value)
    except ValueError:
        return None


@blueprint.route("/admin/sxf-archive", methods=["GET"])
def archive_page():
    if not _admin():
        return render_template("admin_login.html", error="Yönetici oturumu gerekli."), 403
    csrf = session.get("sxf_capitale_archive_csrf")
    if not csrf:
        csrf = secrets.token_urlsafe(32)
        session["sxf_capitale_archive_csrf"] = csrf
    yesterday = dt.datetime.now(ISTANBUL).date() - dt.timedelta(days=1)
    oldest_allowed = max(MIN_DAY, yesterday - dt.timedelta(days=3))
    return render_template(
        "admin_sxf_archive.html",
        csrf_token=csrf,
        github_configured=bool(os.environ.get("CAPITALE_GITHUB_ACTIONS_TOKEN")),
        min_date=oldest_allowed.isoformat(),
        max_date=yesterday.isoformat(),
        initial_date=min(yesterday, dt.datetime.now(ISTANBUL).date()).isoformat(),
    )


@blueprint.route("/api/admin/sxf-archive/dispatch", methods=["POST"])
def archive_dispatch():
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 403
    if not _same_origin() or not _csrf_ok():
        return jsonify(error="CSRF_CHECK_FAILED"), 403
    data = request.get_json(silent=True) or {}
    day_str = data.get("day")
    day = _parse_day(day_str)
    latest_complete_day = dt.datetime.now(ISTANBUL).date() - dt.timedelta(days=1)
    oldest_allowed = max(MIN_DAY, latest_complete_day - dt.timedelta(days=3))
    if day is None:
        return jsonify(error="INVALID_DATE"), 400
    if not oldest_allowed <= day <= latest_complete_day:
        return jsonify(error="DATE_OUT_OF_RANGE"), 400
    if not os.environ.get("CAPITALE_GITHUB_ACTIONS_TOKEN"):
        return jsonify(error="GITHUB_TOKEN_NOT_CONFIGURED"), 503

    now = int(time.time())
    recent = session.get("pratik_archive_recent", {})
    if now - int(recent.get(day_str, 0)) < 120:
        return jsonify(error="ALREADY_REQUESTED_RECENTLY", day=day_str), 409
    try:
        active = next((run for run in _runs()
                       if run.get("display_title") == f"PRATİK {day_str}"
                       and run.get("status") in
                       ("queued", "pending", "waiting", "requested", "in_progress")), None)
    except HTTPError as error:
        return jsonify(error="GITHUB_STATUS_REJECTED", http_status=error.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="GITHUB_CONNECTION_FAILED"), 502
    except RuntimeError as error:
        return jsonify(error=str(error)), 503
    if active:
        return jsonify(error="ARCHIVE_ALREADY_RUNNING",
                       day=day_str, run_url=active.get("html_url")), 409

    url = f"https://api.github.com/repos/{REPO}/actions/workflows/{WORKFLOW}/dispatches"
    try:
        _github_request(url, "POST", {"ref": "main", "inputs": {"day": day_str}})
    except HTTPError as error:
        return jsonify(error="GITHUB_DISPATCH_REJECTED", http_status=error.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="GITHUB_CONNECTION_FAILED"), 502
    except RuntimeError as error:
        return jsonify(error=str(error)), 503
    recent[day_str] = now
    session["pratik_archive_recent"] = recent
    return jsonify(
        status="QUEUED_NOT_ARCHIVED",
        day=day_str,
        actions_url=f"https://github.com/{REPO}/actions/workflows/{WORKFLOW}",
        note="Arşiv ancak Action başarıyla tamamlanıp dosyalar ve SHA-256 doğrulanınca hazır sayılır.",
    ), 202


@blueprint.route("/api/admin/sxf-archive/days", methods=["GET"])
def archive_days():
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 403
    try:
        index = _archive_index()
    except HTTPError as error:
        return jsonify(error="ARCHIVE_INDEX_UNAVAILABLE", http_status=error.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="ARCHIVE_INDEX_CONNECTION_FAILED"), 502
    except (ValueError, TypeError, RuntimeError):
        return jsonify(error="INVALID_ARCHIVE_INDEX"), 502

    if index.get("archive_name") != "PRATİK ARŞİV":
        return jsonify(error="INVALID_ARCHIVE_INDEX"), 502
    indexed = {}
    for item in index.get("days", []):
        if isinstance(item, dict) and isinstance(item.get("date"), str):
            indexed[item["date"]] = item

    latest = dt.datetime.now(ISTANBUL).date() - dt.timedelta(days=1)
    count = max(0, (latest - MIN_DAY).days + 1)
    days = []
    for offset in range(count):
        day = latest - dt.timedelta(days=offset)
        if day < MIN_DAY:
            break
        item = indexed.get(day.isoformat())
        if item is None:
            days.append({
                "date": day.isoformat(), "status": "Eksik",
                "fixtures": None, "alarms": None, "bytes": None,
                "source_status": None,
            })
            continue
        checksums = item.get("checksums", {})
        archived = (
            isinstance(item.get("fixtures"), int)
            and isinstance(item.get("alarms"), int)
            and _sha256(checksums.get("checkpoints"))
            and _sha256(checksums.get("alarms"))
        )
        if not archived:
            status = "Kontrol gerekli"
        elif item.get("source_archive_status") == "PARTIAL":
            status = "Arşivlendi · kaynak kısmi"
        else:
            status = "Arşivlendi"
        days.append({
            "date": day.isoformat(), "status": status,
            "fixtures": item.get("fixtures"), "alarms": item.get("alarms"),
            "bytes": item.get("total_bytes"),
            "source_status": item.get("source_archive_status"),
        })
    return jsonify(days=days)


@blueprint.route("/api/admin/sxf-archive/runs", methods=["GET"])
def archive_runs():
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 403
    try:
        runs = _runs()
    except HTTPError as error:
        return jsonify(error="GITHUB_STATUS_REJECTED", http_status=error.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="GITHUB_CONNECTION_FAILED"), 502
    except RuntimeError as error:
        return jsonify(error=str(error)), 503
    return jsonify(runs=[{
        "title": run.get("display_title") or run.get("name") or "PRATİK günlük",
        "status": run.get("status"),
        "conclusion": run.get("conclusion"),
        "created_at": run.get("created_at"),
        "html_url": run.get("html_url"),
    } for run in runs])
