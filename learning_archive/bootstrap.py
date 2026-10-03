from __future__ import annotations

import base64
import os

import requests


class ArchiveBootstrapError(RuntimeError):
    pass


def _put(session: requests.Session, base: str, branch: str, path: str, payload: bytes) -> str:
    response = session.put(
        f"{base}/contents/{path}",
        json={
            "message": f"Initialize Learning Archive: {path}",
            "content": base64.b64encode(payload).decode("ascii"),
            "branch": branch,
        },
        timeout=30,
    )
    if response.status_code not in (200, 201):
        raise ArchiveBootstrapError(f"failed to initialize {path} ({response.status_code})")
    return response.json()["commit"]["sha"]


def bootstrap_archive_repository(schema_bytes: bytes) -> str:
    """Initialize an already-created private archive repository.

    Repository creation is not performed here. The configured repo must already exist and have
    the configured branch. Existing bootstrap files are left untouched.
    """
    repository = os.environ.get("SMARTXFLOW_LEARNING_ARCHIVE_REPO", "").strip()
    token = os.environ.get("SMARTXFLOW_LEARNING_ARCHIVE_GITHUB_TOKEN", "").strip()
    branch = os.environ.get("SMARTXFLOW_LEARNING_ARCHIVE_BRANCH", "main").strip() or "main"
    if not repository or not token:
        raise ArchiveBootstrapError("archive repository/token configuration is missing")

    base = f"https://api.github.com/repos/{repository}"
    session = requests.Session()
    session.headers.update({
        "Authorization": f"Bearer {token}",
        "Accept": "application/vnd.github+json",
        "X-GitHub-Api-Version": "2022-11-28",
        "User-Agent": "smartxflow-learning-archive-bootstrap",
    })

    ref = session.get(f"{base}/git/ref/heads/{branch}", timeout=30)
    if ref.status_code != 200:
        raise ArchiveBootstrapError(f"archive repository/branch is not ready ({ref.status_code})")

    readme = b"""# SmartXFlow Learning Archive\n\nPrivate, append-only archive of selected Predictor BET/WATCH/PASS cases.\n\n- Never store credentials or secrets.\n- Finalized case payloads are immutable. Corrections are append-only.\n- `manifest.jsonl` is the canonical case index.\n- Application code remains in `hazardyk27-sudo/smartxflow`.\n"""
    files = {
        "README.md": readme,
        "manifest.jsonl": b"",
        "schema/match_case_v1.schema.json": schema_bytes,
    }
    last_commit = ref.json()["object"]["sha"]
    for path, payload in files.items():
        current = session.get(f"{base}/contents/{path}", params={"ref": branch}, timeout=30)
        if current.status_code == 200:
            continue
        if current.status_code != 404:
            raise ArchiveBootstrapError(f"failed to inspect {path} ({current.status_code})")
        last_commit = _put(session, base, branch, path, payload)
    return last_commit
