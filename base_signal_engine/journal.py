"""Preview-only durable append-only JSONL checkpoint journal.

Not a production Supabase event store. Prevents duplicate checkpoint writes
across restarts/parallel preview processes using a nonblocking advisory lock.
"""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


class JournalCorruptError(RuntimeError):
    pass


class CheckpointJsonlJournal:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._lock = threading.RLock()
        self._seen: set[str] = set()
        self._load()

    def _load(self):
        if not self.path.exists():
            return
        raw = self.path.read_bytes()
        lines = raw.split(b"\n")
        if lines[-1]:
            # Truncated last record after a crash: never guess whether it was
            # completed; repair requires an explicit operator action.
            raise JournalCorruptError("unterminated journal record; manual recovery required")
        keys = set()
        for line in lines[:-1]:
            try:
                record = json.loads(line)
                key = record["key"]
                if not isinstance(key, str) or not key:
                    raise ValueError("empty key")
                if key in keys:
                    raise JournalCorruptError("duplicate checkpoint key in journal")
                keys.add(key)
            except (ValueError, KeyError, TypeError) as exc:
                raise JournalCorruptError("corrupt JSONL checkpoint record") from exc
        self._seen = keys

    def has_completed(self, key: str) -> bool:
        with self._lock:
            return key in self._seen

    def commit(self, key: str, payload: dict) -> bool:
        if payload.get("key") != key:
            raise ValueError("journal key/payload mismatch")
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock:
            if key in self._seen:
                return False
            with self.path.open("a+b") as file:
                if fcntl is None:
                    raise RuntimeError("POSIX flock required for shadow journal")
                fcntl.flock(file.fileno(), fcntl.LOCK_EX)
                try:
                    # Detect new writes from another journal object/process.
                    self._load()
                    if key in self._seen:
                        return False
                    encoded = (json.dumps(payload, ensure_ascii=False, sort_keys=True, allow_nan=False) + "\n").encode("utf-8")
                    file.seek(0, os.SEEK_END)
                    file.write(encoded)
                    file.flush()
                    os.fsync(file.fileno())
                    self._seen.add(key)
                    return True
                finally:
                    fcntl.flock(file.fileno(), fcntl.LOCK_UN)
