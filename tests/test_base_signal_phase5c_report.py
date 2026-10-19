"""Part 5C shadow report CLI never misreports production success."""
import json
from datetime import datetime, timezone
from uuid import uuid4

from base_signal_engine.shadow_evidence import ShadowEvidenceJournal
from base_signal_engine.shadow_report import main


def test_missing_evidence_is_not_a_shadow_success(tmp_path,capsys):
    path=tmp_path/"does_not_exist.jsonl"
    assert main(["--evidence",str(path)])==1
    output=json.loads(capsys.readouterr().out)
    assert output["production_approved"] is False
    assert "NO_EVIDENCE_FILE_OR_RECORDS" in output["blockers"]


def test_corrupt_evidence_exits_with_no_sensitive_raw_output(tmp_path,capsys):
    path=tmp_path/"corrupt.jsonl"
    path.write_text('TOKEN_DO_NOT_ECHO')
    assert main(["--evidence",str(path)])==2
    captured=capsys.readouterr().out
    assert "TOKEN_DO_NOT_ECHO" not in captured
    assert json.loads(captured)["status"]=="INVALID_EVIDENCE"


def test_single_real_mode_observation_is_not_24h_proof(tmp_path,capsys):
    path=tmp_path/"real-mode.jsonl"
    journal=ShadowEvidenceJournal(path,run_id=str(uuid4()),mode="OPERATOR_READ_ONLY")
    journal.append(recorded_at=datetime(2026,10,19,8,tzinfo=timezone.utc),
                   counters={"failed":0})
    assert main(["--evidence",str(path)])==1
    output=json.loads(capsys.readouterr().out)
    assert not output["real_24h_verified"] and not output["production_approved"]
    assert "DURATION_NOT_MET" in output["blockers"]
