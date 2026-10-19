"""Part 5D gate: no manifest can silently authorize production release."""
from datetime import datetime,timezone,timedelta
from uuid import uuid4
import json

from base_signal_engine.release_gate import (
    evaluate_release_evidence,migration_inventory,render_offline_report,_REQUIRED)
from base_signal_engine.shadow_evidence import ShadowEvidenceJournal

SHA="a"*40


def test_default_report_is_hard_no_go_and_lists_missing_migrations():
    result=evaluate_release_evidence()
    assert result.decision=="NO_GO"
    assert "MISSING_PINNED_PREVIEW_SHA" in result.blockers
    assert "REAL_SHADOW_EVIDENCE_NOT_PROVIDED" in result.blockers
    assert len(result.migrations["ordered_migrations"])==11
    assert result.migrations["missing_migrations"]==[]
    assert result.deployment_performed is False
    assert result.independently_verified is False
    assert result.migrations["source_capture_has_write_triggers"]


def test_self_certified_all_green_manifest_still_cannot_authorize_live_deploy():
    candidate={"target_preview_sha":SHA,"preview_sha_at_verification":SHA,
               "source_ref":"preview","production_ref":"main",
               "checks":{name:True for name in _REQUIRED}}
    report=evaluate_release_evidence(candidate)
    assert report.decision=="NO_GO"
    assert "OPERATOR_INDEPENDENT_ATTESTATION_REQUIRED" in report.blockers
    assert "EXPLICIT_RELEASE_ACTION_NOT_AUTHORIZED_BY_REPORT" in report.blockers
    assert report.deployment_performed is False


def test_mismatching_shas_and_nonboolean_approvals_fail_closed():
    candidate={"target_preview_sha":SHA,
               "preview_sha_at_verification":"b"*40,
               "source_ref":"main","production_ref":"preview",
               "checks":{name:1 for name in _REQUIRED}}
    out=evaluate_release_evidence(candidate)
    assert "PREVIEW_SHA_NOT_PINNED_TO_VERIFICATION" in out.blockers
    assert "WRONG_SOURCE_BRANCH" in out.blockers
    assert "PRODUCTION_REF_NOT_EXPLICIT" in out.blockers
    assert "MISSING_PREVIEW_APPROVED_BY_USER" in out.blockers


def test_missing_dependency_in_disposable_root_is_a_blocker(tmp_path):
    (tmp_path/"migrations").mkdir()
    missing=migration_inventory(tmp_path)
    assert len(missing["missing_migrations"])==11
    assert not missing["index_proposal_file_present"]
    report=evaluate_release_evidence(root=tmp_path)
    assert "MIGRATION_DEPENDENCY_MISSING" in report.blockers
    assert "APPROVAL_GATED_INDEX_PROPOSAL_MISSING" in report.blockers


def test_synthetic_shadow_24h_file_cannot_turn_gate_green(tmp_path):
    path=tmp_path/"synthetic.jsonl"
    journal=ShadowEvidenceJournal(path,run_id=str(uuid4()),mode="SYNTHETIC")
    at=datetime(2026,10,19,0,tzinfo=timezone.utc)
    counters={"failed":0,"uncertain_commits":0,
              "checkpoint_pending_due":0,"checkpoint_expired_leases":0,
              "reconcile_expired_leases":0,"source_expired_leases":0,
              "source_review_required":0,"source_pending_due":0}
    for t in (at,at+timedelta(hours=24)):
        journal.append(recorded_at=t,counters=counters)
    report=evaluate_release_evidence(shadow_path=path)
    assert "SHADOW_OBSERVATION_GATES_FAILED" in report.blockers
    assert "SYNTHETIC_NOT_REAL_SHADOW" in report.shadow["blockers"]


def test_operator_mode_also_requires_independent_attestation(tmp_path):
    path=tmp_path/"operator.jsonl"
    # Reproduce a self-forged but hash-consistent 24h file. This must still
    # not be accepted as independent, authenticated production evidence.
    from hashlib import sha256
    from base_signal_engine.shadow_evidence import _encode
    at=datetime(2026,10,19,0,tzinfo=timezone.utc)
    run=str(uuid4())
    counters={"failed":0,"uncertain_commits":0,
              "checkpoint_pending_due":0,"checkpoint_expired_leases":0,
              "reconcile_expired_leases":0,"source_expired_leases":0,
              "source_review_required":0,"source_pending_due":0}
    previous="0"*64
    with path.open("wb") as f:
        for minute in range(24*60+1):
            payload={"run_id":run,"mode":"OPERATOR_READ_ONLY",
                     "seq":minute+1,
                     "recorded_at":(at+timedelta(minutes=minute)).isoformat(),
                     "counters":counters,"error_code":None}
            envelope={"payload":payload,"prev_sha256":previous}
            digest=sha256(_encode(envelope)).hexdigest()
            f.write(_encode({**envelope,"sha256":digest})+b"\n")
            previous=digest
    r=evaluate_release_evidence(shadow_path=path)
    assert r.shadow["meets_observation_gates"]
    assert not r.shadow["real_24h_verified"]
    assert r.decision=="NO_GO"


def test_invalid_operator_evidence_is_handled_without_leaking_contents(tmp_path):
    path=tmp_path/"user_evidence.json"
    path.write_text("secret-not-repeated invalid json")
    result=render_offline_report(path)
    assert "INVALID_RELEASE_EVIDENCE" in result["blockers"]
    assert "secret-not-repeated" not in json.dumps(result)
    assert result["decision"]=="NO_GO"
