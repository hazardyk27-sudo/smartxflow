"""Production source master uses 180s only by explicit Hetzner service gate."""
import os
from pathlib import Path
import subprocess
import sys

ROOT=Path(__file__).resolve().parents[1]


def get_interval(value):
    env=os.environ.copy()
    env.pop("SMARTXFLOW_PREMATCH_INTERVAL_SECONDS",None)
    if value is not None:
        env["SMARTXFLOW_PREMATCH_INTERVAL_SECONDS"]=str(value)
    proc=subprocess.run(
        [sys.executable,"-c",
         "import scheduled_scraper_legacy as s;print('INTERVAL='+str(s.PREMATCH_INTERVAL_SECONDS))"],
        cwd=ROOT,env=env,stdout=subprocess.PIPE,stderr=subprocess.PIPE,
        text=True,timeout=15)
    assert proc.returncode==0, proc.stderr[:350]
    return int(proc.stdout.rsplit("INTERVAL=",1)[1].splitlines()[0])


def test_default_prematch_capture_stays_five_minutes_for_preview():
    assert get_interval(None)==300


def test_only_explicit_supported_three_minute_override_is_accepted():
    assert get_interval(180)==180
    for invalid in (30,40,60,120,240,299,"junk","-1",0):
        assert get_interval(invalid)==300


def test_single_provider_authoritative_production_master_enforces_180_seconds():
    service=(ROOT/"deploy/systemd/smartxflow-scraper.service").read_text()
    assert "Environment=SMARTXFLOW_PREMATCH_INTERVAL_SECONDS=180" in service
    assert "Environment=SMARTXFLOW_RUNTIME_ID=hetzner-prod" in service
    assert "ExecStart=/opt/smartxflow/venv/bin/python /opt/smartxflow/prematch_authoritative_runtime.py" in service
    assert "Environment=SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE=true" in service
    source=(ROOT/"scheduled_scraper_legacy.py").read_text()
    assert "PREMATCH_INTERVAL_SECONDS" in source
    assert "get_last_signal_time()" in source
    assert "PREMATCH_WATCHDOG_SECONDS" in source
