from __future__ import annotations

from pathlib import Path
import subprocess
import tempfile
from typing import Any, Iterable

from .github_backend import (
    ArchiveBackendError,
    ArchiveWriteResult,
    GitSshArchiveBackend,
    RepositoryFolderArchiveBackend,
    _parse_manifest,
    build_manifest_entry,
)
from .package import ArchivePackage


class GitSshBatchArchiveBackend(GitSshArchiveBackend):
    """Atomic multi-package SSH writer for the canonical Learning Archive.

    A complete timer batch is materialized in one temporary clone, force-staged
    under the archive root, verified byte-for-byte in the commit tree, then sent
    with one normal non-force push. This removes per-case clone/push latency and
    makes gitignore incapable of silently omitting canonical package files.
    """

    def _run_bytes(self, argv: list[str], *, cwd: Path) -> bytes:
        result = subprocess.run(
            argv,
            cwd=str(cwd),
            env=self._env(),
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            timeout=self.timeout,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or b"git command failed").decode("utf-8", errors="replace").strip()
            raise ArchiveBackendError(f"SSH archive git command failed: {detail}")
        return result.stdout

    def _commit_blob(self, repo_root: Path, commit: str, storage_path: str) -> bytes:
        return self._run_bytes(["git", "show", f"{commit}:{storage_path}"], cwd=repo_root)

    def _verify_commit_packages(
        self,
        repo_root: Path,
        commit: str,
        entries: list[tuple[ArchivePackage, dict[str, Any]]],
    ) -> None:
        manifest_path = f"{self.root}/manifest.jsonl"
        manifest_raw = self._commit_blob(repo_root, commit, manifest_path)
        manifest = _parse_manifest(manifest_raw)

        for package, case in entries:
            for name, payload in package.files.items():
                storage_path = f"{self.root}/{package.file_path(name)}"
                committed = self._commit_blob(repo_root, commit, storage_path)
                if committed != payload:
                    raise ArchiveBackendError(
                        f"commit-tree verification failed for {storage_path}; archive push aborted"
                    )
            expected_manifest = build_manifest_entry(package, case, root=self.root)
            if expected_manifest not in manifest:
                raise ArchiveBackendError(
                    f"commit-tree verification failed for {package.case_id}; manifest event missing"
                )

    def write_cases(
        self,
        entries: Iterable[tuple[ArchivePackage, dict[str, Any]]],
    ) -> list[ArchiveWriteResult]:
        prepared = list(entries)
        if not prepared:
            return []

        with tempfile.TemporaryDirectory(prefix="sxf-learning-archive-batch-") as tmp:
            repo_root = Path(tmp) / "repo"
            self._run([
                "git",
                "clone",
                "--quiet",
                "--single-branch",
                "--branch",
                self.branch,
                "--depth",
                "1",
                self.remote_url,
                str(repo_root),
            ])

            folder_backend = RepositoryFolderArchiveBackend(repo_root, root=self.root)
            item_idempotent: list[bool] = []
            changed = False
            for package, case in prepared:
                staged = folder_backend.write_case(package, case)
                item_idempotent.append(staged.idempotent)
                changed = changed or not staged.idempotent

            current = self._run(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()
            if not changed:
                self._verify_commit_packages(repo_root, current, prepared)
                return [
                    ArchiveWriteResult(
                        archive_reference=(
                            f"https://github.com/{self.repository}/tree/{current}/"
                            f"{self.root}/{package.case_path}"
                        ),
                        commit_sha=current,
                        idempotent=True,
                    )
                    for package, _ in prepared
                ]

            # Force staging is intentional and scoped strictly to the canonical
            # archive root. Global *.json ignore rules must never omit case data.
            self._run(["git", "add", "-f", "--", self.root], cwd=repo_root)
            diff = subprocess.run(
                ["git", "diff", "--cached", "--quiet"],
                cwd=str(repo_root),
                env=self._env(),
                timeout=self.timeout,
            )
            if diff.returncode not in (0, 1):
                raise ArchiveBackendError("SSH archive staged diff verification failed")
            if diff.returncode == 0:
                raise ArchiveBackendError("SSH archive batch changed state but staged no files")

            self._run([
                "git",
                "commit",
                "--quiet",
                "-m",
                f"Archive batch {len(prepared)} package(s)",
            ], cwd=repo_root)
            commit = self._run(["git", "rev-parse", "HEAD"], cwd=repo_root).stdout.strip()

            # Verify every canonical byte before network mutation. If any package
            # file or manifest event is absent (including ignored JSON), no push.
            self._verify_commit_packages(repo_root, commit, prepared)

            self._run([
                "git",
                "push",
                "--porcelain",
                "origin",
                f"HEAD:refs/heads/{self.branch}",
            ], cwd=repo_root)
            self._verify_remote_head(commit)

            return [
                ArchiveWriteResult(
                    archive_reference=(
                        f"https://github.com/{self.repository}/tree/{commit}/"
                        f"{self.root}/{package.case_path}"
                    ),
                    commit_sha=commit,
                    idempotent=item_idempotent[index],
                )
                for index, (package, _) in enumerate(prepared)
            ]

    def write_case(self, package: ArchivePackage, case: dict[str, Any]) -> ArchiveWriteResult:
        return self.write_cases([(package, case)])[0]
