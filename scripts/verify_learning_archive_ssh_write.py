#!/usr/bin/env python3
"""Fail-closed probe for the dedicated Learning Archive GitHub deploy key."""
from __future__ import annotations

import os
from pathlib import Path
import shlex
import stat
import subprocess
import sys
from typing import Callable

REMOTE = "git@github.com:hazardyk27-sudo/smartxflow.git"
ARCHIVE_REF = "refs/heads/learning-archive"
PROBE_REF = "refs/heads/sxf-learning-archive-write-check"


class ArchiveSshWriteProbeError(RuntimeError):
    pass


def _ssh_env(key: Path) -> dict[str, str]:
    env = os.environ.copy()
    env["GIT_SSH_COMMAND"] = (
        f"ssh -i {shlex.quote(str(key))} "
        "-o IdentitiesOnly=yes -o BatchMode=yes "
        "-o StrictHostKeyChecking=accept-new -o ConnectTimeout=10"
    )
    return env


def _run(args: list[str], env: dict[str, str], *, timeout: int = 30) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        args,
        env=env,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        timeout=timeout,
    )
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or "git command failed").strip()
        raise ArchiveSshWriteProbeError(detail)
    return result


def verify_archive_ssh_write(key_path: str | Path) -> str:
    key = Path(key_path).expanduser().resolve()
    if not key.is_file():
        raise ArchiveSshWriteProbeError(f"dedicated archive SSH key is missing: {key}")
    mode = stat.S_IMODE(key.stat().st_mode)
    if mode & 0o077:
        raise ArchiveSshWriteProbeError(
            f"dedicated archive SSH key is group/world-readable ({oct(mode)}); expected 0600-style permissions"
        )

    env = _ssh_env(key)
    remote = _run(["git", "ls-remote", REMOTE, ARCHIVE_REF], env)
    line = next((line.strip() for line in remote.stdout.splitlines() if line.strip()), "")
    if not line:
        raise ArchiveSshWriteProbeError("learning-archive branch was not visible through dedicated deploy key")
    archive_head = line.split()[0]
    if len(archive_head) != 40 or any(ch not in "0123456789abcdefABCDEF" for ch in archive_head):
        raise ArchiveSshWriteProbeError("learning-archive ls-remote returned an invalid commit SHA")

    # Push the local production HEAD to a temporary ref in --dry-run mode. This
    # forces GitHub to authorize repository write access without creating or
    # modifying any ref. A read-only deploy key fails here.
    _run(
        ["git", "push", "--dry-run", "--porcelain", REMOTE, f"HEAD:{PROBE_REF}"],
        env,
    )
    return archive_head.lower()


def main() -> int:
    key = os.environ.get("LEARNING_ARCHIVE_GIT_SSH_KEY", "").strip()
    if not key:
        print("LEARNING_ARCHIVE_SSH_WRITE_FAIL: LEARNING_ARCHIVE_GIT_SSH_KEY is not configured", file=sys.stderr)
        return 1
    try:
        archive_head = verify_archive_ssh_write(key)
    except (ArchiveSshWriteProbeError, OSError, subprocess.SubprocessError) as exc:
        print(f"LEARNING_ARCHIVE_SSH_WRITE_FAIL: {exc}", file=sys.stderr)
        return 1
    print(f"LEARNING_ARCHIVE_SSH_WRITE_OK archive_head={archive_head}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
