from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"


def _read(name: str) -> str:
    return (SYSTEMD / name).read_text(encoding="utf-8")


def test_web_unit_is_ui_only_server_runtime():
    text = _read("smartxflow-web.service")
    assert "EnvironmentFile=/opt/smartxflow/.env" in text
    assert "Environment=SMARTXFLOW_MODE=server" in text
    assert "Environment=DISABLE_SCRAPER=true" in text
    assert "gunicorn app:app" in text
    assert "scheduled_scraper" not in text
    assert "live_scraper" not in text
    assert "alarm_engine.py" not in text


def test_prematch_unit_is_provider_authoritative():
    text = _read("smartxflow-scraper.service")
    assert "EnvironmentFile=/opt/smartxflow/.env" in text
    assert "Environment=SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE=true" in text
    assert "/opt/smartxflow/prematch_authoritative_runtime.py" in text
    assert "Restart=always" in text
    assert "replit_guarded_scraper" not in text


def test_worker_units_are_dedicated_and_restartable():
    expected = {
        "smartxflow-alarm.service": "/opt/smartxflow/alarm_engine.py",
        "smartxflow-live.service": "/opt/smartxflow/live_scraper.py",
        "smartxflow-poly.service": "/opt/smartxflow/polymarket_scraper.py",
    }
    for name, entrypoint in expected.items():
        text = _read(name)
        assert "EnvironmentFile=/opt/smartxflow/.env" in text
        assert entrypoint in text
        assert "Restart=always" in text
        assert "replit_guarded_scraper" not in text


def test_canonical_units_do_not_launch_replit_specific_entrypoints():
    for path in sorted(SYSTEMD.glob("smartxflow-*.service")):
        text = path.read_text(encoding="utf-8").lower()
        assert "scripts/replit_guarded_scraper.py" not in text
        assert "janeway.replit" not in text
