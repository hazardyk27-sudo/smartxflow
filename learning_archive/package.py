from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import gzip
import hashlib
import io
import json
from typing import Any

from .postmatch_learning import build_postmatch_learning_note, postmatch_learning_filename
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


def _parse_utc(value: str, field: str) -> datetime:
    raw = value[:-1] + "+00:00" if value.endswith("Z") else value
    dt = datetime.fromisoformat(raw)
    if dt.tzinfo is None or dt.utcoffset() is None:
        raise ValueError(f"{field} must include timezone")
    return dt.astimezone(timezone.utc)


def _parse_utc_date(value: str) -> tuple[int, int, int]:
    dt = _parse_utc(value, "prediction_at")
    return dt.year, dt.month, dt.day


def _case_path(case: dict[str, Any]) -> str:
    case_id = str(case["case_id"])
    year, month, day = _parse_utc_date(case["prediction"]["prediction_at"])
    return f"cases/{year:04d}/{month:02d}/{day:02d}/{case_id}"


def _case_doc(case: dict[str, Any]) -> dict[str, Any]:
    provenance = case["provenance"]
    immutable_provenance = {
        key: provenance[key]
        for key in ("archive_created_at", "source_repo", "source_commit")
        if key in provenance
    }
    return {
        "archive_schema_version": case["archive_schema_version"],
        "case_id": case["case_id"],
        "match": case["match"],
        "prediction": case["prediction"],
        "provenance": immutable_provenance,
    }


def _ordered_snapshots(snapshots: list[dict[str, Any]]) -> list[dict[str, Any]]:
    indexed = list(enumerate(snapshots))
    indexed.sort(key=lambda pair: (
        str(pair[1].get("scraped_at_utc") or pair[1].get("scraped_at") or pair[1].get("observed_at") or pair[1].get("created_at") or ""),
        str(pair[1].get("_archive_source_table") or pair[1].get("market") or ""),
        pair[0],
    ))
    return [item for _, item in indexed]


def _payload_summary(payloads: dict[str, bytes]) -> str:
    lines = [f"{sha256_hex(payloads[name])}  {name}" for name in sorted(payloads)]
    return sha256_hex(("\n".join(lines) + "\n").encode("utf-8"))


def capture_filename(observed_at: str) -> str:
    dt = _parse_utc(observed_at, "observed_at")
    stamp = dt.strftime("%Y%m%dT%H%M%S")
    if dt.microsecond:
        stamp += "." + f"{dt.microsecond:06d}".rstrip("0")
    stamp += "Z"
    return f"captures/{stamp}.json.gz"


@dataclass(frozen=True)
class ArchivePackage:
    case_id: str
    case_path: str
    files: dict[str, bytes]
    checksum_summary: str
    package_kind: str = "FINALIZED"
    event_key: str = "final"

    def file_path(self, filename: str) -> str:
        return f"{self.case_path}/{filename}"


def build_record_package(
    case: dict[str, Any],
    snapshots: list[dict[str, Any]],
    observed_at: str,
    *,
    revisit: bool = False,
) -> ArchivePackage:
    case_id = str(case["case_id"])
    capture_path = capture_filename(observed_at)
    payloads = {
        "case.json": canonical_json_bytes(_case_doc(case)),
        "evidence.json": canonical_json_bytes(classify_evidence_phase(case)),
        capture_path: deterministic_gzip_json(_ordered_snapshots(snapshots)),
    }
    return ArchivePackage(
        case_id=case_id,
        case_path=_case_path(case),
        files=payloads,
        checksum_summary=_payload_summary(payloads),
        package_kind="CAPTURED" if revisit else "RECORDED",
        event_key=capture_path,
    )


def _postmatch_observed_at(case: dict[str, Any]) -> str:
    provenance = case.get("provenance") or {}
    settlement = case.get("settlement") or {}
    observed_at = str(
        provenance.get("archive_finalized_at")
        or settlement.get("result_observed_at")
        or provenance.get("archive_created_at")
        or ""
    ).strip()
    if not observed_at:
        raise ValueError("finalized archive package requires a postmatch observed_at timestamp")
    _parse_utc(observed_at, "postmatch_observed_at")
    return observed_at


def build_archive_package(case: dict[str, Any], snapshots: list[dict[str, Any]]) -> ArchivePackage:
    case_id = str(case["case_id"])
    ordered_snapshots = _ordered_snapshots(snapshots)
    payloads = {
        "case.json": canonical_json_bytes(_case_doc(case)),
        "evidence.json": canonical_json_bytes(classify_evidence_phase(case)),
        "settlement.json": canonical_json_bytes(case["settlement"]),
        "sxf_snapshots.json.gz": deterministic_gzip_json(ordered_snapshots),
    }
    checksum_lines = [f"{sha256_hex(payloads[name])}  {name}" for name in sorted(payloads)]
    checksums = ("\n".join(checksum_lines) + "\n").encode("utf-8")
    payloads["checksums.sha256"] = checksums

    # Postmatch learning is append-only learning metadata, not a rewrite of the
    # immutable prediction/evidence core. Keep the historical core checksum set
    # backward compatible while requiring every newly finalized package to carry
    # a standardized postmatch observation.
    observed_at = _postmatch_observed_at(case)
    learning_note = build_postmatch_learning_note(
        case,
        ordered_snapshots,
        observed_at=observed_at,
    )
    payloads[postmatch_learning_filename(observed_at)] = canonical_json_bytes(learning_note)

    return ArchivePackage(
        case_id=case_id,
        case_path=_case_path(case),
        files=payloads,
        checksum_summary=sha256_hex(checksums),
        package_kind="FINALIZED",
        event_key="final",
    )


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
