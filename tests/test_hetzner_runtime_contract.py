from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"
ENV_TEMPLATE = ROOT / "deploy" / "env.template"


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


def test_hetzner_env_template_contains_required_production_contract():
    text = ENV_TEMPLATE.read_text(encoding="utf-8")
    assert "SUPABASE_SERVICE_ROLE_KEY=YOUR_SERVICE_ROLE_KEY_HERE" in text
    assert "SMARTXFLOW_MODE=server" in text
    assert "LEARNING_ARCHIVE_ACCESS_SECRET=" in text
    assert "SMARTXFLOW_LEARNING_API_BASE_URL=https://smartxflow.com" in text
    assert "Betwach_api_key=YOUR_BETWATCH_API_TOKEN" in text
    assert "SMARTXFLOW_PRODUCTION=1" in text


def test_env_template_keeps_identity_cutover_fail_safe_by_default():
    text = ENV_TEMPLATE.read_text(encoding="utf-8")
    # A fresh server template must not silently enable the authoritative writer
    # before its DB migration/postflight is explicitly verified.
    assert "SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE=false" in text
