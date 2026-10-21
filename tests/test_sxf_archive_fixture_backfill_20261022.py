"""Preproduction contracts for physical fixture archive gap replay (no DB)."""
import importlib.util
import json
from pathlib import Path
from types import SimpleNamespace
import subprocess

import pytest

PATH = Path(__file__).resolve().parents[1] / "scripts" / "maintenance" / "sxf_archive_fixture_backfill.py"
spec = importlib.util.spec_from_file_location("sxf_archive_fixture_backfill", PATH)
m = importlib.util.module_from_spec(spec)
spec.loader.exec_module(m)


@pytest.mark.parametrize("day", ["2026-10-04", "2026-10-09", "2026-10-21", "2026-10-22", "abc"])
def test_other_days_cannot_be_backfilled(day):
    with pytest.raises(ValueError):
        m.plan_sql(day, 0, 25)
    with pytest.raises(ValueError):
        m.apply_sql(day, 0, 25)


@pytest.mark.parametrize("cursor,limit", [(-1, 25), (0, 0), (0, 26)])
def test_out_of_bounds_pages_blocked(cursor, limit):
    with pytest.raises(ValueError):
        m.plan_sql("2026-10-05",cursor,limit)


def test_planner_is_readonly_has_physical_identity_and_safety_flags():
    sql=m.plan_sql("2026-10-05",0,25)
    assert "BEGIN TRANSACTION READ ONLY" in sql
    assert "2026-10-05" in sql
    assert "ORDER BY s.internal_id ASC LIMIT 25" in sql
    assert "s.fixture_uid" in sql
    assert "a.fixture_uid=s.fixture_uid" in sql
    assert "a.source_internal_id=s.internal_id" in sql
    assert "AT TIME ZONE 'Europe/Istanbul'" in sql
    assert "archive_parity_proven',false" in sql
    assert "cold_backup_verified',false" in sql
    assert "retention_cleanup_allowed',false" in sql
    assert "INSERT INTO" not in sql.upper()
    assert "DELETE FROM" not in sql.upper()
    assert "UPDATE " not in sql.upper()


def test_apply_is_append_only_and_collision_guarded():
    sql=m.apply_sql("2026-10-08",150,10)
    assert "BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ" in sql
    assert "SET LOCAL lock_timeout='1s'" in sql
    assert "SET LOCAL statement_timeout='8s'" in sql
    assert "pg_advisory_xact_lock" in sql
    assert "SXF_ARCHIVE_PHYSICAL_IDENTITY_CONFLICT" in sql
    assert "ON CONFLICT (source_internal_id) DO NOTHING" in sql
    assert "INSERT INTO research_archive.fixtures" in sql
    assert "WHERE s.internal_id > 150" in sql
    assert "ORDER BY s.internal_id ASC LIMIT 10" in sql
    assert "a.fixture_uid=s.fixture_uid" in sql
    assert "source_fixture_date" in sql
    assert "retention_cleanup_allowed',false" in sql
    assert "DELETE FROM" not in sql.upper()
    assert "UPDATE " not in sql.upper()
    assert "TRUNCATE " not in sql.upper()
    assert "DROP TABLE" not in sql.upper()


def test_default_cli_only_submits_read_only_query(monkeypatch,capsys):
    run=[]
    def fake_psql(argv, **kw):
        run.append((argv,kw))
        assert kw["input"].startswith("BEGIN TRANSACTION READ ONLY")
        assert "INSERT INTO" not in kw["input"]
        return SimpleNamespace(stdout=json.dumps({"mode":"READ_ONLY","conflicts":0,"next_after_id":25})+"\\n")
    monkeypatch.setattr(m.subprocess,"run",fake_psql)
    assert m.main(["--day","2026-10-05"])==0
    assert len(run)==1
    assert run[0][0][:3]==["psql","-X","-q"]
    assert "READ_ONLY" in capsys.readouterr().out


def test_apply_requires_separate_exact_authorization(monkeypatch,capsys):
    monkeypatch.delenv(m.APPROVAL_ENV,raising=False)
    monkeypatch.setattr(m,"execute_psql",lambda _: (_ for _ in ()).throw(AssertionError("DB should not be contacted")))
    assert m.main(["--day","2026-10-06","--apply"])==3
    assert "BLOCKED" in capsys.readouterr().err


def test_exact_authorization_allows_only_append_only_sql(monkeypatch):
    monkeypatch.setenv(m.APPROVAL_ENV,m.APPROVAL_VALUE)
    seen=[]
    monkeypatch.setattr(m,"execute_psql",lambda sql: seen.append(sql) or {"mode":"APPEND_ONLY_APPLY","inserted":5})
    assert m.main(["--day","2026-10-07","--apply","--limit","5"])==0
    assert len(seen)==1
    assert "INSERT INTO research_archive.fixtures" in seen[0]


def test_psql_failure_returns_blocked_not_credentials(monkeypatch,capsys):
    monkeypatch.setattr(m.subprocess,"run",lambda *args, **kwargs: (_ for _ in ()).throw(
        subprocess.CalledProcessError(1,"psql",stderr="secret password")))
    assert m.main(["--day","2026-10-08"])==3
    captured=capsys.readouterr()
    assert "secret password" not in captured.err
    assert "BLOCKED" in captured.err
