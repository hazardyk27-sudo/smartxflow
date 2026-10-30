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
RETIRED_ENGINE_KEYS = frozenset({"EARLY_T12", "EARLY_MONEY_T12"})


def _active_engine_map(value):
    if not isinstance(value, dict):
        return {}
    return {name: metric for name, metric in value.items()
            if str(name).strip().upper() not in RETIRED_ENGINE_KEYS}


def _is_retired_engine(value) -> bool:
    return str(value or "").strip().upper() in RETIRED_ENGINE_KEYS


def _filter_retired_report(report: dict) -> dict:
    """Keep the frozen source report intact while omitting retired T-12 from its view."""
    report = dict(report)
    totals = dict(report.get("totals") or {})
    engine_totals = report.get("engine_totals") or {}
    retired = next((metric for name, metric in engine_totals.items()
                    if _is_retired_engine(name)), {})
    report["engine_totals"] = _active_engine_map(engine_totals)
    for field in ("signals", "settled", "canonical_signals"):
        if isinstance(totals.get(field), (int, float)) and isinstance(retired, dict):
            subtract = retired.get("signals" if field != "settled" else "settled", 0)
            if isinstance(subtract, (int, float)):
                totals[field] = max(0, totals[field] - subtract)
    report["totals"] = totals
    clean_days = []
    for entry in report.get("days", []):
        if not isinstance(entry, dict):
            continue
        day = dict(entry)
        engines = day.get("engine") or {}
        retired_day = next((metric for name, metric in engines.items()
                            if _is_retired_engine(name)), {})
        day["engine"] = _active_engine_map(engines)
        for field in ("signals", "settled"):
            if isinstance(day.get(field), (int, float)) and isinstance(retired_day, dict):
                subtract = retired_day.get("signals" if field == "signals" else "settled", 0)
                if isinstance(subtract, (int, float)):
                    day[field] = max(0, day[field] - subtract)
        clean_days.append(day)
    report["days"] = clean_days
    return report


def _filter_retired_runtime_day(day: dict) -> dict:
    clean = dict(day)
    engines = day.get("engines") or {}
    clean_engines = _active_engine_map(engines)
    retired = next((metric for name, metric in engines.items()
                    if _is_retired_engine(name)), {})
    clean["engines"] = clean_engines
    if isinstance(retired, dict) and isinstance(clean.get("logged_events"), (int, float)):
        clean["logged_events"] = max(0, clean["logged_events"] - retired.get("signals", 0))
    clean["settled_signals"] = sum(int(metric.get("settled") or 0)
                                   for metric in clean_engines.values()
                                   if isinstance(metric, dict))
    clean["pending_signals"] = sum(int(metric.get("pending") or 0)
                                   for metric in clean_engines.values()
                                   if isinstance(metric, dict))
    return clean



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
    return _filter_retired_report(value)


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
    days = [_filter_retired_runtime_day(runtime["days"][day]) for day in sorted(runtime["days"], reverse=True)]
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
            settlements = [
                item for item in settlements
                if isinstance(item, dict)
                and not any(_is_retired_engine(engine)
                            for engine in (item.get("engine_tags") or []))
                and not _is_retired_engine(item.get("engine"))
            ]
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
            signals = {event.get("event_id"): event for event in events
                       if event.get("event") == "SIGNAL_RECORDED"
                       and not _is_retired_engine(event.get("engine"))}
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

