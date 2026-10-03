from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from typing import Any

from .validator import classify_evidence_phase


def canonical_json_bytes(value: Any) -> bytes:
    return (json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")) + "\n").encode("utf-8")


def deterministic_gzip_json(value: Any) -> bytes:
    raw = canonical_json_bytes(value)
    buffer = io.BytesIO()
    with gzip.GzipFile(filename="", mode="wb", fileobj=buffer, mtime=0) as gz:
        gz.write(raw)
    return buffer.getvalue()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _parse_utc_date(value: str) -> tuple[int, int, int]:
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError("prediction_at must include timezone")
    utc = dt.astimezone(timezone.utc)
    return utc.year, utc.month, utc.day


@dataclass(frozen=True)
class ArchivePackage:
    case_id: str
    case_path: str
    files: dict[str, bytes]
    checksum_summary: str

    def file_path(self, filename: str) -> str:
        return f"{self.case_path}/{filename}"


def build_archive_package(case: dict[str, Any], snapshots: list[dict[str, Any]]) -> ArchivePackage:
    case_id = str(case["case_id"])
    year, month, day = _parse_utc_date(case["prediction"]["prediction_at"])
    case_path = f"cases/{year:04d}/{month:02d}/{day:02d}/{case_id}"

    case_doc = {
        "archive_schema_version": case["archive_schema_version"],
        "case_id": case["case_id"],
        "match": case["match"],
        "prediction": case["prediction"],
        "provenance": case["provenance"],
    }
    evidence_doc = classify_evidence_phase(case)
    settlement_doc = case["settlement"]

    indexed = list(enumerate(snapshots))
    indexed.sort(key=lambda pair: (
        str(pair[1].get("scraped_at_utc") or pair[1].get("scraped_at") or pair[1].get("observed_at") or pair[1].get("created_at") or ""),
        pair[0],
    ))
    ordered_snapshots = [item for _, item in indexed]

    payloads = {
        "case.json": canonical_json_bytes(case_doc),
        "evidence.json": canonical_json_bytes(evidence_doc),
        "settlement.json": canonical_json_bytes(settlement_doc),
        "sxf_snapshots.json.gz": deterministic_gzip_json(ordered_snapshots),
    }
    checksum_lines = [f"{sha256_hex(payloads[name])}  {name}" for name in sorted(payloads)]
    checksums = ("\n".join(checksum_lines) + "\n").encode("utf-8")
    payloads["checksums.sha256"] = checksums
    summary = sha256_hex(checksums)
    return ArchivePackage(case_id=case_id, case_path=case_path, files=payloads, checksum_summary=summary)


def verify_package_checksums(package: ArchivePackage) -> tuple[bool, tuple[str, ...]]:
    errors: list[str] = []
    raw = package.files.get("checksums.sha256")
    if raw is None:
        return False, ("checksums.sha256 missing",)
    expected: dict[str, str] = {}
    for line in raw.decode("utf-8").splitlines():
        if not line.strip():
            continue
        try:
            digest, name = line.split("  ", 1)
        except ValueError:
            errors.append("checksums.sha256 malformed line")
            continue
        expected[name] = digest
    for name, digest in expected.items():
        payload = package.files.get(name)
        if payload is None:
            errors.append(f"{name}: referenced by checksums but missing")
        elif sha256_hex(payload) != digest:
            errors.append(f"{name}: checksum mismatch")
    return not errors, tuple(sorted(set(errors)))
