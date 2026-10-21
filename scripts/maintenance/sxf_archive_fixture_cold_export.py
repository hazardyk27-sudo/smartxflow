#!/usr/bin/env python3
"""Resumable, checksummed, fixture-only Supabase Storage export (NOT full backup).

DEFAULT: read-only source and local manifest report, NO Storage writes.
--apply requires a separately authorized explicit environment value.

Dataset scope is ONLY research_archive.fixtures. Other history/raw markets,
cross-project backup, restore testing and deletion approval remain UNVERIFIED.
All source rows are read in one read-only PostgreSQL snapshot, sorted by an
immutable primary key; the exporter NEVER uses OFFSET or ctid pagination.
"""
from __future__ import annotations

import argparse
from datetime import datetime
import gzip
import hashlib
import io
import json
import os
import subprocess
import sys
from urllib.parse import quote, urlparse
from zoneinfo import ZoneInfo

import requests

BUCKET = "sxf-research-archive"
FIXTURE_ROOT = "fixtures-only/v1"
MAX_ROWS = 10000
PART_ROWS = 500
AUTH_ENV = "SMARTXFLOW_FIXTURE_COLD_EXPORT_APPROVED"
AUTH_VALUE = "approved-fixtures-only-storage-backup-not-retention"
QUERY = """BEGIN TRANSACTION ISOLATION LEVEL REPEATABLE READ READ ONLY;
SET LOCAL statement_timeout='15s';
SET LOCAL lock_timeout='1s';
SELECT row_to_json(a)::text
FROM research_archive.fixtures a
ORDER BY a.source_internal_id;
COMMIT;"""


def sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def canonical(row: dict) -> bytes:
    return (json.dumps(row,sort_keys=True,ensure_ascii=False,separators=(",",":"))+"\n").encode("utf-8")


def read_fixtures(run=subprocess.run) -> list[dict]:
    proc=run(["psql","-X","-q","-t","-A","-v","ON_ERROR_STOP=1"],
             input=QUERY,check=True,timeout=30,capture_output=True,text=True)
    out=[]
    previous=-1
    istanbul=ZoneInfo("Europe/Istanbul")
    for line in proc.stdout.splitlines():
        if not line.strip():
            continue
        obj=json.loads(line)
        if not isinstance(obj,dict):
            raise ValueError("Invalid fixture row data")
        identifier=obj.get("source_internal_id")
        uid=obj.get("fixture_uid")
        kickoff=obj.get("kickoff_utc")
        if (not isinstance(identifier,int) or identifier<=previous
            or not isinstance(uid,str) or not uid.strip()
            or not isinstance(kickoff,str)):
            raise ValueError("Source fixture physical identity or sort order invalid")
        parsed=datetime.fromisoformat(kickoff.replace("Z","+00:00"))
        if parsed.tzinfo is None:
            raise ValueError("Timezone-naive fixture kickoff rejected")
        if obj.get("local_date")!=parsed.astimezone(istanbul).date().isoformat():
            raise ValueError("Archive fixture local kickoff day inconsistent")
        previous=identifier
        out.append(obj)
        if len(out)>MAX_ROWS:
            raise ValueError("Fixture dataset exceeds canary exporter row limit")
    if not out:
        raise ValueError("Empty archive fixture dataset cannot be finalized")
    return out


def gzip_deterministic(payload: bytes) -> bytes:
    target=io.BytesIO()
    with gzip.GzipFile(fileobj=target,mode="wb",filename="",mtime=0,compresslevel=6) as gz:
        gz.write(payload)
    return target.getvalue()


def build_package(rows: list[dict]) -> tuple[dict,dict[str,bytes]]:
    if not rows or len(rows)>MAX_ROWS:
        raise ValueError("Unsupported fixture snapshot size")
    payload=b"".join(canonical(x) for x in rows)
    snapshot_sha=sha(payload)
    prefix=f"{FIXTURE_ROOT}/{snapshot_sha}"
    parts=[]
    objects={}
    for i in range(0,len(rows),PART_ROWS):
        data=b"".join(canonical(x) for x in rows[i:i+PART_ROWS])
        zipped=gzip_deterministic(data)
        name=f"{prefix}/part-{i//PART_ROWS:05d}.ndjson.gz"
        objects[name]=zipped
        parts.append({"path":name,"rows":len(rows[i:i+PART_ROWS]),
                      "sha256":sha(zipped),"size_bytes":len(zipped)})
    manifest={
        "format":"SXF_RESEARCH_ARCHIVE_FIXTURES_ONLY_V1",
        "physical_identity":"fixture_uid",
        "source_order":"source_internal_id ASC",
        "source_table":"research_archive.fixtures",
        "rows":len(rows),
        "first_source_id":rows[0]["source_internal_id"],
        "last_source_id":rows[-1]["source_internal_id"],
        "source_ndjson_sha256":snapshot_sha,
        "compression":"gzip",
        "parts":parts,
        "full_raw_history_parity_verified":False,
        "independent_offsite_backup_verified":False,
        "restored_from_cold_backup_verified":False,
        "retention_cleanup_allowed":False,
    }
    manifest_path=f"{prefix}/manifest.json"
    objects[manifest_path]=(json.dumps(manifest,sort_keys=True,separators=(",",":"))+"\n").encode("utf-8")
    return manifest,objects


def bucket_object_url(api_url: str, path: str) -> str:
    parsed=urlparse(api_url.strip())
    if parsed.scheme!="https" or not parsed.hostname or not parsed.hostname.endswith(".supabase.co"):
        raise ValueError("Require an official HTTPS Supabase project URL")
    return api_url.rstrip()+"/storage/v1/object/"+quote(BUCKET+"/"+path,safe="/")


def verify_object(session, url: str,headers:dict, content:bytes) -> bool:
    response=session.get(url,headers=headers,timeout=20)
    if response.status_code==404:
        return False
    if response.status_code!=200:
        raise RuntimeError("Storage object verification failed")
    if sha(response.content)!=sha(content):
        raise RuntimeError("Storage object content checksum conflict")
    return True


def upload_verified(session, url:str, headers:dict,content:bytes, mime:str) -> str:
    if verify_object(session,url,headers,content):
        return "already_verified"
    uploaded=session.post(url,headers={**headers,"Content-Type":mime,"x-upsert":"false"},data=content,timeout=30)
    if uploaded.status_code not in (200,201,409):
        raise RuntimeError("Storage immutable upload failed")
    if not verify_object(session,url,headers,content):
        raise RuntimeError("Storage read-after-write verification failed")
    return "uploaded_and_verified" if uploaded.status_code!=409 else "conflict_verified"


def send_package(api_url: str, token: str, objects:dict[str,bytes],session=requests) -> dict:
    if not token:
        raise PermissionError("Server-only Supabase service role key required")
    headers={"apikey":token,"Authorization":f"Bearer {token}"}
    paths=[x for x in objects if x.endswith(".ndjson.gz")]
    manifests=[x for x in objects if x.endswith("/manifest.json")]
    if len(manifests)!=1:
        raise ValueError("Exactly one final fixture manifest required")
    uploaded=0
    reused=0
    for p in sorted(paths)+manifests: # final manifest is LAST
        status=upload_verified(session,bucket_object_url(api_url,p),headers,
                               objects[p],"application/gzip" if p.endswith(".gz") else "application/json")
        if status=="already_verified":
            reused+=1
        else:
            uploaded+=1
    return {"uploaded_files":uploaded,"already_verified_files":reused,
            "manifest_path":manifests[0],"retention_cleanup_allowed":False}


def main(argv:list[str]|None=None)->int:
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--apply",action="store_true")
    args=parser.parse_args(argv)
    try:
        if args.apply and os.environ.get(AUTH_ENV)!=AUTH_VALUE:
            raise PermissionError("Cold fixture export requires separate explicit approval")
        rows=read_fixtures()
        manifest,objects=build_package(rows)
        result={
            "mode":"FIXTURES_ONLY_STORAGE_WRITE" if args.apply else "READ_ONLY_PLAN",
            "source_rows":manifest["rows"],"parts":len(manifest["parts"]),
            "snapshot_sha256":manifest["source_ndjson_sha256"],
            "backup_restored":False,"independent_backup":False,
            "retention_cleanup_allowed":False,
        }
        if args.apply:
            result["storage"]=send_package(os.environ.get("SUPABASE_URL",""),
                                           os.environ.get("SUPABASE_SERVICE_ROLE_KEY",""),objects)
        print(json.dumps(result,sort_keys=True))
        return 0
    except (subprocess.SubprocessError,OSError,ValueError,TypeError,KeyError,RuntimeError,PermissionError) as exc:
        # Never log the service key, raw fixtures, request body or stderr.
        print(json.dumps({"status":"BLOCKED","error_type":type(exc).__name__}),file=sys.stderr)
        return 3


if __name__=="__main__":
    sys.exit(main())
