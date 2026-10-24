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
        github_configured=bool(os.environ.get("CAPITALE_GITHUB_ACTIONS_TOKEN")),
        initial_date="2026-10-09",
        max_date=dt.datetime.now(ZoneInfo("Europe/Istanbul")).date().isoformat(),
    )


@blueprint.route("/api/admin/sxf-archive/dispatch", methods=["POST"])
def archive_dispatch():
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 403
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
    # A browser session's 120-second guard cannot prevent duplicate exports
    # when a two-day GitHub Actions batch is running in another session.
    # Refuse a second real dispatch for ANY active workflow covering this day.
    try:
        active = next(
            (r for r in _archive_runs_for_workflows()
             if _run_matches_day(r, day, kind)
             and r.get("status") in ("queued", "pending", "waiting", "requested", "in_progress")),
            None,
        )
    except HTTPError as error:
        return jsonify(error="GITHUB_STATUS_REJECTED", http_status=error.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="GITHUB_CONNECTION_FAILED"), 502
    except RuntimeError as error:
        return jsonify(error=str(error)), 503
    if active:
        return jsonify(error="ARCHIVE_ALREADY_RUNNING",
                       day=day_str, kind=kind,
                       existing_run_url=active.get("html_url")), 409
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


def _archive_runs_for_workflows():
    """All kinds of SXF Actions runs, including two-day batch launches."""
    results = []
    for workflow in ("sxf-admin-archive.yml", "sxf-raw-two-day-batch.yml"):
        endpoint = (f"https://api.github.com/repos/{REPO}/actions/"
                    f"workflows/{workflow}/runs?per_page=30")
        results.extend(_github_request(endpoint).get("workflow_runs", []))
    results.sort(key=lambda r: r.get("created_at", ""), reverse=True)
    return results


def _run_matches_day(run: dict, day: dt.date, kind: str) -> bool:
    title = run.get("display_title", "")
    if title == f"SXF {day} / {kind}":
        return True
    if kind != "full_snapshots":
        return False
    prefix = "SXF full raw "
    if not title.startswith(prefix) or not title.endswith(" + next day"):
        return False
    try:
        first = dt.date.fromisoformat(title[len(prefix): -len(" + next day")])
    except ValueError:
        return False
    return day in (first, first + dt.timedelta(days=1))


@blueprint.route("/api/admin/sxf-archive/progress", methods=["GET"])
def archive_progress():
    """True uploaded-row progress. Never manufacture a percentage or a success."""
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 403
    day_str, kind = request.args.get("day", ""), request.args.get("kind", "")
    if kind not in KINDS or not re.fullmatch(r"20\d{2}-\d{2}-\d{2}", day_str):
        return jsonify(error="INVALID_ARCHIVE_SELECTION"), 400
    try:
        day = dt.date.fromisoformat(day_str)
    except ValueError:
        return jsonify(error="INVALID_ARCHIVE_SELECTION"), 400
    if not MIN_DAY <= day <= dt.datetime.now(ZoneInfo("Europe/Istanbul")).date():
        return jsonify(error="DATE_OUT_OF_RANGE"), 400

    tag = f"sxf-{'raw' if kind == 'full_snapshots' else 'concentrated'}-{day}-v1"
    try:
        runs = _archive_runs_for_workflows()
        candidates = [run for run in runs if _run_matches_day(run, day, kind)]
        # If a duplicate request is pending while the older batch is actually
        # exporting this day, prefer the running job over the queued duplicate.
        matching = next((run for run in candidates if run.get("status") == "in_progress"),
                        candidates[0] if candidates else None)
        release = None
        release_error = None
        try:
            release = _github_request(f"https://api.github.com/repos/{REPO}/releases/tags/{tag}")
        except HTTPError as exc:
            if exc.code == 404:
                release_error = "RELEASE_NOT_FOUND_OR_NOT_VISIBLE"
            elif exc.code == 403:
                release_error = "RELEASE_CONTENTS_READ_PERMISSION_REQUIRED"
            else:
                return jsonify(error="RELEASE_LOOKUP_REJECTED", http_status=exc.code), 502

        # If the second day of a two-day batch has not started, don't label it
        # actively uploading merely because the overall batch is running.
        day_run_status = matching.get("status") if matching else None
        day_run_conclusion = matching.get("conclusion") if matching else None
        if matching and kind == "full_snapshots" and matching.get("display_title", "").startswith("SXF full raw "):
            try:
                jobs = _github_request(
                    f"https://api.github.com/repos/{REPO}/actions/runs/{matching['id']}/jobs?per_page=100"
                ).get("jobs", [])
                title = matching.get("display_title", "")
                first = dt.date.fromisoformat(title[len("SXF full raw "): -len(" + next day")])
                prefix = "first-day" if day == first else "second-day"
                own = next((job for job in jobs if job.get("name", "").startswith(prefix)), None)
                if own:
                    day_run_status, day_run_conclusion = own.get("status"), own.get("conclusion")
                elif day != first:
                    day_run_status, day_run_conclusion = "queued", None
            except (HTTPError, URLError, TimeoutError, ValueError):
                pass

        assets = release.get("assets", []) if release else []
        # The Release detail response may not include every asset in a large
        # 25k-row-chunk export. Read every assets page to avoid undercounting.
        if release and type(release.get("id")) is int:
            assets = []
            for page in range(1, 12):
                batch = _github_request(
                    f"https://api.github.com/repos/{REPO}/releases/{release['id']}/assets"
                    f"?per_page=100&page={page}"
                )
                if not isinstance(batch, list):
                    raise RuntimeError("INVALID_RELEASE_ASSETS_RESPONSE")
                assets.extend(batch)
                if len(batch) < 100:
                    break
            if len(assets) > 1000:
                raise RuntimeError("UNSAFE_RELEASE_ASSET_COUNT")
        total_markers = [
            int(m.group(1))
            for item in assets
            if (m := re.fullmatch(r"progress_total_rows_([1-9]\d*)\.json", item.get("name", "")))
        ]
        expected = total_markers[0] if len(total_markers) == 1 else None
        uploaded = sum(
            int(m.group(1))
            for item in assets
            if (m := re.search(r"_rows_([1-9]\d*)\.jsonl\.gz$", item.get("name", "")))
        )
        receipt = any(item.get("name") == "verification_receipt.json" for item in assets)
        verified = bool(
            receipt and expected is not None and uploaded == expected
            and day_run_status == "completed" and day_run_conclusion == "success"
        )
        if verified:
            status, percent = "DOĞRULANDI", 100
        elif day_run_conclusion in ("failure", "cancelled", "timed_out"):
            status, percent = "BAŞARISIZ", min(99, uploaded * 100 // expected) if expected else None
        elif day_run_status in ("queued", "waiting", "pending"):
            status, percent = "BEKLİYOR", min(99, uploaded * 100 // expected) if expected else None
        elif day_run_status == "in_progress" or release:
            status, percent = "AKTARILIYOR", min(99, uploaded * 100 // expected) if expected else None
        else:
            status, percent = "BEKLİYOR", None
        return jsonify(
            day=day_str, kind=kind, status=status, percent=percent,
            expected_rows=expected, uploaded_rows=uploaded,
            remaining_rows=max(0, expected - uploaded) if expected is not None else None,
            verified=verified, release_tag=tag, release_error=release_error,
            run_url=matching.get("html_url") if matching else None,
            run_status=day_run_status, run_conclusion=day_run_conclusion,
            note=("Tamamlandı yalnız GitHub SHA-256/JSONL geri okuma denetimi ve iş başarısı ile onaylanır."
                  if verified else "Yalnız GitHub'a yüklenen parçalar sayılır; bitmeden yüzde 100 gösterilmez."),
        )
    except HTTPError as exc:
        return jsonify(error="GITHUB_STATUS_REJECTED", http_status=exc.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="GITHUB_CONNECTION_FAILED"), 502
    except RuntimeError as exc:
        return jsonify(error=str(exc)), 503


@blueprint.route("/api/admin/sxf-archive/runs", methods=["GET"])
def archive_runs():
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 403
    try:
        data = _archive_runs_for_workflows()
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
        for r in data[:20]
    ]
    return jsonify(runs=runs)
