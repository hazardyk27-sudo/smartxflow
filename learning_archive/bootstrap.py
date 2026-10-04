from __future__ import annotations

import os

from .github_backend import GitHubArchiveBackend


class ArchiveBootstrapError(RuntimeError):
    pass


def bootstrap_archive_repository(schema_bytes: bytes) -> str:
    """Ensure the in-repo Learning Archive folder exists on the data branch.

    No repository is created and no archive-specific token is used. The existing SmartXFlow
    repository credentials are reused and the backend is locked to hazardyk27-sudo/smartxflow.
    """
    token = os.environ.get("GITHUB_TOKEN", "").strip() or os.environ.get("GH_TOKEN", "").strip()
    if not token:
        raise ArchiveBootstrapError("normal repository GitHub credentials are missing (GITHUB_TOKEN or GH_TOKEN)")

    backend = GitHubArchiveBackend(token=token)
    try:
        backend._head_sha()
    except Exception as exc:
        raise ArchiveBootstrapError("learning-archive branch is not ready") from exc

    readme = b"""# SmartXFlow Learning Archive\n\nAppend-only selected-match archive inside `hazardyk27-sudo/smartxflow`.\n\n- Data branch: `learning-archive`\n- Root: `learning_archive_data/`\n- Only Predictor-researched BET/WATCH/PASS cases belong here.\n- Never store credentials or secrets.\n- Original prediction/evidence/history is immutable; corrections are append-only.\n- `manifest.jsonl` is an append-only event index.\n- A worktree-only write is not durable; DONE requires a verified GitHub commit.\n"""
    files = {
        "README.md": readme,
        "manifest.jsonl": b"",
        "schema/match_case_v1.schema.json": schema_bytes,
    }
    try:
        for path, payload in files.items():
            current = backend._read(path)
            if current is None:
                backend._put_new(path, payload, f"Initialize Learning Archive: {path}")
        return backend._head_sha()
    except Exception as exc:
        raise ArchiveBootstrapError(f"failed to initialize in-repo Learning Archive: {exc}") from exc
