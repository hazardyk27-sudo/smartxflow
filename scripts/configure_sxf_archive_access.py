#!/usr/bin/env python3
"""Owner-run, interactive setup of SXF admin password and CAPITALE Actions token.

Does not touch Supabase or create PostgreSQL credentials. Does not print secrets.
Only install a RESTRICTED GitHub fine-grained token for CAPITALE Actions:write.
Run manually on the authorized SXF server:
  sudo /opt/smartxflow/venv/bin/python scripts/configure_sxf_archive_access.py
"""
from __future__ import annotations

import argparse
import getpass
import os
import pathlib
import stat
import tempfile

from werkzeug.security import generate_password_hash

DEFAULT_PATH = pathlib.Path("/opt/smartxflow/.env")
UPDATES = ("SXF_ADMIN_PASSWORD_HASH", "CAPITALE_GITHUB_ACTIONS_TOKEN")


def check_file(path: pathlib.Path):
    if path.is_symlink() or not path.is_file():
        raise RuntimeError("Configuration must be an existing regular non-symlink file")
    s = path.stat()
    if stat.S_IMODE(s.st_mode) != 0o600:
        raise RuntimeError("Refusing non-private .env; require chmod 600")
    if not os.access(path, os.R_OK | os.W_OK):
        raise RuntimeError("Process lacks permission to edit private .env")
    return s


def check_only(path: pathlib.Path):
    check_file(path)
    contents = path.read_text("utf-8")
    for name in UPDATES:
        found = [line for line in contents.splitlines() if line.startswith(name + "=")]
        if len(found) > 1:
            raise RuntimeError(f"Duplicate {name} entries")
        print(f"{name}: {'SET' if found and len(found[0]) > len(name) + 1 else 'MISSING'}")
    print("SXF_ARCHIVE_DATABASE_URL: configure independently as a CAPITALE GitHub Actions secret")
    print("No secret values printed")


def save_secret_lines(path: pathlib.Path, replacements: dict[str, str]):
    s = check_file(path)
    original = path.read_text("utf-8")
    lines = original.splitlines()
    result = []
    used = set()
    for line in lines:
        key = line.partition("=")[0]
        if key in replacements:
            if key in used:
                raise RuntimeError(f"Duplicate {key} in .env")
            result.append(key + "=" + replacements[key])
            used.add(key)
        else:
            result.append(line)
    for k, v in replacements.items():
        if k not in used:
            result.append(k + "=" + v)
    data = "\n".join(result) + "\n"
    fd, tmp = tempfile.mkstemp(prefix=".sxf-admin-setup-", dir=str(path.parent))
    try:
        os.fchmod(fd, 0o600)
        os.fchown(fd, s.st_uid, s.st_gid)
        with os.fdopen(fd, "w", encoding="utf-8") as file:
            file.write(data)
            file.flush()
            os.fsync(file.fileno())
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--env-file", type=pathlib.Path, default=DEFAULT_PATH)
    p.add_argument("--check", action="store_true")
    args = p.parse_args()
    if args.check:
        check_only(args.env_file)
        return
    check_file(args.env_file)
    print("This program never echoes passwords, token values or password hashes.")
    new_pw = getpass.getpass("New dedicated SXF administrator password (min. 16 characters): ")
    confirm = getpass.getpass("Repeat SXF administrator password: ")
    if len(new_pw) < 16 or new_pw != confirm:
        raise SystemExit("Password mismatch or too short; nothing changed")
    token = getpass.getpass("Fine-grained CAPITALE-only GitHub token, Actions:write: ")
    if not token or "\n" in token or len(token) < 20 or "=" in token:
        raise SystemExit("Token absent/invalid; nothing changed")
    replacements = {
        "SXF_ADMIN_PASSWORD_HASH": generate_password_hash(new_pw, method="scrypt"),
        "CAPITALE_GITHUB_ACTIONS_TOKEN": token.strip(),
    }
    save_secret_lines(args.env_file, replacements)
    del new_pw, confirm, token
    print("Stored password hash and scoped token in private .env; no values shown.")
    print("Now run: sudo systemctl restart smartxflow-web")
    print("GitHub Actions still needs the SELECT-only SXF_ARCHIVE_DATABASE_URL repository secret.")


if __name__ == "__main__":
    main()
