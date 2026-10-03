from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from typing import Any
from urllib.parse import quote

import requests

from .package import ArchivePackage


class ArchiveBackendError(RuntimeError):
    pass


class ArchiveConflictError(ArchiveBackendError):
    pass


@dataclass(frozen=True)
class ArchiveWriteResult:
    archive_reference: str
    commit_sha: str
    idempotent: bool


class GitHubArchiveBackend:
    """Append-only writer for the dedicated private Learning Archive repository."""

    api_base = "https://api.github.com"

    def __init__(self, repository: str, token: str, branch: str = "main", timeout: float = 30.0):
        if "/" not in repository:
            raise ValueError("repository must be owner/name")
        if not token:
            raise ValueError("archive GitHub token is required")
        self.repository = repository
        self.branch = branch
        self.timeout = timeout
        self.session = requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "smartxflow-learning-archive",
        })

    def _url(self, suffix: str) -> str:
        return f"{self.api_base}/repos/{self.repository}{suffix}"

    def _read(self, path: str, ref: str | None = None) -> tuple[bytes, str] | None:
        encoded_path = quote(path, safe="/")
        response = self.session.get(
            self._url(f"/contents/{encoded_path}"),
            params={"ref": ref or self.branch},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ArchiveBackendError(f"archive read failed for {path} ({response.status_code})")
        body = response.json()
        sha = body.get("sha")
        content = body.get("content")
        if isinstance(content, str) and content:
            return base64.b64decode(content), sha
        if not sha:
            raise ArchiveBackendError(f"archive read returned no blob SHA for {path}")
        blob = self.session.get(self._url(f"/git/blobs/{sha}"), timeout=self.timeout)
        if blob.status_code != 200:
            raise ArchiveBackendError(f"archive blob read failed for {path} ({blob.status_code})")
        blob_content = blob.json().get("content")
        if not isinstance(blob_content, str):
            raise ArchiveBackendError(f"archive blob has no readable content for {path}")
        return base64.b64decode(blob_content), sha

    def _put_new(self, path: str, payload: bytes, message: str) -> str:
        encoded_path = quote(path, safe="/")
        response = self.session.put(
            self._url(f"/contents/{encoded_path}"),
            json={
                "message": message,
                "content": base64.b64encode(payload).decode("ascii"),
                "branch": self.branch,
            },
            timeout=self.timeout,
        )
        if response.status_code not in (200, 201):
            raise ArchiveBackendError(f"archive write failed for {path} ({response.status_code})")
        return response.json()["commit"]["sha"]

    def _update(self, path: str, payload: bytes, sha: str, message: str) -> str:
        encoded_path = quote(path, safe="/")
        response = self.session.put(
            self._url(f"/contents/{encoded_path}"),
            json={
                "message": message,
                "content": base64.b64encode(payload).decode("ascii"),
                "sha": sha,
                "branch": self.branch,
            },
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ArchiveBackendError(f"archive update failed for {path} ({response.status_code})")
        return response.json()["commit"]["sha"]

    def _manifest_entry(self, package: ArchivePackage, case: dict[str, Any]) -> dict[str, Any]:
        return {
            "case_id": package.case_id,
            "archive_path": package.case_path,
            "archive_schema_version": case["archive_schema_version"],
            "match_id_hash": case["match"]["match_id_hash"],
            "prediction_at": case["prediction"]["prediction_at"],
            "decision": case["prediction"]["decision"],
            "settlement_status": case["settlement"]["status"],
            "checksum_summary": package.checksum_summary,
        }

    def _write_manifest(self, package: ArchivePackage, case: dict[str, Any]) -> str:
        current = self._read("manifest.jsonl")
        raw, sha = current if current else (b"", None)
        entries = []
        for line in raw.decode("utf-8").splitlines():
            if line.strip():
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError as exc:
                    raise ArchiveBackendError("manifest.jsonl contains invalid JSON") from exc
        new_entry = self._manifest_entry(package, case)
        for entry in entries:
            if entry.get("case_id") == package.case_id:
                if entry != new_entry:
                    raise ArchiveConflictError(f"case_id {package.case_id} has conflicting manifest metadata")
                return self._head_sha()
        line = json.dumps(new_entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        updated = raw + (b"" if not raw or raw.endswith(b"\n") else b"\n") + line.encode("utf-8") + b"\n"
        if sha:
            return self._update("manifest.jsonl", updated, sha, f"Index archive case {package.case_id}")
        return self._put_new("manifest.jsonl", updated, f"Create archive manifest with {package.case_id}")

    def _head_sha(self) -> str:
        response = self.session.get(self._url(f"/git/ref/heads/{self.branch}"), timeout=self.timeout)
        if response.status_code != 200:
            raise ArchiveBackendError(f"archive branch read failed ({response.status_code})")
        return response.json()["object"]["sha"]

    def write_case(self, package: ArchivePackage, case: dict[str, Any]) -> ArchiveWriteResult:
        existing_checksums = self._read(package.file_path("checksums.sha256"))
        if existing_checksums:
            if existing_checksums[0] != package.files["checksums.sha256"]:
                raise ArchiveConflictError(
                    f"case_id {package.case_id} already exists with different payload; corrections must be append-only"
                )
            for name, payload in package.files.items():
                remote = self._read(package.file_path(name))
                if remote is None or remote[0] != payload:
                    raise ArchiveConflictError(f"finalized case {package.case_id} is incomplete or differs at {name}")
            commit = self._head_sha()
            return ArchiveWriteResult(
                archive_reference=f"https://github.com/{self.repository}/tree/{commit}/{package.case_path}",
                commit_sha=commit,
                idempotent=True,
            )

        last_commit = ""
        for name, payload in sorted(package.files.items()):
            path = package.file_path(name)
            existing = self._read(path)
            if existing is not None:
                if existing[0] != payload:
                    raise ArchiveConflictError(f"partial case {package.case_id} conflicts at {name}")
                continue
            last_commit = self._put_new(path, payload, f"Archive {package.case_id}: {name}")

        last_commit = self._write_manifest(package, case) or last_commit
        self.verify_case(package, case)
        commit = self._head_sha()
        return ArchiveWriteResult(
            archive_reference=f"https://github.com/{self.repository}/tree/{commit}/{package.case_path}",
            commit_sha=commit,
            idempotent=False,
        )

    def verify_case(self, package: ArchivePackage, case: dict[str, Any]) -> None:
        for name, payload in package.files.items():
            remote = self._read(package.file_path(name))
            if remote is None or remote[0] != payload:
                raise ArchiveBackendError(f"post-write verification failed for {package.file_path(name)}")
        manifest = self._read("manifest.jsonl")
        if manifest is None:
            raise ArchiveBackendError("post-write manifest verification failed: manifest missing")
        expected = self._manifest_entry(package, case)
        entries = [json.loads(line) for line in manifest[0].decode("utf-8").splitlines() if line.strip()]
        if expected not in entries:
            raise ArchiveBackendError("post-write manifest verification failed: case entry missing")
