"""Sampled snapshot-tail checks are read-only and never source-capture proof."""
from base_signal_engine import source_tail_probe as probe
import pytest


class FakeReader:
    def __init__(self,rows):
        self.rows=rows
        self.calls=[]
    def _get(self,table,params):
        self.calls.append((table,params))
        return self.rows


def row(i,*,odds="1.80",uid="74acc8bd-665e-488c-b1e7-32f95674ccdd"):
    return {"id":i,"fixture_uid":uid,"match_id_hash":"hashone",
            "market":"1X2","selection":"1","odds":odds,
            "volume":"35.00","share":"10.00",
            "scraped_at_utc":"2026-10-19T19:20:00+00:00"}


def test_tail_sample_is_strict_bounded_get_and_digest_only():
    reader=FakeReader([row(102),row(101),row(100,uid=None)])
    state=probe.sample_tail(reader,limit=4)
    assert state["head_id"]==102 and state["floor_id"]==100
    assert state["rows"]==3 and state["null_uid_rows"]==1
    assert len(state["digests"])==3
    assert reader.calls==[("moneyway_snapshots",[
        ("select",",".join(probe.FIELDS)),("order","id.desc"),("limit","4")])]
    assert "1.80" not in str(state) and "hashone" not in str(state)
    assert "74acc8bd" not in str(state)


def test_tail_comparison_detects_overlap_mutation_and_potential_delete():
    first=probe.sample_tail(FakeReader([row(104),row(103),row(102),row(101)]),limit=4)
    second=probe.sample_tail(FakeReader([row(106),row(105),row(104,odds="1.70")]),limit=4)
    result=probe.compare_tail(first,second)
    assert result["status"]=="MUTATION_SUSPECTED"
    assert result["overlap"]==1 and result["changed"]==1
    assert result["potential_missing"]==0
    assert not result["source_mutation_capture_verified"]

    third=probe.sample_tail(FakeReader([row(106),row(105),row(102)]),limit=4)
    result=probe.compare_tail(second,third)
    assert result["potential_missing"]==1  # id 104 still above new floor
    assert result["status"]=="MUTATION_SUSPECTED"


def test_tail_comparison_no_overlap_is_not_success_attestation():
    first=probe.sample_tail(FakeReader([row(4),row(3)]),limit=2)
    second=probe.sample_tail(FakeReader([row(100),row(99)]),limit=2)
    assert probe.compare_tail(None,first)["status"]=="BASELINE_ONLY"
    report=probe.compare_tail(first,second)
    assert report["status"]=="NO_OVERLAP_UNVERIFIED"
    assert report["source_mutation_capture_verified"] is False


def test_strict_sample_rejects_order_invalid_row_and_unsafe_limit():
    for values in ([row(1),row(2)],[row(4),row(4)],[row(3,odds="1.8"),{"id":2}],[]):
        with pytest.raises(ValueError):
            probe.sample_tail(FakeReader(values),limit=4)
    for n in (0,501,-1,True):
        with pytest.raises(ValueError):
            probe.sample_tail(FakeReader([row(4)]),limit=n)


def test_local_digest_state_is_private_and_rejects_corruption(tmp_path):
    state=probe.sample_tail(FakeReader([row(3),row(2)]))
    path=tmp_path/"audit-state.json"
    probe._save(path,state)
    assert path.stat().st_mode & 0o777==0o600
    assert probe._load(path)==state
    path.write_text('{"malformed":true}')
    with pytest.raises(ValueError):
        probe._load(path)


def test_source_tail_probe_cli_requires_opt_in(monkeypatch):
    monkeypatch.delenv("SXF_BASE_SOURCE_TAIL_PROBE_APPROVED",raising=False)
    with pytest.raises(SystemExit,match="2"):
        probe.main(["--state","/tmp/never-write-source-tail.json"])


def test_decreasing_head_requires_review_even_when_some_rows_overlap():
    old=probe.sample_tail(FakeReader([row(105),row(104),row(103)]),limit=3)
    new=probe.sample_tail(FakeReader([row(104),row(103)]),limit=3)
    report=probe.compare_tail(old,new)
    assert report["status"]=="HEAD_REGRESSION_REVIEW"
    assert report["head_advanced"] is False
    assert report["source_mutation_capture_verified"] is False
