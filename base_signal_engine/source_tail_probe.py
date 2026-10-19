"""Read-only, bounded source-tail integrity sampler for Hetzner preflight.

A sample can notice changes/deletions within *overlapping* newest-ID pages;
it CANNOT prove completeness of historical mutation capture or establish a
PostgreSQL commit watermark. Never treat it as a Phase 5A outbox replacement.
Only GET requests against public.moneyway_snapshots; saved state contains
ID/digests, never secrets, teams or source odds.
"""
from __future__ import annotations

import argparse
from datetime import datetime, timezone
from hashlib import sha256
import json
import os
from pathlib import Path
import sys
import tempfile
from typing import Any

from .reader import SupabaseMoneywayReader, _parse_time

FIELDS=("id","fixture_uid","match_id_hash","market","selection",
        "scraped_at_utc","odds","volume","share")
_VERSION=1


def sample_tail(reader: Any, *, limit: int=250) -> dict:
    if type(limit) is not int or not 1<=limit<=500:
        raise ValueError("unsafe source-tail sample bound")
    rows=reader._get("moneyway_snapshots",[
        ("select",",".join(FIELDS)),("order","id.desc"),("limit",str(limit))])
    if not rows or len(rows)>limit:
        raise ValueError("missing or oversized source-tail evidence")
    hashes={}
    last=None
    uid_null=0
    for row in rows:
        try:
            ident=int(row["id"])
            if type(row["id"]) not in (int,str) or ident<=0 or (
                    last is not None and ident>=last):
                raise ValueError("invalid tail ID order")
            if row["fixture_uid"] is None:
                uid_null+=1
            _parse_time(row["scraped_at_utc"])
            blob={field:row[field] for field in FIELDS if field!="id"}
            digest=sha256(json.dumps(blob,sort_keys=True,separators=(",",":"),
                                     ensure_ascii=True,default=str).encode()).hexdigest()
        except (KeyError,TypeError,ValueError) as exc:
            raise ValueError("invalid source-tail evidence") from exc
        hashes[str(ident)]=digest
        last=ident
    return {"version":_VERSION,"head_id":max(map(int,hashes)),
            "floor_id":min(map(int,hashes)),"rows":len(hashes),
            "null_uid_rows":uid_null,"digests":hashes}


def compare_tail(previous: dict | None, current: dict) -> dict:
    if not isinstance(current,dict) or current.get("version")!=_VERSION:
        raise ValueError("unrecognized source-tail version")
    new_ids=set(current["digests"])
    if previous is None:
        return {"status":"BASELINE_ONLY","overlap":0,"changed":0,
                "potential_missing":0,"head_advanced":False,
                "source_mutation_capture_verified":False}
    if (not isinstance(previous,dict) or previous.get("version")!=_VERSION
            or not isinstance(previous.get("digests"),dict)):
        raise ValueError("invalid previous tail sample")
    old_ids=set(previous["digests"])
    overlap=old_ids & new_ids
    changes=sum(previous["digests"][i]!=current["digests"][i] for i in overlap)
    floor=int(current["floor_id"])
    potential_missing=sum(int(i)>=floor for i in old_ids-new_ids)
    head_advanced=current["head_id"]>previous["head_id"]
    status=("MUTATION_SUSPECTED" if changes or potential_missing else
            "NO_OVERLAP_UNVERIFIED" if not overlap else
            "OVERLAP_SAMPLED")
    return {"status":status,"overlap":len(overlap),"changed":changes,
            "potential_missing":potential_missing,
            "head_advanced":head_advanced,
            "source_mutation_capture_verified":False}


def _load(path: Path) -> dict | None:
    if not path.exists():
        return None
    raw=path.read_bytes()
    if not raw or len(raw)>80000:
        raise ValueError("untrusted source-tail state size")
    obj=json.loads(raw)
    if not isinstance(obj,dict) or obj.get("version")!=_VERSION:
        raise ValueError("invalid local tail-state version")
    if (type(obj.get("rows")) is not int or not 1<=obj["rows"]<=500
            or not isinstance(obj.get("digests"),dict)
            or len(obj["digests"])!=obj["rows"]):
        raise ValueError("invalid local tail state")
    for k,v in obj["digests"].items():
        if (not k.isdigit() or int(k)<=0 or not isinstance(v,str)
                or len(v)!=64 or any(c not in "0123456789abcdef" for c in v)):
            raise ValueError("invalid source-tail digest")
    return obj


def _save(path: Path, state: dict) -> None:
    if not path.parent.is_dir():
        raise ValueError("state directory must exist and be access controlled")
    # Writes local-only, in the caller-supplied restricted evidence directory.
    raw=json.dumps(state,sort_keys=True,separators=(",",":")).encode()
    fd,name=tempfile.mkstemp(prefix=".source-tail-",dir=str(path.parent))
    try:
        os.fchmod(fd,0o600)
        with os.fdopen(fd,"wb") as stream:
            stream.write(raw)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(name,path)
    finally:
        if os.path.exists(name):
            os.unlink(name)


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="read-only sampled source integrity")
    parser.add_argument("--state",required=True,help="local restricted digest-only file")
    parser.add_argument("--limit",type=int,default=250)
    args=parser.parse_args(argv)
    if os.environ.get("SXF_BASE_SOURCE_TAIL_PROBE_APPROVED")!="yes":
        parser.error("one-shot opt-in required")
    try:
        state_path=Path(args.state)
        prior=_load(state_path)
        reader=SupabaseMoneywayReader(
            os.environ.get("SUPABASE_URL",""),
            os.environ.get("SUPABASE_SERVICE_ROLE_KEY",""),
            page_size=500,max_pages_per_window=1,request_timeout_seconds=15)
        current=sample_tail(reader,limit=args.limit)
        comparison=compare_tail(prior,current)
        _save(state_path,current)
        print(json.dumps({"mode":"READ_ONLY_SAMPLED_SOURCE_TAIL",
                          "head_id":current["head_id"],
                          "tail_rows":current["rows"],
                          "null_uid_rows":current["null_uid_rows"],
                          **comparison,"release_gate":"BLOCKED_NO_COMPLETE_CHANGE_CAPTURE",
                          "db_writes_performed":False},sort_keys=True))
        return 0
    except Exception as exc:
        print(json.dumps({"mode":"READ_ONLY_SAMPLED_SOURCE_TAIL",
                          "status":"FAILED",
                          "error_type":type(exc).__name__,
                          "source_mutation_capture_verified":False}),
              file=sys.stderr)
        return 2


if __name__=="__main__":
    sys.exit(main())
