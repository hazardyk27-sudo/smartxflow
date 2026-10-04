from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any, Protocol

from .github_backend import ArchiveWriteResult, GitHubArchiveBackend, GitSshArchiveBackend
from .package import ArchivePackage, build_archive_package, build_record_package, verify_package_checksums
from .retention import (
    RetentionHoldError,
    create_retention_hold,
    release_retention_hold,
    retention_holds_enabled,
)
from .validator import validate_case


class ArchiveFinalizationError(RuntimeError):
    pass


class ArchiveBackend(Protocol):
    durable: bool
    def write_case(self, package: ArchivePackage, case: dict[str, Any]) -> ArchiveWriteResult: ...


@dataclass(frozen=True)
class RecordResult:
    status: str
    archive_reference: str
    archive_commit: str
    checksum_summary: str
    idempotent: bool


@dataclass(frozen=True)
class FinalizationResult:
    status: str
    archive_reference: str
    archive_commit: str
    checksum_summary: str
    idempotent: bool


class LearningArchiveExporter:
    def __init__(self, backend: ArchiveBackend):
        self.backend = backend

    @classmethod
    def from_env(cls) -> "LearningArchiveExporter":
        token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
        if token:
            return cls(GitHubArchiveBackend(token=token))

        ssh_key = os.environ.get("LEARNING_ARCHIVE_GIT_SSH_KEY", "").strip()
        if ssh_key:
            try:
                return cls(GitSshArchiveBackend(ssh_key=ssh_key))
            except (OSError, ValueError) as exc:
                raise ArchiveFinalizationError(f"Learning Archive SSH backend is invalid: {exc}") from exc

        raise ArchiveFinalizationError(
            "canonical Learning Archive credentials are not configured "
            "(GITHUB_TOKEN/GH_TOKEN or LEARNING_ARCHIVE_GIT_SSH_KEY)"
        )

    def _canonical_retention_required(self) -> bool:
        # Local/memory backends are test/dev artifacts and must never mutate
        # production retention state. Both canonical GitHub writers do.
        return isinstance(self.backend, (GitHubArchiveBackend, GitSshArchiveBackend)) and retention_holds_enabled()

    def record_case(
        self,
        case: dict[str, Any],
        snapshots: list[dict[str, Any]],
        *,
        observed_at: str,
        revisit: bool = False,
    ) -> RecordResult:
        validation = validate_case(case, snapshots)
        if not validation.ok:
            raise ArchiveFinalizationError("validator FAIL: " + "; ".join(validation.errors))
        if case["settlement"]["status"] != "PENDING":
            raise ArchiveFinalizationError("record/capture requires PENDING settlement; settled cases must use finalization")

        # Retention protection is part of the canonical archive contract, not an
        # optional caller responsibility. The hold remains PENDING across
        # RECORDED/CAPTURED and is released only after settlement finalization.
        if self._canonical_retention_required():
            try:
                create_retention_hold(
                    case["case_id"],
                    case["match"]["match_id_hash"],
                    case["prediction"]["prediction_at"],
                )
            except RetentionHoldError as exc:
                raise ArchiveFinalizationError(
                    "retention hold creation failed; case must not be recorded without source-history protection"
                ) from exc

        package = build_record_package(case, snapshots, observed_at, revisit=revisit)
        write = self.backend.write_case(package, case)
        if not write.archive_reference or not write.commit_sha:
            raise ArchiveFinalizationError("archive write did not return reference/commit state")
        status = "CAPTURED" if revisit else "RECORDED"
        if getattr(self.backend, "durable", False) is False:
            status += "_UNCOMMITTED"
        return RecordResult(
            status=status,
            archive_reference=write.archive_reference,
            archive_commit=write.commit_sha,
            checksum_summary=package.checksum_summary,
            idempotent=write.idempotent,
        )

    def finalize_case(self, case: dict[str, Any], snapshots: list[dict[str, Any]]) -> FinalizationResult:
        validation = validate_case(case, snapshots)
        if not validation.ok:
            raise ArchiveFinalizationError("validator FAIL: " + "; ".join(validation.errors))
        if case["settlement"]["status"] == "PENDING":
            raise ArchiveFinalizationError("settlement is still PENDING; final archive cannot be DONE")

        package = build_archive_package(case, snapshots)
        checksum_ok, checksum_errors = verify_package_checksums(package)
        if not checksum_ok:
            raise ArchiveFinalizationError("package checksum FAIL: " + "; ".join(checksum_errors))

        write = self.backend.write_case(package, case)
        if not write.archive_reference or not write.commit_sha:
            raise ArchiveFinalizationError("archive write did not return durable reference/commit")
        if getattr(self.backend, "durable", False) is False:
            raise ArchiveFinalizationError(
                "archive files exist only in an uncommitted worktree; case is not DONE"
            )

        if self._canonical_retention_required():
            try:
                release_retention_hold(case["case_id"], write.archive_reference, package.checksum_summary)
            except RetentionHoldError as exc:
                raise ArchiveFinalizationError(
                    "archive verified but retention hold release failed; case remains retryable"
                ) from exc

        return FinalizationResult(
            status="DONE",
            archive_reference=write.archive_reference,
            archive_commit=write.commit_sha,
            checksum_summary=package.checksum_summary,
            idempotent=write.idempotent,
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
