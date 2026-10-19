"""Part 5D: deliberately conservative, offline production readiness gate.

A tool cannot grant deployment approval. This parser reviews operator-provided
evidence; it never executes migrations, connects to production, or marks a
self-declared record as independently authenticated.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Mapping
import json
import re

from .shadow_evidence import _read, assess_shadow, ShadowEvidenceError

_MIGRATION_SEQUENCE = (
    "2026_10_18_sxf_base_durable_queue.sql",
    "2026_10_19_sxf_base_phase4a_waiting_data_hardening.sql",
    "2026_10_19_sxf_base_phase4b_reconciliation_rpc.sql",
    "2026_10_19_sxf_base_phase4c_reconcile_queue.sql",
    "2026_10_19_sxf_base_phase4c_discovery_cursor.sql",
    "2026_10_19_sxf_base_phase4c4_kickoff_drift.sql",
    "2026_10_19_sxf_base_phase4c4_discovery_heartbeat.sql",
    "2026_10_19_sxf_base_phase4c4_health.sql",
    "2026_10_19_sxf_base_phase4c4_projection.sql",
    "2026_10_19_sxf_base_phase5a_source_capture_PROPOSED.sql",
    "2026_10_19_sxf_base_phase5b_source_health.sql",
)
_OPTIONAL_INDEX = "2026_10_18_sxf_base_snapshot_index_APPROVAL_REQUIRED.sql"
_HEX40 = re.compile(r"^[0-9a-f]{40}$")

_REQUIRED = (
    "source_schema_readonly_verified",
    "source_retention_verified",
    "fixture_uid_remap_and_cancellation_reviewed",
    "source_trigger_owner_and_rls_audited",
    "producer_transaction_write_load_benchmarked",
    "source_snapshot_index_explain_verified",
    "historical_bootstrap_and_gap_accounted",
    "snapshot_update_delete_policy_reviewed",
    "consumer_and_backlog_alarm_reviewed",
    "rollback_dry_run_verified",
    "real_shadow_externally_attested",
    "preview_ui_tested_on_exact_sha",
    "preview_approved_by_user",
    "live_migration_explicitly_approved_by_user",
    "production_promotion_explicitly_approved_by_user",
)
_NO_GO_CODE = "NO_GO"
_ROOT = Path(__file__).resolve().parents[1]


def migration_inventory(root: Path | None = None) -> dict:
    """Dependency order from GitHub source. Never run these files."""
    directory=(root or _ROOT)/"migrations"
    absent=[name for name in _MIGRATION_SEQUENCE if not (directory/name).is_file()]
    optional=(directory/_OPTIONAL_INDEX).is_file()
    return {
        "ordered_migrations":list(_MIGRATION_SEQUENCE),
        "missing_migrations":absent,
        "source_capture_has_write_triggers":True,
        "index_requires_independent_approval":True,
        "index_proposal_file_present":optional,
    }


@dataclass(frozen=True)
class ReadinessReport:
    decision: str
    blockers: tuple[str,...]
    target_preview_sha: str | None
    migrations: dict
    shadow: dict
    independently_verified: bool = False
    deployment_performed: bool = False

    def as_dict(self) -> dict:
        return {
            "decision":self.decision,"blockers":list(self.blockers),
            "target_preview_sha":self.target_preview_sha,
            "migrations":self.migrations,"shadow":self.shadow,
            "independently_verified":self.independently_verified,
            "deployment_performed":self.deployment_performed,
        }


def evaluate_release_evidence(evidence: Mapping[str,Any] | None = None, *,
                              shadow_path: str | Path | None = None,
                              root: Path | None = None) -> ReadinessReport:
    """NO-GO if ANY proof is absent. Self-declarations do not authorize writes.

    A nominal complete report is still NO-GO: real approval requires
    authentication and independent operator checks outside this process.
    """
    evidence=dict(evidence or {})
    blockers=[]
    source_sha=evidence.get("target_preview_sha")
    if not isinstance(source_sha,str) or not _HEX40.fullmatch(source_sha):
        blockers.append("MISSING_PINNED_PREVIEW_SHA")
        source_sha=None
    verified_sha=evidence.get("preview_sha_at_verification")
    if verified_sha!=source_sha or verified_sha is None:
        blockers.append("PREVIEW_SHA_NOT_PINNED_TO_VERIFICATION")
    if evidence.get("source_ref")!="preview":
        blockers.append("WRONG_SOURCE_BRANCH")
    if evidence.get("production_ref")!="main":
        blockers.append("PRODUCTION_REF_NOT_EXPLICIT")
    checks=evidence.get("checks")
    checks=checks if isinstance(checks,Mapping) else {}
    for name in _REQUIRED:
        if checks.get(name) is not True:
            blockers.append("MISSING_"+name.upper())
    # A self-asserted true means only the user supplied a record. It does not
    # authenticate actor identity or the state of GitHub/live services.
    blockers.append("OPERATOR_INDEPENDENT_ATTESTATION_REQUIRED")
    blockers.append("EXPLICIT_RELEASE_ACTION_NOT_AUTHORIZED_BY_REPORT")
    inventory=migration_inventory(root)
    if inventory["missing_migrations"]:
        blockers.append("MIGRATION_DEPENDENCY_MISSING")
    if not inventory["index_proposal_file_present"]:
        blockers.append("APPROVAL_GATED_INDEX_PROPOSAL_MISSING")
    shadow={"status":"NOT_SUBMITTED","real_24h_verified":False}
    if shadow_path is None:
        blockers.append("REAL_SHADOW_EVIDENCE_NOT_PROVIDED")
    else:
        try:
            shadow=assess_shadow(_read(Path(shadow_path)))
            if shadow["blockers"]:
                blockers.append("SHADOW_OBSERVATION_GATES_FAILED")
        except (ShadowEvidenceError,ValueError,TypeError,OSError):
            blockers.append("INVALID_SHADOW_EVIDENCE")
            shadow={"status":"INVALID","real_24h_verified":False}
    return ReadinessReport(
        decision=_NO_GO_CODE,
        blockers=tuple(sorted(set(blockers))),
        target_preview_sha=source_sha,
        migrations=inventory,shadow=shadow,
    )


def render_offline_report(evidence_json_path: str | Path | None = None,
                          shadow_path: str | Path | None = None,
                          *, root: Path | None = None) -> dict:
    """Never leak contents of supplied operator evidence in report/logs."""
    candidate=None
    if evidence_json_path is not None:
        try:
            data=Path(evidence_json_path).read_bytes()
            if len(data)>32768:
                raise ValueError("oversize approval evidence")
            candidate=json.loads(data)
            if not isinstance(candidate,dict):
                raise ValueError("invalid approval evidence shape")
        except (ValueError,TypeError,OSError):
            report=evaluate_release_evidence(shadow_path=shadow_path,root=root).as_dict()
            report["blockers"]=sorted(set(report["blockers"]+["INVALID_RELEASE_EVIDENCE"]))
            return report
    return evaluate_release_evidence(candidate,shadow_path=shadow_path,root=root).as_dict()
