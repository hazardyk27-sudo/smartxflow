"""Phase 5C1: local shadow observation evidence. No live worker activation.

The append-only hash chain detects accidental edits/truncation. It does NOT
authenticate real time, source origin, or guarantee continuous production
operation; independent operator attestation is a separate release gate.
"""
from __future__ import annotations

from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
from uuid import UUID

try:
    import fcntl
except ImportError:  # pragma: no cover
    fcntl = None


class ShadowEvidenceError(RuntimeError):
    pass


_ALLOWED_MODES = frozenset({"SYNTHETIC", "OPERATOR_READ_ONLY"})
_ALLOWED_COUNTERS = frozenset({
    "fixtures_discovered", "due", "committed", "already_done", "failed",
    "checkpoint_pending_due", "checkpoint_waiting_data", "checkpoint_expired_leases",
    "reconcile_pending_due", "reconcile_waiting_data", "reconcile_expired_leases",
    "source_pending_due", "source_review_required", "source_expired_leases",
    "uncertain_commits",
})


def _stamp(value: str) -> datetime:
    if not isinstance(value, str):
        raise ShadowEvidenceError("invalid evidence timestamp")
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ShadowEvidenceError("invalid evidence timestamp") from exc
    if dt.tzinfo is None or dt.utcoffset() != timezone.utc.utcoffset(dt):
        raise ShadowEvidenceError("shadow timestamps must be UTC")
    return dt


def _encode(obj: dict) -> bytes:
    return json.dumps(obj,sort_keys=True,separators=(",",":"),
                      allow_nan=False,ensure_ascii=True).encode("ascii")


def _read(path: Path) -> list[dict]:
    if not path.exists():
        return []
    data=path.read_bytes()
    if data and not data.endswith(b"\n"):
        raise ShadowEvidenceError("unterminated shadow evidence record")
    records=[]
    last_digest="0"*64
    last_at=None
    run_id=None
    mode=None
    for raw in data.splitlines():
        try:
            row=json.loads(raw)
            if not isinstance(row,dict) or set(row)!={"payload","prev_sha256","sha256"}:
                raise ValueError("invalid evidence row")
            payload=row["payload"]
            if not isinstance(payload,dict) or set(payload)!={
                "run_id","mode","seq","recorded_at","counters","error_code"}:
                raise ValueError("unexpected evidence fields")
            if str(UUID(payload["run_id"]))!=payload["run_id"]:
                raise ValueError("noncanonical run id")
            if payload["mode"] not in _ALLOWED_MODES or (
                    run_id is not None and run_id!=payload["run_id"]) or (
                    mode is not None and mode!=payload["mode"]):
                raise ValueError("run metadata conflict")
            if type(payload["seq"]) is not int or payload["seq"]!=len(records)+1:
                raise ValueError("sequence gap or duplicate")
            at=_stamp(payload["recorded_at"])
            if last_at is not None and at<=last_at:
                raise ValueError("nonmonotonic observed time")
            counters=payload["counters"]
            if not isinstance(counters,dict) or not set(counters).issubset(_ALLOWED_COUNTERS):
                raise ValueError("unexpected telemetry names")
            if not counters or any(type(v) is not int or v<0 for v in counters.values()):
                raise ValueError("invalid telemetry counters")
            code=payload["error_code"]
            if code is not None and (
                not isinstance(code,str) or not 1<=len(code)<=64 or
                any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in code)):
                raise ValueError("unsafe error code")
            if row["prev_sha256"]!=last_digest:
                raise ValueError("hash chain predecessor mismatch")
            digest=sha256(_encode({"payload":payload,"prev_sha256":last_digest})).hexdigest()
            if row["sha256"]!=digest:
                raise ValueError("shadow evidence checksum mismatch")
            last_digest=digest
            last_at=at
            run_id=payload["run_id"]
            mode=payload["mode"]
            records.append(payload)
        except (ValueError,TypeError,KeyError,OverflowError) as exc:
            raise ShadowEvidenceError("invalid or altered shadow evidence") from exc
    return records


class ShadowEvidenceJournal:
    """Append one no-secret metrics record using a POSIX exclusive file lock."""

    def __init__(self,path: str | Path, *, run_id: str,mode: str):
        self.path=Path(path)
        self.run_id=str(UUID(run_id))
        if mode not in _ALLOWED_MODES:
            raise ValueError("invalid evidence mode")
        self.mode=mode
        if fcntl is None:
            raise RuntimeError("POSIX file locking required")

    def append(self, *, recorded_at: datetime,
               counters: dict[str,int], error_code: str | None = None) -> int:
        if not isinstance(recorded_at,datetime) or recorded_at.tzinfo is None:
            raise ValueError("timezone-aware evidence time required")
        at=recorded_at.astimezone(timezone.utc)
        if not isinstance(counters,dict) or not counters or not set(counters).issubset(_ALLOWED_COUNTERS):
            raise ShadowEvidenceError("unexpected shadow telemetry fields")
        if any(type(value) is not int or value<0 for value in counters.values()):
            raise ShadowEvidenceError("invalid telemetry counter values")
        if error_code is not None and (
                not isinstance(error_code,str) or not 1<=len(error_code)<=64 or
                any(ch not in "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789_" for ch in error_code)):
            raise ShadowEvidenceError("unsafe telemetry error class")
        self.path.parent.mkdir(parents=True,exist_ok=True)
        fd=os.open(self.path,os.O_RDWR|os.O_CREAT,0o600)
        try:
            with os.fdopen(fd,"r+b") as f:
                fcntl.flock(f.fileno(),fcntl.LOCK_EX)
                existing=_read(self.path)
                if existing and (
                    existing[-1]["run_id"]!=self.run_id or
                    existing[-1]["mode"]!=self.mode):
                    raise ShadowEvidenceError("different run cannot append to evidence file")
                previous="0"*64
                if existing:
                    f.seek(0,os.SEEK_END)
                    f.seek(0)
                    previous=json.loads(f.read().splitlines()[-1])["sha256"]
                payload={"run_id":self.run_id,"mode":self.mode,
                         "seq":len(existing)+1,"recorded_at":at.isoformat(),
                         "counters":counters,"error_code":error_code}
                # Revalidate complete row before it becomes visible.
                raw={"payload":payload,"prev_sha256":previous}
                raw["sha256"]=sha256(_encode(raw)).hexdigest()
                if existing and _stamp(payload["recorded_at"])<=_stamp(existing[-1]["recorded_at"]):
                    raise ShadowEvidenceError("out-of-order observation")
                encoded=_encode(raw)+b"\n"
                f.seek(0,os.SEEK_END)
                f.write(encoded)
                f.flush()
                os.fsync(f.fileno())
                return payload["seq"]
        finally:
            pass

    def read(self) -> list[dict]:
        return _read(self.path)


def assess_shadow(records: list[dict], *,
                  min_duration_hours: float = 24, max_gap_seconds: int = 180,
                  max_pending_due: int = 250, max_review_required: int = 0) -> dict:
    """Conservative evidence check. Never claims production release approval."""
    if not isinstance(records,list):
        raise ValueError("invalid evidence list")
    if not 1<=min_duration_hours<=168 or not 30<=max_gap_seconds<=3600:
        raise ValueError("unsafe shadow duration/gap configuration")
    if any(type(x) is not int or x<0 for x in (max_pending_due,max_review_required)):
        raise ValueError("invalid backlog bounds")
    blockers=[]
    if len(records)<2:
        blockers.append("INSUFFICIENT_OBSERVATIONS")
    for a,b in zip(records,records[1:]):
        if (b["seq"]!=a["seq"]+1 or b["run_id"]!=a["run_id"] or b["mode"]!=a["mode"]):
            blockers.append("RUN_OR_SEQUENCE_GAP")
        gap=(_stamp(b["recorded_at"])-_stamp(a["recorded_at"])).total_seconds()
        if gap<=0 or gap>max_gap_seconds:
            blockers.append("SAMPLING_GAP")
    duration=(_stamp(records[-1]["recorded_at"])-
              _stamp(records[0]["recorded_at"])).total_seconds()/3600 if len(records)>=2 else 0
    if duration<min_duration_hours:
        blockers.append("DURATION_NOT_MET")
    if records and records[0]["mode"]!="OPERATOR_READ_ONLY":
        blockers.append("SYNTHETIC_NOT_REAL_SHADOW")
    necessary=frozenset({
        "failed","uncertain_commits","checkpoint_pending_due",
        "checkpoint_expired_leases","reconcile_expired_leases",
        "source_expired_leases","source_review_required","source_pending_due"})
    for payload in records:
        counters=payload["counters"]
        if not necessary.issubset(counters):
            blockers.append("MISSING_HEALTH_METRICS")
        if payload["error_code"] is not None or counters.get("failed",0)>0:
            blockers.append("ERROR_DURING_SHADOW")
        if counters.get("uncertain_commits",0)>0:
            blockers.append("UNCERTAIN_COMMIT")
        if any(counters.get(x,0)>0 for x in (
                "checkpoint_expired_leases","reconcile_expired_leases",
                "source_expired_leases")):
            blockers.append("EXPIRED_LEASE")
        if max(counters.get("checkpoint_pending_due",0),
               counters.get("source_pending_due",0))>max_pending_due:
            blockers.append("BACKLOG_EXCEEDED")
        if counters.get("source_review_required",0)>max_review_required:
            blockers.append("MANUAL_REVIEW_BACKLOG")
    distinct=sorted(set(blockers))
    return {"record_count":len(records),"duration_hours":round(duration,3),
            "evidence_mode":records[0]["mode"] if records else None,
            "blockers":distinct,"meets_observation_gates":not distinct,
            "real_24h_verified":False,"production_approved":False,
            "requires_independent_operator_attestation":True}
