#!/usr/bin/env python3
"""Append SmartXFlow signal events and FT settlements to learning-archive."""
from __future__ import annotations

import argparse
from datetime import datetime, timedelta
import json
import os
from pathlib import Path, PurePosixPath
import sys
from urllib.parse import quote

# Running a script by path puts scripts/ first on sys.path, not the repository root.
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import requests

from base_signal_engine.feed import BaseFeedUnavailable, BaseSignalsFeed, TR_TZ
from signal_performance.archive import (
    ARCHIVE_SCHEMA, SignalArchiveError, decode_day, encode_day, merge_feed_day, summarize_day,
)


REPOSITORY = "hazardyk27-sudo/smartxflow"
BRANCH = "learning-archive"
ROOT = "learning_archive_data/signal_engine_performance"
INDEX_PATH = f"{ROOT}/index.json"
MAX_INDEX_BYTES = 2_000_000


class GitHubContents:
    def __init__(self, token: str, session: requests.Session | None = None):
        if not token:
            raise SignalArchiveError("GITHUB_TOKEN is required for durable archive writes")
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "SmartXFlow-Signal-Performance-Archive",
        })

    def read(self, path: str) -> tuple[bytes, str] | None:
        if path.startswith("/") or ".." in PurePosixPath(path).parts or not path.startswith("learning_archive_data/signal_engine_performance/"):
            raise SignalArchiveError("archive path outside signal-performance root")
        url = f"https://api.github.com/repos/{REPOSITORY}/contents/{quote(path, safe='/')}"
        response = self.session.get(url, params={"ref": BRANCH}, timeout=30)
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise SignalArchiveError(f"GitHub archive read failed ({response.status_code})")
        body = response.json()
        content = body.get("content")
        if not isinstance(content, str) or not isinstance(body.get("sha"), str):
            raise SignalArchiveError("GitHub archive read returned an invalid object")
        import base64
        return base64.b64decode(content), body["sha"]

    def write(self, path: str, payload: bytes, *, sha: str | None, message: str) -> str:
        if (path.startswith("/") or ".." in PurePosixPath(path).parts
                or not path.startswith(f"{ROOT}/")):
            raise SignalArchiveError("archive path outside signal-performance root")
        import base64
        url = f"https://api.github.com/repos/{REPOSITORY}/contents/{quote(path, safe='/')}"
        payload_json = {
            "message": message,
            "content": base64.b64encode(payload).decode("ascii"),
            "branch": BRANCH,
        }
        if sha:
            payload_json["sha"] = sha
        response = self.session.put(url, json=payload_json, timeout=45)
        if response.status_code not in (200, 201):
            raise SignalArchiveError(f"GitHub archive write failed ({response.status_code})")
        commit = (response.json().get("commit") or {}).get("sha")
        if not isinstance(commit, str) or len(commit) != 40:
            raise SignalArchiveError("GitHub archive write returned no commit reference")
        return commit


def _read_json(backend: GitHubContents, path: str) -> tuple[dict, str | None]:
    found = backend.read(path)
    if found is None:
        return {}, None
    raw, sha = found
    if len(raw) > MAX_INDEX_BYTES:
        raise SignalArchiveError("signal archive index exceeds size limit")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SignalArchiveError("signal archive index is malformed") from exc
    if not isinstance(value, dict):
        raise SignalArchiveError("signal archive index has an invalid shape")
    return value, sha


def archive(feed: dict, backend: GitHubContents) -> dict:
    if not isinstance(feed, dict) or feed.get("status") != "ok" or not isinstance(feed.get("items"), list):
        raise SignalArchiveError("Base signal feed is incomplete; no archive write attempted")
    existing_index, index_sha = _read_json(backend, INDEX_PATH)
    if existing_index and existing_index.get("schema_version") != ARCHIVE_SCHEMA:
        raise SignalArchiveError("existing signal archive index has an unsupported schema")
    old_days = existing_index.get("days", {}) if existing_index else {}
    if not isinstance(old_days, dict):
        raise SignalArchiveError("existing signal archive day index is malformed")

    start_value = feed.get("start")
    window_days = feed.get("days")
    if (not isinstance(start_value, str) or type(window_days) is not int
            or not 1 <= window_days <= 21):
        raise SignalArchiveError("Base signal feed has an invalid archive window")
    try:
        window_start = datetime.fromisoformat(start_value).date()
    except ValueError as exc:
        raise SignalArchiveError("Base signal feed has an invalid archive start") from exc
    if window_start.isoformat() != start_value:
        raise SignalArchiveError("Base signal feed has a non-canonical archive start")
    by_day: dict[str, list[dict]] = {
        (window_start + timedelta(days=offset)).isoformat(): []
        for offset in range(window_days)
    }
    for item in feed["items"]:
        if not isinstance(item, dict):
            raise SignalArchiveError("Base signal feed contains a malformed row")
        day = item.get("day")
        if not isinstance(day, str) or day not in by_day:
            raise SignalArchiveError("Base signal feed contains a row outside its archive window")
        by_day[day].append(item)

    index_days = dict(old_days)
    changed_days = 0
    appended_events = 0
    final_index = None
    for day in sorted(by_day):
        day_path = f"{ROOT}/days/{day[:4]}/{day[5:7]}/{day[8:10]}.jsonl.gz"
        current = backend.read(day_path)
        previous_events, file_sha = decode_day(current[0]) if current else ([], None)
        merged, changed = merge_feed_day(day, by_day[day], previous_events)
        if changed or current is None:
            prior_count = len(previous_events)
            payload = encode_day(merged)
            commit_sha = backend.write(
                day_path, payload, sha=file_sha,
                message=f"Archive SmartXFlow signal performance {day}",
            )
            changed_days += 1
            appended_events += len(merged) - prior_count
        summary = summarize_day(day, merged)
        if day == datetime.now(TR_TZ).date().isoformat():
            summary["status"] = "IN_PROGRESS"
        index_days[day] = {
            **summary,
            "path": day_path,
            "archive_bytes": len(encode_day(merged)),
            "source_state": feed.get("results_source_state"),
        }

    index = {
        "schema_version": ARCHIVE_SCHEMA,
        "archive_name": "SmartXFlow Signal Performance",
        "repository": REPOSITORY,
        "branch": BRANCH,
        "source": "public.sxf_base_signal_events + identity-checked public.live_fixtures FT results",
        "timezone": "Europe/Istanbul",
        "score_rule": "90-minute normal-time score; extra time and penalties excluded",
        "phase": "SHADOW",
        "source_complete": False,
        "settlement_window_days": 21,
        "engines": feed.get("engines", []),
        "days": {key: index_days[key] for key in sorted(index_days, reverse=True)},
    }
    encoded = (json.dumps(index, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")
    previous_index_bytes = backend.read(INDEX_PATH)
    if previous_index_bytes is None or previous_index_bytes[0] != encoded:
        final_index = backend.write(
            INDEX_PATH, encoded, sha=index_sha if previous_index_bytes else None,
            message="Update SmartXFlow signal performance index",
        )
    else:
        final_index = "UNCHANGED"
    return {
        "status": "ARCHIVED",
        "source_complete": False,
        "days_seen": len(by_day),
        "days_changed": changed_days,
        "events_appended": appended_events,
        "index_commit": final_index,
        "results_source_state": feed.get("results_source_state"),
    }


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description="Append and reconcile daily SmartXFlow signal events/results")
    parser.add_argument("--lookback-days", type=int, default=21)
    args = parser.parse_args(argv)
    if args.lookback_days != 21:
        parser.error("--lookback-days is locked to 21 to reconcile delayed FT results")
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    token = os.environ.get("GITHUB_TOKEN", "").strip()
    if not url or not key or not token:
        print(json.dumps({"status": "STOPPED", "error": "required archive credentials are unavailable"}))
        return 2
    stage = "source_read"
    try:
        start = datetime.now(TR_TZ).date() - timedelta(days=20)
        feed = BaseSignalsFeed(url, key).read(start, days=21)
        stage = "archive_read_write"
        result = archive(feed, GitHubContents(token))
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 0
    except (BaseFeedUnavailable, SignalArchiveError, requests.RequestException, ValueError, TypeError) as exc:
        # Emit only a bounded phase, exception class, and static internal message.
        # Never include response bodies, request URLs, credentials, or raw rows.
        failure = {"status": "STOPPED", "stage": stage, "error_type": type(exc).__name__}
        if isinstance(exc, (BaseFeedUnavailable, SignalArchiveError)):
            failure["reason"] = str(exc)[:160]
        frames = __import__("traceback").extract_tb(exc.__traceback__)
        if frames:
            frame = frames[-1]
            failure["location"] = {
                "file": PurePosixPath(frame.filename).name,
                "function": frame.name,
                "line": frame.lineno,
            }
        print(json.dumps(failure, ensure_ascii=False, sort_keys=True))
        return 1


if __name__ == "__main__":
    sys.exit(main())

