"""Admin-only view of historical research reports and durable daily motor records."""
from __future__ import annotations

import gzip
import json
import re
from urllib.error import HTTPError, URLError
from urllib.parse import quote
from urllib.request import Request, urlopen

from flask import Blueprint, jsonify, render_template, session


blueprint = Blueprint("sxf_signal_performance_admin", __name__)
CAPITALE_RAW = "https://raw.githubusercontent.com/hazardyk27-sudo/capitale/main/"
SXF_ARCHIVE_RAW = "https://raw.githubusercontent.com/hazardyk27-sudo/smartxflow/learning-archive/"
HISTORICAL_REPORT = "SXF_arastirma_arsivi/sinyal_performanslari/Sinyal_Performanslari.json"
RUNTIME_INDEX = "learning_archive_data/signal_engine_performance/index.json"
MAX_JSON_BYTES = 2_000_000
DAY_RE = re.compile(r"^20\d{2}-\d{2}-\d{2}$")


def _admin() -> bool:
    return session.get("admin_authenticated") is True


def _read_json(url: str) -> dict:
    req = Request(url, headers={"User-Agent": "SmartXFlow-Signal-Performance-Admin"})
    with urlopen(req, timeout=15) as response:
        raw = response.read(MAX_JSON_BYTES + 1)
    if len(raw) > MAX_JSON_BYTES:
        raise ValueError("remote performance JSON exceeds size limit")
    value = json.loads(raw.decode("utf-8"))
    if not isinstance(value, dict):
        raise ValueError("remote performance JSON has invalid shape")
    return value


def _historical_index() -> dict:
    value = _read_json(CAPITALE_RAW + HISTORICAL_REPORT)
    if value.get("schema_version") != "SXF_MOTOR_PERFORMANCE_V1":
        raise ValueError("unsupported CAPITALE performance report")
    days = value.get("days")
    if not isinstance(days, list) or len(days) > 100:
        raise ValueError("invalid historical report day list")
    return value


def _runtime_index() -> dict:
    try:
        value = _read_json(SXF_ARCHIVE_RAW + RUNTIME_INDEX)
    except HTTPError as error:
        if error.code == 404:
            return {"schema_version": "SXF_SIGNAL_PERFORMANCE_DAY_V1", "days": {}}
        raise
    if value.get("schema_version") != "SXF_SIGNAL_PERFORMANCE_DAY_V1":
        raise ValueError("unsupported runtime signal archive")
    if not isinstance(value.get("days"), dict) or len(value["days"]) > 1000:
        raise ValueError("invalid runtime archive day list")
    return value


@blueprint.route("/admin/signal-performance", methods=["GET"])
def performance_page():
    if not _admin():
        return render_template("admin_login.html", error="Yönetici oturumu gerekli."), 403
    return render_template("admin_signal_performance.html")


@blueprint.route("/api/admin/signal-performance/overview", methods=["GET"])
def performance_overview():
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 401
    historical = None
    history_error = None
    try:
        report = _historical_index()
        historical = {
            "status": report.get("status"),
            "period_start": report.get("period_start_tr"),
            "period_end": report.get("period_end_tr"),
            "generated_at_utc": report.get("generated_at_utc"),
            "mode": report.get("mode"),
            "score_rule": report.get("score_rule"),
            "totals": report.get("totals"),
            "engine_totals": report.get("engine_totals"),
            "days": report.get("days"),
            "warnings": report.get("quality_warnings"),
        }
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError):
        history_error = "CAPITALE tarihsel performans raporu şu an okunamadı."
    try:
        runtime = _runtime_index()
    except (HTTPError, URLError, TimeoutError, ValueError, TypeError):
        return jsonify(error="SIGNAL_ARCHIVE_UNAVAILABLE",
                       history_error=history_error,
                       message="Günlük SmartXFlow sinyal arşivi okunamadı."), 502
    days = [runtime["days"][day] for day in sorted(runtime["days"], reverse=True)]
    return jsonify({
        "historical": historical,
        "historical_error": history_error,
        "runtime": {
            "schema_version": runtime.get("schema_version"),
            "phase": runtime.get("phase", "SHADOW"),
            "source_complete": runtime.get("source_complete", False),
            "score_rule": runtime.get("score_rule"),
            "days": days,
        },
    })


@blueprint.route("/api/admin/signal-performance/day/<source>/<day>", methods=["GET"])
def performance_day(source: str, day: str):
    if not _admin():
        return jsonify(error="ADMIN_REQUIRED"), 401
    if not DAY_RE.fullmatch(day):
        return jsonify(error="INVALID_DATE"), 400
    try:
        if source == "historical":
            report = _historical_index()
            row = next((entry for entry in report["days"] if entry.get("date") == day), None)
            if row is None:
                return jsonify(error="DAY_NOT_FOUND"), 404
            path = row.get("source_file")
            if not isinstance(path, str) or not path.startswith("SXF_arastirma_arsivi/2026/10/") or ".." in path.split("/"):
                return jsonify(error="INVALID_ARCHIVE_REFERENCE"), 502
            detail = _read_json(CAPITALE_RAW + quote(path, safe="/"))
            settlements = detail.get("settlements")
            if not isinstance(settlements, list) or len(settlements) > 5000:
                return jsonify(error="INVALID_ARCHIVE_DAY"), 502
            return jsonify({
                "source": "CAPITALE · tarihsel araştırma",
                "date": day,
                "mode": detail.get("mode") or detail.get("publication_state"),
                "score_rule": detail.get("score_rule") or "90 dakika; uzatma ve penaltılar hariç",
                "summary": row,
                "items": settlements,
                "experimental": detail.get("experimental_shadow_metrics"),
            })
        if source == "runtime":
            index = _runtime_index()
            row = index.get("days", {}).get(day)
            if not isinstance(row, dict):
                return jsonify(error="DAY_NOT_FOUND"), 404
            path = row.get("path")
            expected_prefix = f"learning_archive_data/signal_engine_performance/days/{day[:4]}/{day[5:7]}/"
            if not isinstance(path, str) or not path.startswith(expected_prefix) or ".." in path.split("/") or not path.endswith(".jsonl.gz"):
                return jsonify(error="INVALID_ARCHIVE_REFERENCE"), 502
            req = Request(SXF_ARCHIVE_RAW + quote(path, safe="/"), headers={"User-Agent": "SmartXFlow-Signal-Performance-Admin"})
            with urlopen(req, timeout=15) as response:
                raw = response.read(4_000_001)
            if len(raw) > 4_000_000:
                return jsonify(error="ARCHIVE_DAY_TOO_LARGE"), 502
            try:
                events = [json.loads(line) for line in gzip.decompress(raw).decode("utf-8").splitlines() if line.strip()]
            except (OSError, UnicodeDecodeError, json.JSONDecodeError):
                return jsonify(error="INVALID_ARCHIVE_DAY"), 502
            signals = {event.get("event_id"): event for event in events if event.get("event") == "SIGNAL_RECORDED"}
            statuses = {event.get("event_id"): event for event in events if event.get("event") == "SIGNAL_STATUS_OBSERVED"}
            settlements = {event.get("event_id"): event for event in events if event.get("event") in ("SETTLEMENT_RECORDED", "SETTLEMENT_CORRECTED")}
            items = []
            for event_id, signal in sorted(signals.items(), key=lambda pair: (pair[1].get("kickoff_utc") or "", pair[1].get("engine") or "", pair[0])):
                items.append({**signal, "status": statuses.get(event_id), "settlement": settlements.get(event_id)})
            return jsonify({"source": "SmartXFlow · günlük SHADOW motor kaydı", "date": day,
                            "mode": "SHADOW", "score_rule": index.get("score_rule"),
                            "summary": row, "items": items})
        return jsonify(error="INVALID_SOURCE"), 400
    except HTTPError as error:
        return jsonify(error="ARCHIVE_DAY_UNAVAILABLE", http_status=error.code), 502
    except (URLError, TimeoutError):
        return jsonify(error="ARCHIVE_DAY_CONNECTION_FAILED"), 502
    except (ValueError, TypeError, KeyError):
        return jsonify(error="INVALID_ARCHIVE_DAY"), 502

