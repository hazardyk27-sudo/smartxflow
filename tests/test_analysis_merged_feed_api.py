"""No live DB: execute only the existing PRO-gated API function in isolation.

The AST preserves the real application route body (not a hand-copied mock) and
replaces framework modules, network clients, and the two private feeds with
safe in-memory fakes. Test process cannot access Supabase or production.
"""
from __future__ import annotations
import ast
from datetime import date, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[1]
CODE=(ROOT/"app.py").read_text()
FN=next(node for node in ast.parse(CODE).body
        if isinstance(node,ast.FunctionDef) and node.name=="base_signal_feed_api")

class Unavailable(Exception):
    pass

class LegacySource:
    fail=False
    calls=0
    def __init__(self,source): self.source=source
    def read(self,*args,**kwargs):
        self.__class__.calls+=1
        if self.__class__.fail: raise Unavailable("legacy private source down")
        return {"items":[{"id":100000000001,"kickoff_utc":"2026-10-20T19:00:00Z"}],
                "engines":["LEGACY_EARLY_MONEY_LOCK"],
                "source_rows":{"LEGACY_EARLY_MONEY_LOCK":1},
                "identity_excluded":0,"duplicate_events_removed":0}

class BaseSource:
    fail=False
    calls=0
    def __init__(self,*args): pass
    def read(self,*args,**kwargs):
        self.__class__.calls+=1
        if self.__class__.fail: raise Unavailable("base private source down")
        return {"status":"ok","items":[{"id":2,"kickoff_utc":"2026-10-20T10:00:00Z"}],
                "engines":["1X2_CONCENTRATION_V1"],"phase":"SHADOW"}

def route(*,plan="pro",account=False):
    # Extract the actual route implementation; stubs supply imports only.
    node=ast.FunctionDef(name=FN.name,args=FN.args,body=[
        item for item in FN.body if not isinstance(item,ast.ImportFrom)
    ],decorator_list=[],returns=FN.returns,type_comment=None)
    namespace={
        "session":{"license_plan":plan,"license_key":"FAKE-PRO"},
        "request":SimpleNamespace(args={},headers={}),
        "jsonify":lambda x:x,
        "datetime":datetime,"timedelta":timedelta,"parse_day":date.fromisoformat,
        "TR_TZ":ZoneInfo("Europe/Istanbul"),
        "os":SimpleNamespace(environ={}),
        "BaseFeedUnavailable":Unavailable,
        "BaseSignalsFeed":BaseSource,
        "LegacySignalsFeed":LegacySource,
        "LEGACY_SOURCES":[("LEGACY_EARLY_MONEY_LOCK","early_money_lock_signals")],
        "_legacy_license_session_valid":lambda:True,
        "_validated_licenses":{"FAKE-PRO":{"plan":"pro"}},
        "app":SimpleNamespace(logger=SimpleNamespace(warning=lambda *x:None)),
    }
    if account:
        namespace["session"].update({"sb_access_token":"FAKE-ACCOUNT"})
        namespace["resolve_account_session"]=lambda: ({"email_confirmed":True},{"plan":plan})
        namespace["auth_helpers"]=SimpleNamespace(is_membership_active=lambda x:True)
    module=ast.fix_missing_locations(ast.Module(body=[node],type_ignores=[]))
    exec(compile(module,"app.py:base_signal_feed_api","exec"),namespace)
    return namespace["base_signal_feed_api"]()

def setup_function():
    BaseSource.fail=False
    BaseSource.calls=0
    LegacySource.fail=False
    LegacySource.calls=0


def test_only_new_base_signals_returned_even_when_legacy_source_would_fail():
    LegacySource.fail=True
    payload=route()
    assert payload["status"]=="ok"
    assert payload["items"]==[{"id":2,"kickoff_utc":"2026-10-20T10:00:00Z"}]
    assert payload["phase"]=="SIGNAL_MOTOR"
    assert payload["engines"]==["1X2_CONCENTRATION_V1"]
    assert LegacySource.calls==0 and BaseSource.calls==1


def test_base_failure_fails_closed_without_reading_legacy():
    BaseSource.fail=True
    payload,status=route()
    assert status==503 and payload["error"]=="SIGNAL_DATA_UNAVAILABLE"
    assert LegacySource.calls==0


def test_pro_gate_rejects_core_before_any_private_reads():
    payload,status=route(plan="core")
    assert status==403 and payload["error"]=="PRO_REQUIRED"
    assert BaseSource.calls==0 and LegacySource.calls==0


def test_account_pro_gate_serves_only_new_signals():
    payload=route(account=True)
    assert payload["phase"]=="SIGNAL_MOTOR"
    assert [x["id"] for x in payload["items"]]==[2]
    assert "legacy_audit" not in payload
    assert BaseSource.calls==1 and LegacySource.calls==0
