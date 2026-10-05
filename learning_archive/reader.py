from __future__ import annotations

import gzip
import json
from pathlib import Path
from typing import Any, Iterator

from .github_backend import ArchiveBackendError, DEFAULT_ROOT
from .package import sha256_hex


class LearningArchiveReadError(ArchiveBackendError):
    pass


class LearningArchiveReader:
    """Development-side reader for a checked-out/mounted learning_archive_data folder."""

    def __init__(self, repo_root: str | Path, *, root: str = DEFAULT_ROOT):
        self.repo_root = Path(repo_root)
        self.root_name = root.strip("/") or DEFAULT_ROOT
        self.root = self.repo_root / self.root_name

    def _manifest(self) -> list[dict[str, Any]]:
        path = self.root / "manifest.jsonl"
        if not path.exists():
            raise LearningArchiveReadError("manifest.jsonl is missing")
        entries: list[dict[str, Any]] = []
        for line in path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError as exc:
                raise LearningArchiveReadError("manifest.jsonl contains invalid JSON") from exc
            if not isinstance(item, dict):
                raise LearningArchiveReadError("manifest entry must be an object")
            entries.append(item)
        return entries

    def _case_dir(self, archive_path: str) -> Path:
        clean = archive_path.strip("/")
        prefix = self.root_name + "/"
        if clean.startswith(prefix):
            clean = clean[len(prefix):]
        path = (self.root / clean).resolve()
        root = self.root.resolve()
        if path != root and root not in path.parents:
            raise LearningArchiveReadError("archive path escapes learning archive root")
        return path

    def _load_json(self, path: Path) -> Any:
        try:
            return json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise LearningArchiveReadError(f"could not read {path.name}") from exc

    def _verify_checksums(self, case_dir: Path) -> None:
        checksum_path = case_dir / "checksums.sha256"
        if not checksum_path.exists():
            raise LearningArchiveReadError("finalized case is missing checksums.sha256")
        for line in checksum_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            try:
                digest, name = line.split("  ", 1)
            except ValueError as exc:
                raise LearningArchiveReadError("checksums.sha256 is malformed") from exc
            target = case_dir / name
            if not target.exists() or sha256_hex(target.read_bytes()) != digest:
                raise LearningArchiveReadError(f"checksum mismatch for {name}")

    def _load_historical_snapshots(self, case_dir: Path) -> tuple[Any | None, dict[str, Any] | None]:
        """Read append-only legacy history hydration without mutating original case checksums."""
        history_path = case_dir / "historical_sxf_snapshots.json"
        if not history_path.exists():
            return None, None

        checksum_path = case_dir / "historical_sxf_snapshots.sha256"
        if not checksum_path.exists():
            raise LearningArchiveReadError("historical SXF backfill is missing historical_sxf_snapshots.sha256")
        lines = [line for line in checksum_path.read_text(encoding="utf-8").splitlines() if line.strip()]
        if len(lines) != 1:
            raise LearningArchiveReadError("historical_sxf_snapshots.sha256 is malformed")
        try:
            digest, name = lines[0].split("  ", 1)
        except ValueError as exc:
            raise LearningArchiveReadError("historical_sxf_snapshots.sha256 is malformed") from exc
        if name != "historical_sxf_snapshots.json":
            raise LearningArchiveReadError("historical SXF checksum references unexpected artifact")
        raw = history_path.read_bytes()
        if sha256_hex(raw) != digest:
            raise LearningArchiveReadError("checksum mismatch for historical_sxf_snapshots.json")
        try:
            snapshots = json.loads(raw.decode("utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError) as exc:
            raise LearningArchiveReadError("could not read historical_sxf_snapshots.json") from exc
        if not isinstance(snapshots, list) or not snapshots:
            raise LearningArchiveReadError("historical_sxf_snapshots.json must contain a non-empty array")

        metadata_path = case_dir / "addenda" / "historical_sxf_backfill.json"
        metadata = self._load_json(metadata_path) if metadata_path.exists() else None
        if metadata is not None and not isinstance(metadata, dict):
            raise LearningArchiveReadError("historical SXF backfill metadata must be an object")
        return snapshots, metadata

    @staticmethod
    def _has_concrete_prediction(item: dict[str, Any]) -> bool:
        prediction = (item.get("case") or {}).get("prediction") or {}
        decision = prediction.get("decision")
        market = prediction.get("market")
        selection = prediction.get("selection")
        return (
            decision in {"BET", "WATCH"}
            and isinstance(market, str)
            and bool(market.strip())
            and isinstance(selection, str)
            and bool(selection.strip())
        )

    def read_case(self, case_id: str) -> dict[str, Any]:
        events = [entry for entry in self._manifest() if entry.get("case_id") == case_id]
        if not events:
            raise LearningArchiveReadError(f"case_id {case_id} not found")
        case_dir = self._case_dir(str(events[-1]["archive_path"]))
        case_doc = self._load_json(case_dir / "case.json")
        evidence = self._load_json(case_dir / "evidence.json")
        finalized = any(event.get("event") == "FINALIZED" for event in events)
        settlement = self._load_json(case_dir / "settlement.json") if (case_dir / "settlement.json").exists() else None
        snapshots = None
        snapshot_source = None
        snapshot_provenance = None
        if (case_dir / "sxf_snapshots.json.gz").exists():
            try:
                snapshots = json.loads(gzip.decompress((case_dir / "sxf_snapshots.json.gz").read_bytes()).decode("utf-8"))
            except (OSError, json.JSONDecodeError, UnicodeDecodeError) as exc:
                raise LearningArchiveReadError("could not read sxf_snapshots.json.gz") from exc
            snapshot_source = "canonical"
        else:
            snapshots, snapshot_provenance = self._load_historical_snapshots(case_dir)
            if snapshots is not None:
                snapshot_source = "historical_backfill"
        if finalized:
            self._verify_checksums(case_dir)
        captures = sorted(str(path.relative_to(case_dir)) for path in (case_dir / "captures").glob("*.json.gz")) if (case_dir / "captures").exists() else []
        pre_evidence = [item for item in evidence if item.get("phase") == "PRE"]
        post_evidence = [item for item in evidence if item.get("phase") == "POST"]
        return {
            "case": case_doc,
            "evidence": evidence,
            "pre_evidence": pre_evidence,
            "post_evidence": post_evidence,
            "settlement": settlement,
            "snapshots": snapshots,
            "snapshot_source": snapshot_source,
            "snapshot_provenance": snapshot_provenance,
            "captures": captures,
            "manifest_events": events,
            "finalized": finalized,
        }

    def iter_cases(
        self,
        *,
        finalized_only: bool = False,
        prediction_only: bool = True,
    ) -> Iterator[dict[str, Any]]:
        """Iterate usable prediction cases by default; legacy no-pick/PASS cases remain auditable via read_case or prediction_only=False."""
        seen: set[str] = set()
        for entry in self._manifest():
            case_id = str(entry.get("case_id") or "")
            if not case_id or case_id in seen:
                continue
            seen.add(case_id)
            item = self.read_case(case_id)
            if finalized_only and not item["finalized"]:
                continue
            if prediction_only and not self._has_concrete_prediction(item):
                continue
            yield item
