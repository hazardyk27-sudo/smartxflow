from __future__ import annotations

from dataclasses import asdict
from datetime import datetime
import gzip
import hashlib
import json
import os
from pathlib import Path
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

from predictor_policy.stage_comparison import compare_stage_preferences, summarize_comparisons

from .github_backend import GitHubArchiveBackend, GitSshArchiveBackend
from .postmatch_learning import build_postmatch_learning_note


_REPOSITORY = "hazardyk27-sudo/smartxflow"


class PostmatchDiaryError(RuntimeError):
    pass


def _parse_dt(value: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(raw)
    except ValueError as exc:
        raise PostmatchDiaryError("invalid diary timestamp") from exc
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise PostmatchDiaryError("diary timestamp must include timezone")
    return parsed


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise PostmatchDiaryError(f"cannot read {path.name}") from exc


def _read_snapshots(path: Path) -> list[dict[str, Any]]:
    try:
        with gzip.open(path, "rt", encoding="utf-8") as handle:
            value = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        raise PostmatchDiaryError("cannot read finalized SXF snapshots") from exc
    if not isinstance(value, list) or not value:
        raise PostmatchDiaryError("finalized SXF snapshots are empty")
    return value


def _manifest_latest(archive_root: Path) -> dict[str, dict[str, Any]]:
    path = archive_root / "learning_archive_data" / "manifest.jsonl"
    if not path.is_file():
        raise PostmatchDiaryError("Learning Archive manifest is missing")
    latest: dict[str, dict[str, Any]] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PostmatchDiaryError("Learning Archive manifest is invalid") from exc
        if not isinstance(row, dict):
            raise PostmatchDiaryError("Learning Archive manifest row is invalid")
        case_id = str(row.get("case_id") or "").strip()
        if case_id:
            latest[case_id] = row
    return latest


def _comparison(case: dict[str, Any], settlement: dict[str, Any]) -> dict[str, Any]:
    prediction = case.get("prediction") if isinstance(case.get("prediction"), dict) else {}
    baseline = prediction.get("stage1_baseline")
    if not isinstance(baseline, dict):
        return {
            "status": "UNRESOLVED",
            "reason": "Frozen Stage 1 baseline is unavailable for this historical case.",
        }
    market = str(baseline.get("market") or "").strip()
    selection = str(baseline.get("selection") or "").strip()
    if not market or not selection:
        return {
            "status": "UNRESOLVED",
            "reason": "Frozen Stage 1 baseline market/selection is incomplete.",
        }
    final_score = str(settlement.get("final_score") or "").strip()
    if not final_score:
        raise PostmatchDiaryError("settlement final_score is missing")
    stage3_pref = {
        "market": prediction.get("market"),
        "selection": prediction.get("selection"),
        "price": prediction.get("entry_odds"),
    }
    try:
        row = compare_stage_preferences(
            fixture_id=str((case.get("match") or {}).get("match_id_hash") or case.get("case_id") or ""),
            match=case.get("match") or {},
            stage1_preference=baseline,
            stage3_preference=stage3_pref,
            stage3_action=str(prediction.get("decision") or ""),
            final_score=final_score,
            change_driver=str(prediction.get("change_driver") or "NONE"),
        )
    except (ValueError, KeyError) as exc:
        return {"status": "UNRESOLVED", "reason": str(exc)}
    value = asdict(row)
    value["status"] = "RESOLVED"
    return value


def build_postmatch_diary_entry(
    *,
    case: dict[str, Any],
    evidence: list[dict[str, Any]],
    settlement: dict[str, Any],
    snapshots: list[dict[str, Any]],
    observed_at: str,
) -> dict[str, Any]:
    if not isinstance(case, dict) or not isinstance(evidence, list) or not isinstance(settlement, dict):
        raise PostmatchDiaryError("finalized case package is incomplete")
    combined = dict(case)
    combined["evidence"] = evidence
    combined["settlement"] = settlement
    note = build_postmatch_learning_note(combined, snapshots, observed_at=observed_at)
    prediction = combined.get("prediction") or {}
    decision = str(prediction.get("decision") or "").upper()
    outcome = settlement.get("status") if decision == "BET" else settlement.get("hypothetical_result")
    why = (
        f"{note['result_relevance']} {note['stage2_context_check']} "
        f"Final-prematch comparison: {note['prediction_to_final_prematch_comparison']}"
    )
    return {
        "case_id": combined.get("case_id"),
        "prediction_at": prediction.get("prediction_at"),
        "match": combined.get("match") or {},
        "prediction": prediction,
        "settlement": settlement,
        "outcome": outcome,
        "why_it_won_lost": why,
        "stage_comparison": _comparison(combined, settlement),
        "observed_at": observed_at,
    }


def load_finalized_diary_entry(
    archive_root: Path,
    case_id: str,
    *,
    observed_at: str,
) -> dict[str, Any]:
    latest = _manifest_latest(archive_root)
    event = latest.get(str(case_id or "").strip())
    if not event or event.get("event") != "FINALIZED":
        raise PostmatchDiaryError(f"{case_id}: FINALIZED archive receipt is unavailable")
    archive_path = str(event.get("archive_path") or "").strip()
    if not archive_path:
        raise PostmatchDiaryError(f"{case_id}: archive_path is missing")
    case_dir = archive_root / archive_path
    case = _read_json(case_dir / "case.json")
    evidence = _read_json(case_dir / "evidence.json")
    settlement = _read_json(case_dir / "settlement.json")
    snapshots = _read_snapshots(case_dir / "sxf_snapshots.json.gz")
    return build_postmatch_diary_entry(
        case=case,
        evidence=evidence,
        settlement=settlement,
        snapshots=snapshots,
        observed_at=observed_at,
    )


class PostmatchDiaryWriter:
    def __init__(self, *, token: str = "", ssh_key: str = ""):
        self.token = str(token or "").strip()
        self.ssh_key = str(ssh_key or "").strip()
        if not self.token and not self.ssh_key:
            raise PostmatchDiaryError("Learning Archive diary credentials are not configured")

    @classmethod
    def from_env(cls) -> "PostmatchDiaryWriter":
        return cls(
            token=os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip(),
            ssh_key=os.environ.get("LEARNING_ARCHIVE_GIT_SSH_KEY", "").strip(),
        )

    @staticmethod
    def _date_path(entry: dict[str, Any], timezone_name: str) -> str:
        tz = ZoneInfo(timezone_name or "Europe/Istanbul")
        local = _parse_dt(str(entry.get("prediction_at") or "")).astimezone(tz)
        return f"diaries/{local:%Y/%m/%d}/postmatch.md"

    @staticmethod
    def _entry_block(entry: dict[str, Any]) -> str:
        case_id = str(entry.get("case_id") or "")
        match = entry.get("match") or {}
        prediction = entry.get("prediction") or {}
        settlement = entry.get("settlement") or {}
        comparison = entry.get("stage_comparison") or {}
        lines = [
            f"<!-- SXF-POSTMATCH-CASE:{case_id}:BEGIN -->",
            f"### {match.get('home')} – {match.get('away')}",
            f"- Original prediction: **{prediction.get('selection')} | {prediction.get('market')}**",
            f"- Original action: **{prediction.get('decision')}** | confidence: **{prediction.get('confidence')}**",
            f"- prediction_at: `{prediction.get('prediction_at')}`",
            f"- Final score: **{settlement.get('final_score')}**",
            f"- Outcome: **{entry.get('outcome')}**",
            f"- **Why it won/lost:** {entry.get('why_it_won_lost')}",
        ]
        if comparison.get("status") == "RESOLVED":
            s1 = comparison.get("stage1") or {}
            s3 = comparison.get("stage3") or {}
            lines.extend(
                [
                    f"- Stage 1 baseline: **{s1.get('selection')} | {s1.get('market')} → {s1.get('result')}**",
                    f"- Stage 3 final preference: **{s3.get('selection')} | {s3.get('market')} → {s3.get('result')}**",
                    f"- Transition: **{comparison.get('transition')}** | changed: **{comparison.get('preference_changed')}** | driver: **{comparison.get('change_driver')}**",
                ]
            )
        else:
            lines.append(f"- Stage 1 vs Stage 3 comparison: **UNRESOLVED** — {comparison.get('reason')}")
        lines.extend([f"<!-- SXF-POSTMATCH-CASE:{case_id}:END -->", ""])
        return "\n".join(lines)

    @staticmethod
    def _comparison_snapshot(entries: list[dict[str, Any]]) -> str:
        resolved = [entry.get("stage_comparison") for entry in entries if (entry.get("stage_comparison") or {}).get("status") == "RESOLVED"]
        if not resolved:
            return ""
        # Rehydrate only the small dataclass-compatible shape needed by the canonical summary.
        from predictor_policy.stage_comparison import StageComparison, StageOutcome
        rows = []
        for value in resolved:
            rows.append(
                StageComparison(
                    fixture_id=value["fixture_id"],
                    stage1=StageOutcome(**value["stage1"]),
                    stage3=StageOutcome(**value["stage3"]),
                    stage3_action=value["stage3_action"],
                    preference_changed=value["preference_changed"],
                    transition=value["transition"],
                    change_driver=value["change_driver"],
                )
            )
        summary = summarize_comparisons(rows)
        digest = hashlib.sha256(
            json.dumps(summary, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest()[:16]
        return (
            f"<!-- SXF-STAGE-COMPARISON:{digest}:BEGIN -->\n"
            "## Stage 1 vs Stage 3 matched comparison snapshot\n\n"
            f"- Matched cases: **{summary['matched_cases']}**\n"
            f"- Stage 1 hit rate: **{summary['stage1']['hit_rate']}**\n"
            f"- Stage 3 hit rate: **{summary['stage3']['hit_rate']}**\n"
            f"- Hit-rate delta: **{summary['hit_rate_delta']}**\n"
            f"- Changed / unchanged: **{summary['preference_changed']} / {summary['preference_unchanged']}**\n"
            f"- Transitions: `{summary['transitions']}`\n"
            f"- Stage 1 one-unit ROI: `{summary['stage1']['roi']}`\n"
            f"- Stage 3 one-unit ROI: `{summary['stage3']['roi']}`\n"
            f"<!-- SXF-STAGE-COMPARISON:{digest}:END -->\n\n"
        )

    @classmethod
    def _content(cls, existing: str, entries: list[dict[str, Any]]) -> tuple[str, list[str]]:
        changed_ids: list[str] = []
        additions: list[str] = []
        for entry in entries:
            case_id = str(entry.get("case_id") or "").strip()
            if not case_id:
                raise PostmatchDiaryError("postmatch diary entry is missing case_id")
            marker = f"SXF-POSTMATCH-CASE:{case_id}:BEGIN"
            if marker in existing:
                changed_ids.append(case_id)
                continue
            additions.append(cls._entry_block(entry))
            changed_ids.append(case_id)
        if additions:
            additions.append(cls._comparison_snapshot(entries))
        header = "# SmartXFlow Postmatch Diary\n\n" if not existing else ""
        separator = "\n" if existing and not existing.endswith("\n") else ""
        return existing + separator + header + "".join(additions), changed_ids

    def _write_token(self, grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        backend = GitHubArchiveBackend(token=self.token)
        refs: dict[str, str] = {}
        written: list[str] = []
        idempotent = True
        for path, entries in sorted(grouped.items()):
            current = backend._read(path)
            raw, sha = current if current else (b"", None)
            existing = raw.decode("utf-8") if raw else ""
            updated, case_ids = self._content(existing, entries)
            written.extend(case_ids)
            if updated == existing:
                head = backend._head_sha()
                refs[path] = f"https://github.com/{_REPOSITORY}/blob/{head}/learning_archive_data/{path}"
                continue
            idempotent = False
            payload = updated.encode("utf-8")
            if sha:
                backend._update(path, payload, sha, "Append SmartXFlow postmatch diary")
            else:
                backend._put_new(path, payload, "Create SmartXFlow postmatch diary")
            head = backend._head_sha()
            refs[path] = f"https://github.com/{_REPOSITORY}/blob/{head}/learning_archive_data/{path}"
        return {"case_ids": sorted(set(written)), "references": refs, "idempotent": idempotent}

    def _write_ssh(self, grouped: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
        backend = GitSshArchiveBackend(self.ssh_key)
        with tempfile.TemporaryDirectory(prefix="sxf-postmatch-diary-") as tmp:
            repo = Path(tmp) / "repo"
            backend._run([
                "git", "clone", "--quiet", "--single-branch", "--branch", backend.branch,
                "--depth", "1", backend.remote_url, str(repo),
            ])
            changed = False
            written: list[str] = []
            paths: list[str] = []
            for path, entries in sorted(grouped.items()):
                target = repo / "learning_archive_data" / path
                target.parent.mkdir(parents=True, exist_ok=True)
                existing = target.read_text(encoding="utf-8") if target.exists() else ""
                updated, case_ids = self._content(existing, entries)
                written.extend(case_ids)
                paths.append(path)
                if updated != existing:
                    target.write_text(updated, encoding="utf-8")
                    changed = True
            current = backend._run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            if changed:
                backend._run(["git", "add", "-f", "--", "learning_archive_data/diaries"], cwd=repo)
                backend._run(["git", "commit", "--quiet", "-m", "Append SmartXFlow postmatch diary"], cwd=repo)
                current = backend._run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
                backend._run(["git", "push", "--porcelain", "origin", f"HEAD:refs/heads/{backend.branch}"], cwd=repo)
                backend._verify_remote_head(current)
            refs = {
                path: f"https://github.com/{_REPOSITORY}/blob/{current}/learning_archive_data/{path}"
                for path in paths
            }
            return {"case_ids": sorted(set(written)), "references": refs, "idempotent": not changed}

    def write_entries(self, entries: list[dict[str, Any]], *, timezone_name: str = "Europe/Istanbul") -> dict[str, Any]:
        if not entries:
            return {"case_ids": [], "references": {}, "idempotent": True}
        grouped: dict[str, list[dict[str, Any]]] = {}
        for entry in entries:
            grouped.setdefault(self._date_path(entry, timezone_name), []).append(entry)
        for values in grouped.values():
            values.sort(key=lambda item: (str(item.get("prediction_at") or ""), str(item.get("case_id") or "")))
        return self._write_ssh(grouped) if self.ssh_key else self._write_token(grouped)
