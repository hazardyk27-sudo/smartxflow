"""Deterministic fixture-only cold export: checksum, resume, atomic manifest tests."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
from urllib.parse import unquote

import pytest

PATH=Path(__file__).resolve().parents[1]/"scripts"/"maintenance"/"sxf_archive_fixture_cold_export.py"
spec=importlib.util.spec_from_file_location("sxf_archive_fixture_cold_export",PATH)
m=importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


def row(i=1,kickoff="2026-10-09T20:00:00+00:00",local="2026-10-09"):
    return {
        "source_internal_id":i,
        "fixture_uid":f"f9d7a59a-8fbf-4f1f-8e48-{i:012x}",
        "kickoff_utc":kickoff,
        "local_date":local,
        "match_id_hash":"shared-hash-is-NOT-identity",
    }


class FakeStorage:
    def __init__(self):
        self.blobs={}
        self.writes=[]
        self.fail_after=None

    def get(self,url,headers,timeout):
        if url not in self.blobs:
            return SimpleNamespace(status_code=404,content=b"")
        return SimpleNamespace(status_code=200,content=self.blobs[url])

    def post(self,url,headers,data,timeout):
        if self.fail_after is not None and len(self.writes)>=self.fail_after:
            return SimpleNamespace(status_code=503)
        if url in self.blobs:
            return SimpleNamespace(status_code=409)
        self.writes.append(url)
        self.blobs[url]=data
        return SimpleNamespace(status_code=201)


def test_pg_snapshot_query_never_offsets_or_uses_ctid():
    assert "REPEATABLE READ READ ONLY" in m.QUERY
    assert "ORDER BY a.source_internal_id" in m.QUERY
    assert "OFFSET" not in m.QUERY
    assert "ctid" not in m.QUERY
    assert "UPDATE " not in m.QUERY
    assert "DELETE " not in m.QUERY
    assert "INSERT " not in m.QUERY


def test_physical_identity_and_local_date_checked_before_export():
    sample=[row(2),row(1)]
    fake=lambda argv,**kw:SimpleNamespace(stdout="\\n".join(json.dumps(x) for x in sample))
    with pytest.raises(ValueError,match="sort order"):
        m.read_fixtures(run=fake)
    fake=lambda argv,**kw:SimpleNamespace(stdout=json.dumps(row(1,local="2026-10-10")))
    with pytest.raises(ValueError,match="kickoff day"):
        m.read_fixtures(run=fake)
    fake=lambda argv,**kw:SimpleNamespace(stdout=json.dumps(row(1,kickoff="2026-10-09T20:00:00")))
    with pytest.raises(ValueError,match="Timezone-naive"):
        m.read_fixtures(run=fake)


def test_manifest_deterministic_and_never_claims_full_backup():
    a1,o1=m.build_package([row(1),row(2)])
    a2,o2=m.build_package([row(1),row(2)])
    assert a1==a2 and o1==o2
    assert a1["rows"]==2
    assert a1["full_raw_history_parity_verified"] is False
    assert a1["independent_offsite_backup_verified"] is False
    assert a1["restored_from_cold_backup_verified"] is False
    assert a1["retention_cleanup_allowed"] is False
    assert len(a1["parts"])==1
    assert m.sha(next(v for k,v in o1.items() if k.endswith(".gz")))==a1["parts"][0]["sha256"]


def test_export_resume_and_manifest_uploaded_last_only_when_parts_verified():
    _manifest,objects=m.build_package([row(i) for i in range(1,503)])
    fake=FakeStorage()
    fake.fail_after=1
    with pytest.raises(RuntimeError,match="upload failed"):
        m.send_package("https://abc.supabase.co/","service-key",objects,session=fake)
    assert len(fake.blobs)==1
    assert not any(x.endswith("/manifest.json") for x in fake.blobs)
    fake.fail_after=None
    summary=m.send_package("https://abc.supabase.co/","service-key",objects,session=fake)
    assert summary["already_verified_files"]==1
    assert summary["uploaded_files"]==2
    assert fake.writes[-1].endswith("/manifest.json")
    summary=m.send_package("https://abc.supabase.co/","service-key",objects,session=fake)
    assert summary["already_verified_files"]==3
    assert summary["uploaded_files"]==0
    assert summary["retention_cleanup_allowed"] is False


def test_tampered_existing_blob_blocks_final_manifest():
    _manifest,objects=m.build_package([row(1)])
    fake=FakeStorage()
    part=next(k for k in objects if k.endswith(".gz"))
    fake.blobs[m.bucket_object_url("https://abc.supabase.co",part)]=b"corrupt"
    with pytest.raises(RuntimeError,match="checksum conflict"):
        m.send_package("https://abc.supabase.co","service-key",objects,session=fake)
    assert not any(x.endswith("/manifest.json") for x in fake.blobs)


def test_default_cli_never_contacts_storage(monkeypatch,capsys):
    monkeypatch.setattr(m,"read_fixtures",lambda:[row(1),row(2)])
    monkeypatch.setattr(m,"send_package",lambda *a,**kw: (_ for _ in ()).throw(AssertionError("storage write must not happen")))
    assert m.main([])==0
    result=json.loads(capsys.readouterr().out)
    assert result["mode"]=="READ_ONLY_PLAN"
    assert result["parts"]==1
    assert result["independent_backup"] is False


def test_apply_requires_independent_explicit_authorization(monkeypatch,capsys):
    monkeypatch.delenv(m.AUTH_ENV,raising=False)
    monkeypatch.setattr(m,"read_fixtures",lambda: (_ for _ in ()).throw(AssertionError("no DB access")))
    assert m.main(["--apply"])==3
    assert "BLOCKED" in capsys.readouterr().err


def test_invalid_remote_url_rejected_before_service_token_exposure():
    with pytest.raises(ValueError):
        m.bucket_object_url("http://abc.supabase.co","p")
    with pytest.raises(ValueError):
        m.bucket_object_url("https://attacker.invalid","p")
    assert m.bucket_object_url("https://abc.supabase.co/","p")== "https://abc.supabase.co/storage/v1/object/sxf-research-archive/p"
