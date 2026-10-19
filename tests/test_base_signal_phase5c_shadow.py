"""Part 5C1 local shadow evidence: integrity, clock gaps, release safety."""
import json
from datetime import datetime, timedelta, timezone
from uuid import uuid4

import pytest
from base_signal_engine.shadow_evidence import (
    ShadowEvidenceJournal, ShadowEvidenceError, assess_shadow)

AT=datetime(2026,10,19,0,tzinfo=timezone.utc)
COUNTERS={
    "failed":0,"uncertain_commits":0,"checkpoint_pending_due":0,
    "checkpoint_expired_leases":0,"reconcile_expired_leases":0,
    "source_expired_leases":0,"source_review_required":0,
    "source_pending_due":0,"fixtures_discovered":6,"committed":3,
}


def journal(tmp_path, *, mode="SYNTHETIC", run=None):
    return ShadowEvidenceJournal(tmp_path/"shadow.jsonl",
                                 run_id=run or str(uuid4()),mode=mode)


def test_append_and_revalidate_hash_chain_and_sequence(tmp_path):
    w=journal(tmp_path)
    assert w.append(recorded_at=AT,counters=COUNTERS)==1
    assert w.append(recorded_at=AT+timedelta(seconds=30),counters=COUNTERS)==2
    records=w.read()
    assert [r["seq"] for r in records]==[1,2]
    with pytest.raises(ShadowEvidenceError,match="different run"):
        journal(tmp_path).append(recorded_at=AT+timedelta(minutes=1),counters=COUNTERS)


def test_corrupt_content_and_truncated_line_rejected(tmp_path):
    w=journal(tmp_path)
    w.append(recorded_at=AT,counters=COUNTERS)
    path=tmp_path/"shadow.jsonl"
    content=path.read_text()
    path.write_text(content.replace('"committed":3','"committed":8'))
    with pytest.raises(ShadowEvidenceError):
        w.read()
    path.write_text(content.rstrip("\n"))
    with pytest.raises(ShadowEvidenceError,match="unterminated"):
        w.read()


def test_nonmonotonic_clock_and_unauthorized_extra_fields_rejected(tmp_path):
    w=journal(tmp_path)
    w.append(recorded_at=AT,counters=COUNTERS)
    with pytest.raises(ShadowEvidenceError,match="out-of-order"):
        w.append(recorded_at=AT,counters=COUNTERS)
    with pytest.raises(ShadowEvidenceError):
        w.append(recorded_at=AT+timedelta(minutes=1),
                 counters={**COUNTERS,"secret_key":1})
    assert len(w.read())==1


def test_synthetic_24_hour_records_never_count_as_actual_production():
    samples=[{"seq":i+1,"run_id":"one","mode":"SYNTHETIC",
             "recorded_at":(AT+timedelta(minutes=i)).isoformat(),
             "counters":COUNTERS,"error_code":None}
             for i in range(1441)]
    review=assess_shadow(samples,max_gap_seconds=180)
    assert review["duration_hours"]==24
    assert review["blockers"]==["SYNTHETIC_NOT_REAL_SHADOW"]
    assert not review["real_24h_verified"] and not review["production_approved"]


def test_operator_mode_without_24h_or_health_is_never_green():
    small=[{"seq":1,"run_id":"r","mode":"OPERATOR_READ_ONLY",
            "recorded_at":AT.isoformat(),"counters":{"failed":0},"error_code":None}]
    review=assess_shadow(small)
    assert "INSUFFICIENT_OBSERVATIONS" in review["blockers"]
    assert "MISSING_HEALTH_METRICS" in review["blockers"]


def test_error_gap_backlog_and_lease_count_as_independent_blockers():
    rows=[{"seq":1,"run_id":"r","mode":"OPERATOR_READ_ONLY",
           "recorded_at":AT.isoformat(),
           "counters":{**COUNTERS,"failed":1,"source_review_required":1},
           "error_code":"SNAPSHOTREADERROR"},
          {"seq":2,"run_id":"r","mode":"OPERATOR_READ_ONLY",
           "recorded_at":(AT+timedelta(hours=24)).isoformat(),
           "counters":{**COUNTERS,"checkpoint_expired_leases":1,
                       "source_pending_due":300},
           "error_code":None}]
    report=assess_shadow(rows)
    assert {"ERROR_DURING_SHADOW","SAMPLING_GAP","EXPIRED_LEASE",
            "MANUAL_REVIEW_BACKLOG","BACKLOG_EXCEEDED"}<=set(report["blockers"])


def test_well_formed_operator_24h_still_requires_independent_attestation():
    records=[{"seq":i+1,"run_id":"operator-run","mode":"OPERATOR_READ_ONLY",
              "recorded_at":(AT+timedelta(minutes=i)).isoformat(),
              "counters":COUNTERS,"error_code":None} for i in range(1441)]
    report=assess_shadow(records)
    assert report["meets_observation_gates"]
    assert report["requires_independent_operator_attestation"]
    assert not report["real_24h_verified"] and not report["production_approved"]


def test_unsupported_metrics_and_invalid_timestamp_fail_before_append(tmp_path):
    w=journal(tmp_path)
    with pytest.raises(ValueError):
        w.append(recorded_at=datetime(2026,10,19),counters=COUNTERS)
    with pytest.raises(ShadowEvidenceError):
        w.append(recorded_at=AT,counters={**COUNTERS,"password":7})
    assert not w.path.exists() or not w.path.read_bytes()
