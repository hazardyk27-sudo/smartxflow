from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import os
from typing import Any, Protocol

from .github_backend import ArchiveWriteResult, GitHubArchiveBackend
from .package import ArchivePackage, build_archive_package, verify_package_checksums
from .validator import validate_case


class ArchiveFinalizationError(RuntimeError):
    pass


class ArchiveBackend(Protocol):
    def write_case(self, package: ArchivePackage, case: dict[str, Any]) -> ArchiveWriteResult: ...


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
        repository = os.environ.get("SMARTXFLOW_LEARNING_ARCHIVE_REPO", "").strip()
        token = os.environ.get("SMARTXFLOW_LEARNING_ARCHIVE_GITHUB_TOKEN", "").strip()
        branch = os.environ.get("SMARTXFLOW_LEARNING_ARCHIVE_BRANCH", "main").strip() or "main"
        if not repository:
            raise ArchiveFinalizationError("SMARTXFLOW_LEARNING_ARCHIVE_REPO is not configured")
        if not token:
            raise ArchiveFinalizationError("SMARTXFLOW_LEARNING_ARCHIVE_GITHUB_TOKEN is not configured")
        return cls(GitHubArchiveBackend(repository=repository, token=token, branch=branch))

    def finalize_case(self, case: dict[str, Any], snapshots: list[dict[str, Any]]) -> FinalizationResult:
        validation = validate_case(case, snapshots)
        if not validation.ok:
            raise ArchiveFinalizationError("validator FAIL: " + "; ".join(validation.errors))

        package = build_archive_package(case, snapshots)
        checksum_ok, checksum_errors = verify_package_checksums(package)
        if not checksum_ok:
            raise ArchiveFinalizationError("package checksum FAIL: " + "; ".join(checksum_errors))

        write = self.backend.write_case(package, case)
        if not write.archive_reference or not write.commit_sha:
            raise ArchiveFinalizationError("archive write did not return durable reference/commit")

        return FinalizationResult(
            status="DONE",
            archive_reference=write.archive_reference,
            archive_commit=write.commit_sha,
            checksum_summary=package.checksum_summary,
            idempotent=write.idempotent,
        )


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat().replace("+00:00", "Z")
