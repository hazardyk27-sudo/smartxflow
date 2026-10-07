from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import hashlib
import os
from pathlib import Path
import re
import subprocess
import tempfile
from typing import Any
from zoneinfo import ZoneInfo

from learning_archive.exporter import ArchiveFinalizationError, LearningArchiveExporter
from learning_archive.github_backend import GitHubArchiveBackend, GitSshArchiveBackend
from learning_archive.supabase_source import (
    LearningArchiveSourceError,
    read_learning_archive_match_history,
)


_REPOSITORY = "hazardyk27-sudo/smartxflow"


class ArchivePublicationError(RuntimeError):
    pass


@dataclass(frozen=True)
class DiaryWriteResult:
    status: str
    reference: str
    commit_sha: str
    idempotent: bool


def _parse_dt(value: str) -> datetime:
    raw = str(value or "").strip()
    if raw.endswith("Z"):
        raw = raw[:-1] + "+00:00"
    parsed = datetime.fromisoformat(raw)
    if parsed.tzinfo is None or parsed.utcoffset() is None:
        raise ArchivePublicationError("timestamp must include timezone")
    return parsed


def _runtime_commit() -> str:
    for key in ("SMARTXFLOW_SOURCE_COMMIT", "SMARTXFLOW_RELEASE_SHA", "GITHUB_SHA"):
        value = os.environ.get(key, "").strip()
        if value:
            return value
    repo_root = Path(__file__).resolve().parents[1]
    try:
        value = subprocess.check_output(
            ["git", "rev-parse", "HEAD"],
            cwd=str(repo_root),
            text=True,
            stderr=subprocess.DEVNULL,
            timeout=5,
        ).strip()
    except (OSError, subprocess.SubprocessError):
        value = ""
    return value or "runtime-commit-unavailable"


def _fixture_id(item: dict[str, Any]) -> str:
    return str(item.get("fixture_id") or item.get("fixture_uid") or item.get("match_id_hash") or "").strip()


def _by_fixture(rows: list[dict[str, Any]] | None) -> dict[str, dict[str, Any]]:
    result: dict[str, dict[str, Any]] = {}
    for item in rows or []:
        if isinstance(item, dict) and _fixture_id(item):
            result[_fixture_id(item)] = item
    return result


def _case_id(prediction_at: str, fixture_id: str, market: str, selection: str) -> str:
    date = _parse_dt(prediction_at).astimezone(timezone.utc).strftime("%Y%m%d")
    clean_fixture = re.sub(r"[^a-zA-Z0-9]+", "", fixture_id).lower() or "fixture"
    digest = hashlib.sha256(f"{fixture_id}\n{market}\n{selection}".encode("utf-8")).hexdigest()[:10]
    return f"{date}-{clean_fixture}-{digest}"


def _flatten_history(payload: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    histories = getattr(payload, "histories", {})
    for table_name, table_rows in histories.items():
        for row in table_rows:
            copied = dict(row)
            copied["_archive_source_table"] = table_name
            rows.append(copied)
    rows.sort(
        key=lambda row: (
            str(
                row.get("scraped_at")
                or row.get("scraped_at_utc")
                or row.get("snapshot_at")
                or row.get("created_at")
                or ""
            ),
            str(row.get("_archive_source_table") or ""),
        )
    )
    return rows


def _price_observation(
    context: dict[str, Any],
    fixture_id: str,
    market: str,
    selection: str,
) -> dict[str, Any] | None:
    for item in context.get("price_evidence") or []:
        if not isinstance(item, dict):
            continue
        if str(item.get("fixture_id") or "").strip() != fixture_id:
            continue
        if str(item.get("market") or "").strip() != market:
            continue
        if str(item.get("selection") or "").strip() != selection:
            continue
        return dict(item)
    return None


def _evidence(
    *,
    fixture_id: str,
    stage1_row: dict[str, Any],
    stage2_row: dict[str, Any],
    stage3_row: dict[str, Any],
    stage1_context: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    evidence: list[dict[str, Any]] = []
    inferences: list[dict[str, Any]] = []
    baseline = stage3_row.get("stage1_baseline") or stage1_row.get("preference") or {}
    stage1_price = _price_observation(
        stage1_context,
        fixture_id,
        str(baseline.get("market") or ""),
        str(baseline.get("selection") or ""),
    )
    if stage1_price and stage1_price.get("observed_at"):
        evidence.append(
            {
                "source": "SmartXFlow accepted Stage 1",
                "note": str(stage1_row.get("rationale") or "Frozen Stage 1 native SXF preference."),
                "observed_at": stage1_price["observed_at"],
                "relationship": "SUPPORTS",
            }
        )

    for fact in stage2_row.get("facts") or []:
        if not isinstance(fact, dict):
            continue
        kind = str(fact.get("kind") or "").upper()
        relationship = str(fact.get("relationship") or "UNKNOWN").upper()
        if relationship not in {"SUPPORTS", "CONTRADICTS", "NEUTRAL", "UNKNOWN"}:
            relationship = "UNKNOWN"
        claim = str(fact.get("claim") or "").strip()
        source = str(fact.get("source") or "").strip()
        observed_at = str(fact.get("observed_at") or "").strip()
        if kind == "FACT" and claim and source and observed_at:
            item: dict[str, Any] = {
                "source": source,
                "note": claim,
                "observed_at": observed_at,
                "relationship": relationship,
            }
            if fact.get("url"):
                item["url"] = fact.get("url")
            if fact.get("published_at"):
                item["published_at"] = fact.get("published_at")
            evidence.append(item)
        elif claim:
            inferences.append(
                {
                    "kind": kind or "INFERENCE",
                    "relationship": relationship,
                    "claim": claim,
                }
            )

    price_evidence = stage3_row.get("price_evidence")
    if isinstance(price_evidence, dict):
        origin = str(price_evidence.get("origin") or "").upper()
        observed_at = str(price_evidence.get("observed_at") or "").strip()
        price = price_evidence.get("price")
        if origin in {"USER_SUPPLIED", "EXTERNAL_VERIFIED"} and observed_at and isinstance(price, (int, float)):
            evidence.append(
                {
                    "source": str(price_evidence.get("source") or origin),
                    "note": (
                        f"Observed execution price {price:g} for "
                        f"{(stage3_row.get('preference') or {}).get('market')} / "
                        f"{(stage3_row.get('preference') or {}).get('selection')}."
                    ),
                    "observed_at": observed_at,
                    "relationship": "NEUTRAL",
                }
            )
    return evidence, inferences


def build_archive_case(
    *,
    workflow_scope: dict[str, Any],
    stage1_payload: dict[str, Any],
    stage2_payload: dict[str, Any],
    stage3_row: dict[str, Any],
    stage1_context: dict[str, Any],
    source_commit: str,
) -> dict[str, Any]:
    fixture_id = _fixture_id(stage3_row)
    if not fixture_id:
        raise ArchivePublicationError("formal Stage 3 row has no fixture_id")
    stage1_by_id = _by_fixture(stage1_payload.get("matches"))
    stage2_by_id = _by_fixture(stage2_payload.get("matches"))
    context_by_id = _by_fixture(stage1_context.get("fixtures"))
    stage1_row = stage1_by_id.get(fixture_id) or {}
    stage2_row = stage2_by_id.get(fixture_id) or {}
    fixture = context_by_id.get(fixture_id) or {}

    prediction_at = str(stage3_row.get("prediction_at") or "").strip()
    decision = str(stage3_row.get("decision") or "").upper()
    preference = stage3_row.get("preference") or {}
    market = str(preference.get("market") or "").strip()
    selection = str(preference.get("selection") or "").strip()
    if decision not in {"BET", "WATCH"}:
        raise ArchivePublicationError("only BET/WATCH rows are formal archive cases")
    if not prediction_at or not market or not selection:
        raise ArchivePublicationError("formal Stage 3 row is missing prediction identity")

    price_evidence = stage3_row.get("price_evidence") if isinstance(stage3_row.get("price_evidence"), dict) else {}
    price = preference.get("price")
    if not isinstance(price, (int, float)):
        price = price_evidence.get("price")
    if decision == "BET" and (not isinstance(price, (int, float)) or isinstance(price, bool) or price <= 1):
        raise ArchivePublicationError("formal BET cannot be archived without an observed entry price")

    evidence, inferences = _evidence(
        fixture_id=fixture_id,
        stage1_row=stage1_row,
        stage2_row=stage2_row,
        stage3_row=stage3_row,
        stage1_context=stage1_context,
    )
    created_at = prediction_at
    prediction: dict[str, Any] = {
        "prediction_at": prediction_at,
        "decision": decision,
        "market": market,
        "selection": selection,
        "entry_odds": float(price) if isinstance(price, (int, float)) and not isinstance(price, bool) else None,
        "confidence": stage3_row.get("final_confidence"),
        "rationale": str(stage3_row.get("rationale") or "").strip(),
        "counterargument": str(stage3_row.get("strongest_counterargument") or "").strip(),
        "grade": stage3_row.get("grade"),
        "execution_type": stage3_row.get("execution_type"),
        "divergence_state": stage3_row.get("divergence_state"),
        "counter_severity": stage3_row.get("counter_severity"),
        "stage2_verdict": stage3_row.get("stage2_verdict"),
        "stage1_baseline": stage3_row.get("stage1_baseline"),
        "change_driver": stage3_row.get("change_driver"),
    }
    threshold = price_evidence.get("minimum_acceptable_price")
    if isinstance(threshold, (int, float)) and not isinstance(threshold, bool):
        prediction["minimum_acceptable_odds"] = float(threshold)
    if inferences:
        prediction["stage2_inferences"] = inferences

    kickoff = fixture.get("kickoff_utc") or fixture.get("kickoff_at")
    if not kickoff:
        raise ArchivePublicationError(f"{fixture_id}: kickoff is missing from trusted Stage 1 context")
    return {
        "archive_schema_version": 1,
        "case_id": _case_id(prediction_at, fixture_id, market, selection),
        "match": {
            "match_id_hash": fixture_id,
            "league": str(fixture.get("league") or "").strip(),
            "home": str(fixture.get("home") or fixture.get("home_team") or "").strip(),
            "away": str(fixture.get("away") or fixture.get("away_team") or "").strip(),
            "kickoff_at": kickoff,
        },
        "prediction": prediction,
        "evidence": evidence,
        "settlement": {"status": "PENDING"},
        "provenance": {
            "archive_created_at": created_at,
            "source_repo": _REPOSITORY,
            "source_commit": source_commit,
        },
        "analysis_scope": dict(workflow_scope),
    }


class PredictionDiaryWriter:
    """Append-only day diary writer for the canonical learning-archive branch."""

    def __init__(self, *, token: str = "", ssh_key: str = ""):
        self.token = token.strip()
        self.ssh_key = ssh_key.strip()
        if not self.token and not self.ssh_key:
            raise ArchivePublicationError("Learning Archive diary credentials are not configured")

    @classmethod
    def from_env(cls) -> "PredictionDiaryWriter":
        return cls(
            token=os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip(),
            ssh_key=os.environ.get("LEARNING_ARCHIVE_GIT_SSH_KEY", "").strip(),
        )

    @staticmethod
    def _path(prediction_at: str, timezone_name: str) -> str:
        tz = ZoneInfo(timezone_name or "Europe/Istanbul")
        local = _parse_dt(prediction_at).astimezone(tz)
        return f"diaries/{local:%Y/%m/%d}/predictions.md"

    @staticmethod
    def _block(
        *,
        workflow_id: str,
        stage_run_id: str,
        scope: dict[str, Any],
        cases: list[dict[str, Any]],
        case_status: dict[str, str],
    ) -> str:
        marker = f"SXF-PREDICTOR-STAGE3:{stage_run_id}"
        lines = [
            f"<!-- {marker}:BEGIN -->",
            f"## Predictor run `{workflow_id}`",
            "",
            f"- Stage 3 run: `{stage_run_id}`",
            f"- Scope: `{scope}`",
            "",
        ]
        for case in cases:
            match = case["match"]
            prediction = case["prediction"]
            case_id = case["case_id"]
            price = prediction.get("entry_odds")
            threshold = prediction.get("minimum_acceptable_odds")
            price_text = f"@{price:g}" if isinstance(price, (int, float)) else (
                f"minimum {threshold:g}" if isinstance(threshold, (int, float)) else "price not verified"
            )
            lines.extend(
                [
                    f"### {match['home']} – {match['away']}",
                    f"- Category: **{prediction['decision']}**",
                    f"- Execution: **{prediction['selection']} | {prediction['market']} | {price_text}**",
                    f"- Confidence: **{prediction.get('confidence')}**",
                    f"- prediction_at: `{prediction['prediction_at']}`",
                    f"- Stage 1 baseline: `{prediction.get('stage1_baseline')}`",
                    f"- Stage 2 verdict: `{prediction.get('stage2_verdict')}`",
                    f"- case_id: `{case_id}` | archive state: **{case_status.get(case_id, 'ARCHIVE_PENDING')}**",
                    f"- **Why this prediction:** {prediction['rationale']} Caution: {prediction['counterargument']}",
                    "",
                ]
            )
        lines.append(f"<!-- {marker}:END -->")
        return "\n".join(lines) + "\n"

    def _write_token(self, path: str, marker: str, block: str) -> DiaryWriteResult:
        backend = GitHubArchiveBackend(token=self.token)
        current = backend._read(path)
        raw, sha = current if current else (b"", None)
        text = raw.decode("utf-8") if raw else ""
        if marker in text:
            head = backend._head_sha()
            return DiaryWriteResult(
                status="RECORDED",
                reference=f"https://github.com/{_REPOSITORY}/blob/{head}/learning_archive_data/{path}",
                commit_sha=head,
                idempotent=True,
            )
        header = "# SmartXFlow Prediction Diary\n\n" if not text else ""
        updated = (text + ("\n" if text and not text.endswith("\n") else "") + header + block).encode("utf-8")
        if sha:
            backend._update(path, updated, sha, "Append Predictor prediction diary")
        else:
            backend._put_new(path, updated, "Create Predictor prediction diary")
        head = backend._head_sha()
        return DiaryWriteResult(
            status="RECORDED",
            reference=f"https://github.com/{_REPOSITORY}/blob/{head}/learning_archive_data/{path}",
            commit_sha=head,
            idempotent=False,
        )

    def _write_ssh(self, path: str, marker: str, block: str) -> DiaryWriteResult:
        backend = GitSshArchiveBackend(self.ssh_key)
        with tempfile.TemporaryDirectory(prefix="sxf-predictor-diary-") as tmp:
            repo = Path(tmp) / "repo"
            backend._run([
                "git", "clone", "--quiet", "--single-branch", "--branch", backend.branch,
                "--depth", "1", backend.remote_url, str(repo),
            ])
            target = repo / "learning_archive_data" / path
            target.parent.mkdir(parents=True, exist_ok=True)
            text = target.read_text(encoding="utf-8") if target.exists() else ""
            if marker in text:
                head = backend._run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
                return DiaryWriteResult(
                    status="RECORDED",
                    reference=f"https://github.com/{_REPOSITORY}/blob/{head}/learning_archive_data/{path}",
                    commit_sha=head,
                    idempotent=True,
                )
            header = "# SmartXFlow Prediction Diary\n\n" if not text else ""
            target.write_text(text + ("\n" if text and not text.endswith("\n") else "") + header + block, encoding="utf-8")
            backend._run(["git", "add", "--", str(target.relative_to(repo))], cwd=repo)
            backend._run(["git", "commit", "--quiet", "-m", "Append Predictor prediction diary"], cwd=repo)
            head = backend._run(["git", "rev-parse", "HEAD"], cwd=repo).stdout.strip()
            backend._run(["git", "push", "--porcelain", "origin", f"HEAD:refs/heads/{backend.branch}"], cwd=repo)
            backend._verify_remote_head(head)
            return DiaryWriteResult(
                status="RECORDED",
                reference=f"https://github.com/{_REPOSITORY}/blob/{head}/learning_archive_data/{path}",
                commit_sha=head,
                idempotent=False,
            )

    def write_predictions(
        self,
        *,
        workflow_id: str,
        stage_run_id: str,
        scope: dict[str, Any],
        cases: list[dict[str, Any]],
        case_status: dict[str, str],
    ) -> DiaryWriteResult:
        if not cases:
            raise ArchivePublicationError("prediction diary requires at least one formal case")
        prediction_at = cases[0]["prediction"]["prediction_at"]
        timezone_name = str(scope.get("timezone") or "Europe/Istanbul")
        path = self._path(prediction_at, timezone_name)
        marker = f"SXF-PREDICTOR-STAGE3:{stage_run_id}"
        block = self._block(
            workflow_id=workflow_id,
            stage_run_id=stage_run_id,
            scope=scope,
            cases=cases,
            case_status=case_status,
        )
        if self.ssh_key:
            return self._write_ssh(path, marker, block)
        return self._write_token(path, marker, block)


class Stage3ArchivePublisher:
    def __init__(
        self,
        *,
        exporter: LearningArchiveExporter,
        diary_writer: PredictionDiaryWriter,
        history_reader=read_learning_archive_match_history,
        source_commit: str | None = None,
    ):
        self.exporter = exporter
        self.diary_writer = diary_writer
        self.history_reader = history_reader
        self.source_commit = source_commit or _runtime_commit()

    @classmethod
    def from_env_optional(cls) -> "Stage3ArchivePublisher | None":
        has_credentials = bool(
            os.environ.get("LEARNING_ARCHIVE_GIT_SSH_KEY", "").strip()
            or os.environ.get("GITHUB_TOKEN", "").strip()
            or os.environ.get("GH_TOKEN", "").strip()
        )
        if not has_credentials:
            return None
        try:
            return cls(
                exporter=LearningArchiveExporter.from_env(),
                diary_writer=PredictionDiaryWriter.from_env(),
            )
        except (ArchiveFinalizationError, ArchivePublicationError, OSError, ValueError):
            return None

    def publish(
        self,
        *,
        workflow_id: str,
        stage_run_id: str,
        workflow_scope: dict[str, Any],
        stage1_payload: dict[str, Any],
        stage2_payload: dict[str, Any],
        stage3_payload: dict[str, Any],
        stage1_context: dict[str, Any],
    ) -> dict[str, Any]:
        formal_rows = [
            item for item in stage3_payload.get("matches") or []
            if isinstance(item, dict) and str(item.get("decision") or "").upper() in {"BET", "WATCH"}
        ]
        if not formal_rows:
            return {"status": "NOT_APPLICABLE", "formal_cases": 0, "cases": [], "diary_status": "NOT_REQUIRED"}

        cases: list[dict[str, Any]] = []
        receipts: list[dict[str, Any]] = []
        for row in formal_rows:
            fixture_id = _fixture_id(row)
            try:
                case = build_archive_case(
                    workflow_scope=workflow_scope,
                    stage1_payload=stage1_payload,
                    stage2_payload=stage2_payload,
                    stage3_row=row,
                    stage1_context=stage1_context,
                    source_commit=self.source_commit,
                )
                cases.append(case)
                history = self.history_reader(fixture_id)
                snapshots = _flatten_history(history)
                result = self.exporter.record_case(
                    case,
                    snapshots,
                    observed_at=case["provenance"]["archive_created_at"],
                    revisit=False,
                )
                receipts.append(
                    {
                        "fixture_id": fixture_id,
                        "case_id": case["case_id"],
                        "archive_status": "RECORDED" if result.status == "RECORDED" else result.status,
                        "archive_reference": result.archive_reference,
                        "archive_commit": result.archive_commit,
                        "checksum_summary": result.checksum_summary,
                        "error": None,
                    }
                )
            except (ArchiveFinalizationError, ArchivePublicationError, LearningArchiveSourceError, OSError, ValueError, KeyError, RuntimeError) as exc:
                if not any(_fixture_id(existing) == fixture_id for existing in cases):
                    try:
                        cases.append(
                            build_archive_case(
                                workflow_scope=workflow_scope,
                                stage1_payload=stage1_payload,
                                stage2_payload=stage2_payload,
                                stage3_row=row,
                                stage1_context=stage1_context,
                                source_commit=self.source_commit,
                            )
                        )
                    except Exception:
                        pass
                receipts.append(
                    {
                        "fixture_id": fixture_id,
                        "case_id": next((c["case_id"] for c in cases if c["match"]["match_id_hash"] == fixture_id), None),
                        "archive_status": "ARCHIVE_PENDING",
                        "archive_reference": None,
                        "archive_commit": None,
                        "checksum_summary": None,
                        "error": str(exc)[:500],
                    }
                )

        case_status = {
            str(item.get("case_id") or ""): str(item.get("archive_status") or "ARCHIVE_PENDING")
            for item in receipts
            if item.get("case_id")
        }
        diary: dict[str, Any]
        try:
            diary_result = self.diary_writer.write_predictions(
                workflow_id=workflow_id,
                stage_run_id=stage_run_id,
                scope=workflow_scope,
                cases=cases,
                case_status=case_status,
            )
            diary = {
                "status": diary_result.status,
                "reference": diary_result.reference,
                "commit": diary_result.commit_sha,
                "idempotent": diary_result.idempotent,
                "error": None,
            }
        except Exception as exc:
            diary = {
                "status": "DIARY_PENDING",
                "reference": None,
                "commit": None,
                "idempotent": False,
                "error": str(exc)[:500],
            }

        for item in receipts:
            item["diary_status"] = diary["status"]
            item["diary_reference"] = diary["reference"]
        all_recorded = all(item["archive_status"] == "RECORDED" for item in receipts)
        complete = all_recorded and diary["status"] == "RECORDED"
        return {
            "status": "RECORDED" if complete else "ARCHIVE_PENDING",
            "formal_cases": len(formal_rows),
            "cases": receipts,
            "diary_status": diary["status"],
            "diary": diary,
        }
