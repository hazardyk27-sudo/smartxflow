from __future__ import annotations

import base64
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from urllib.parse import quote

import requests

from .package import ArchivePackage, sha256_hex

DEFAULT_REPOSITORY = "hazardyk27-sudo/smartxflow"
DEFAULT_BRANCH = "learning-archive"
DEFAULT_ROOT = "learning_archive_data"


class ArchiveBackendError(RuntimeError):
    pass


class ArchiveConflictError(ArchiveBackendError):
    pass


@dataclass(frozen=True)
class ArchiveWriteResult:
    archive_reference: str
    commit_sha: str
    idempotent: bool


def build_manifest_entry(package: ArchivePackage, case: dict[str, Any], *, root: str = DEFAULT_ROOT) -> dict[str, Any]:
    capture_files = sorted(name for name in package.files if name.startswith("captures/"))
    entry: dict[str, Any] = {
        "case_id": package.case_id,
        "event": package.package_kind,
        "event_key": package.event_key,
        "archive_path": f"{root.rstrip('/')}/{package.case_path}",
        "archive_schema_version": case["archive_schema_version"],
        "match_id_hash": case["match"]["match_id_hash"],
        "prediction_at": case["prediction"]["prediction_at"],
        "decision": case["prediction"]["decision"],
        "settlement_status": case["settlement"]["status"],
        "checksum_summary": package.checksum_summary,
    }
    if capture_files:
        entry["captures"] = [
            {"path": f"{entry['archive_path']}/{name}", "sha256": sha256_hex(package.files[name])}
            for name in capture_files
        ]
    return entry


def _parse_manifest(raw: bytes) -> list[dict[str, Any]]:
    entries: list[dict[str, Any]] = []
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            value = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ArchiveBackendError("manifest.jsonl contains invalid JSON") from exc
        if not isinstance(value, dict):
            raise ArchiveBackendError("manifest.jsonl entry must be an object")
        entries.append(value)
    return entries


def _manifest_update(raw: bytes, new_entry: dict[str, Any]) -> tuple[bytes, bool]:
    entries = _parse_manifest(raw)
    for entry in entries:
        if (
            entry.get("case_id") == new_entry.get("case_id")
            and entry.get("event") == new_entry.get("event")
            and entry.get("event_key") == new_entry.get("event_key")
        ):
            if entry != new_entry:
                raise ArchiveConflictError(
                    f"case_id {new_entry.get('case_id')} has conflicting {new_entry.get('event')} manifest event"
                )
            return raw, False
    line = json.dumps(new_entry, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    updated = raw + (b"" if not raw or raw.endswith(b"\n") else b"\n") + line.encode("utf-8") + b"\n"
    return updated, True


class GitHubArchiveBackend:
    """Durable append-only writer to this repository's Learning Archive data branch.

    No separate archive repository or archive-specific token is supported. The writer is
    locked to hazardyk27-sudo/smartxflow and uses normal repository GitHub credentials.
    """

    api_base = "https://api.github.com"
    durable = True

    def __init__(
        self,
        token: str,
        *,
        repository: str = DEFAULT_REPOSITORY,
        branch: str = DEFAULT_BRANCH,
        root: str = DEFAULT_ROOT,
        timeout: float = 30.0,
        session: requests.Session | None = None,
    ):
        if repository != DEFAULT_REPOSITORY:
            raise ValueError(f"Learning Archive repository is locked to {DEFAULT_REPOSITORY}")
        if not token:
            raise ValueError("existing repository GitHub token is required")
        self.repository = repository
        self.branch = branch
        self.root = root.strip("/") or DEFAULT_ROOT
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.update({
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "smartxflow-learning-archive",
        })

    def _url(self, suffix: str) -> str:
        return f"{self.api_base}/repos/{self.repository}{suffix}"

    def _storage_path(self, path: str) -> str:
        clean = path.lstrip("/")
        if clean == self.root or clean.startswith(self.root + "/"):
            return clean
        return f"{self.root}/{clean}"

    def _read(self, path: str, ref: str | None = None) -> tuple[bytes, str] | None:
        storage_path = self._storage_path(path)
        encoded_path = quote(storage_path, safe="/")
        response = self.session.get(
            self._url(f"/contents/{encoded_path}"),
            params={"ref": ref or self.branch},
            timeout=self.timeout,
        )
        if response.status_code == 404:
            return None
        if response.status_code != 200:
            raise ArchiveBackendError(f"archive read failed for {storage_path} ({response.status_code})")
        body = response.json()
        sha = body.get("sha")
        content = body.get("content")
        if isinstance(content, str):
            return base64.b64decode(content), sha
        if not sha:
            raise ArchiveBackendError(f"archive read returned no blob SHA for {storage_path}")
        blob = self.session.get(self._url(f"/git/blobs/{sha}"), timeout=self.timeout)
        if blob.status_code != 200:
            raise ArchiveBackendError(f"archive blob read failed for {storage_path} ({blob.status_code})")
        blob_content = blob.json().get("content")
        if not isinstance(blob_content, str):
            raise ArchiveBackendError(f"archive blob has no readable content for {storage_path}")
        return base64.b64decode(blob_content), sha

    def _put_new(self, path: str, payload: bytes, message: str) -> str:
        storage_path = self._storage_path(path)
        encoded_path = quote(storage_path, safe="/")
        response = self.session.put(
            self._url(f"/contents/{encoded_path}"),
            json={"message": message, "content": base64.b64encode(payload).decode("ascii"), "branch": self.branch},
            timeout=self.timeout,
        )
        if response.status_code not in (200, 201):
            raise ArchiveBackendError(f"archive write failed for {storage_path} ({response.status_code})")
        return response.json()["commit"]["sha"]

    def _update(self, path: str, payload: bytes, sha: str, message: str) -> str:
        storage_path = self._storage_path(path)
        encoded_path = quote(storage_path, safe="/")
        response = self.session.put(
            self._url(f"/contents/{encoded_path}"),
            json={"message": message, "content": base64.b64encode(payload).decode("ascii"), "sha": sha, "branch": self.branch},
            timeout=self.timeout,
        )
        if response.status_code != 200:
            raise ArchiveBackendError(f"archive update failed for {storage_path} ({response.status_code})")
        return response.json()["commit"]["sha"]

    def _head_sha(self) -> str:
        response = self.session.get(self._url(f"/git/ref/heads/{self.branch}"), timeout=self.timeout)
        if response.status_code != 200:
            raise ArchiveBackendError(f"archive branch read failed ({response.status_code})")
        return response.json()["object"]["sha"]

    def _write_manifest(self, package: ArchivePackage, case: dict[str, Any]) -> bool:
        current = self._read("manifest.jsonl")
        raw, sha = current if current else (b"", None)
        updated, changed = _manifest_update(raw, build_manifest_entry(package, case, root=self.root))
        if not changed:
            return False
        if sha:
            self._update("manifest.jsonl", updated, sha, f"Index archive {package.package_kind.lower()} {package.case_id}")
        else:
            self._put_new("manifest.jsonl", updated, f"Create archive manifest with {package.case_id}")
        return True

    def write_case(self, package: ArchivePackage, case: dict[str, Any]) -> ArchiveWriteResult:
        missing: list[tuple[str, bytes]] = []
        for name, payload in sorted(package.files.items()):
            path = package.file_path(name)
            existing = self._read(path)
            if existing is None:
                missing.append((name, payload))
            elif existing[0] != payload:
                raise ArchiveConflictError(
                    f"case_id {package.case_id} conflicts at {name}; historical truth is append-only"
                )

        for name, payload in missing:
            self._put_new(package.file_path(name), payload, f"Archive {package.case_id}: {name}")

        manifest_written = self._write_manifest(package, case)
        self.verify_case(package, case)
        commit = self._head_sha()
        return ArchiveWriteResult(
            archive_reference=f"https://github.com/{self.repository}/tree/{commit}/{self.root}/{package.case_path}",
            commit_sha=commit,
            idempotent=not missing and not manifest_written,
        )

    def verify_case(self, package: ArchivePackage, case: dict[str, Any]) -> None:
        for name, payload in package.files.items():
            remote = self._read(package.file_path(name))
            if remote is None or remote[0] != payload:
                raise ArchiveBackendError(f"post-write verification failed for {package.file_path(name)}")
        manifest = self._read("manifest.jsonl")
        if manifest is None:
            raise ArchiveBackendError("post-write manifest verification failed: manifest missing")
        expected = build_manifest_entry(package, case, root=self.root)
        if expected not in _parse_manifest(manifest[0]):
            raise ArchiveBackendError("post-write manifest verification failed: event missing")


class RepositoryFolderArchiveBackend:
    """Worktree/staging writer used for tests and local Development reads.

    This backend intentionally does not claim durability: writing a worktree does not commit
    to GitHub. Production/Predictor automatic archival must use GitHubArchiveBackend.
    """

    durable = False

    def __init__(self, repo_root: str | Path, *, root: str = DEFAULT_ROOT):
        self.repo_root = Path(repo_root)
        self.root = root.strip("/") or DEFAULT_ROOT
        self.archive_root = self.repo_root / self.root

    def _path(self, path: str) -> Path:
        clean = path.lstrip("/")
        if clean == self.root or clean.startswith(self.root + "/"):
            clean = clean[len(self.root):].lstrip("/")
        return self.archive_root / clean

    def write_case(self, package: ArchivePackage, case: dict[str, Any]) -> ArchiveWriteResult:
        wrote = False
        for name, payload in sorted(package.files.items()):
            target = self._path(package.file_path(name))
            if target.exists():
                if target.read_bytes() != payload:
                    raise ArchiveConflictError(
                        f"case_id {package.case_id} conflicts at {name}; historical truth is append-only"
                    )
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(payload)
            wrote = True

        manifest_path = self._path("manifest.jsonl")
        manifest_path.parent.mkdir(parents=True, exist_ok=True)
        raw = manifest_path.read_bytes() if manifest_path.exists() else b""
        updated, changed = _manifest_update(raw, build_manifest_entry(package, case, root=self.root))
        if changed:
            manifest_path.write_bytes(updated)
            wrote = True
        return ArchiveWriteResult(
            archive_reference=str(self._path(package.case_path)),
            commit_sha="UNCOMMITTED_WORKTREE",
            idempotent=not wrote,
        )
