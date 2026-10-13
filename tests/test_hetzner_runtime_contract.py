from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SYSTEMD = ROOT / "deploy" / "systemd"
ENV_TEMPLATE = ROOT / "deploy" / "env.template"
UNIT_SYNC = ROOT / "deploy" / "sync_runtime_units.sh"
PREFLIGHT = ROOT / "deploy" / "hetzner_preflight.sh"
DEPLOY_WORKFLOW = ROOT / ".github" / "workflows" / "deploy.yml"
CONTRACT_WORKFLOW = ROOT / ".github" / "workflows" / "hetzner-runtime-contract-tests.yml"


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


def test_unit_sync_installs_all_runtime_units_without_restarting_or_stopping():
    text = UNIT_SYNC.read_text(encoding="utf-8")
    required = [
        "smartxflow-web.service",
        "smartxflow-scraper.service",
        "smartxflow-alarm.service",
        "smartxflow-sinyal.service",
        "smartxflow-live.service",
        "smartxflow-poly.service",
        "smartxflow-learning-archive-prematch.timer",
        "smartxflow-learning-archive-postmatch.timer",
    ]
    for unit in required:
        assert unit in text
    assert "systemctl daemon-reload" in text
    assert "systemctl enable" in text
    assert "systemctl restart" not in text
    assert "systemctl stop" not in text
    assert "systemctl disable" not in text
    assert "reset --hard" not in text


def test_preflight_is_read_only_and_checks_cutover_critical_contracts():
    text = PREFLIGHT.read_text(encoding="utf-8")
    required_checks = [
        "EXPECTED_SHA",
        "tracked worktree clean",
        "SUPABASE_SERVICE_ROLE_KEY",
        "LEARNING_ARCHIVE_ACCESS_SECRET",
        "SMARTXFLOW_LEARNING_API_BASE_URL",
        "prematch_authoritative_runtime.py",
        "SMARTXFLOW_FIXTURE_UID_AUTHORITATIVE_WRITE=true",
        "SMARTXFLOW_MODE=server",
        "DISABLE_SCRAPER=true",
        "127\\.0\\.0\\.1:8000",
        "HTTPS root reachable",
        "HETZNER_PREFLIGHT_OK",
    ]
    for token in required_checks:
        assert token in text

    forbidden = [
        "systemctl restart",
        "systemctl stop",
        "systemctl start",
        "systemctl enable",
        "systemctl disable",
        "systemctl daemon-reload",
        "git fetch",
        "git pull",
        "git merge",
        "git checkout",
        "git switch",
        "git reset",
        "git rebase",
        "git cherry-pick",
        "rm -rf",
        "truncate ",
        "DELETE FROM",
        "DROP TABLE",
    ]
    for token in forbidden:
        assert token not in text


def test_contract_ci_parses_both_operational_shell_scripts():
    text = CONTRACT_WORKFLOW.read_text(encoding="utf-8")
    assert "bash -n deploy/sync_runtime_units.sh" in text
    assert "bash -n deploy/hetzner_preflight.sh" in text
    assert "python -m pytest -q tests/test_hetzner_runtime_contract.py" in text


def test_deploy_syncs_canonical_units_and_verifies_runtime_entrypoints():
    text = DEPLOY_WORKFLOW.read_text(encoding="utf-8")
    assert "deploy/sync_runtime_units.sh" in text
    assert "systemctl restart smartxflow-web" in text
    assert "systemctl restart smartxflow-scraper" in text
    assert "systemctl restart smartxflow-alarm" in text
    assert "systemctl restart smartxflow-sinyal" in text
    assert "systemctl restart smartxflow-live" in text
    assert "systemctl restart smartxflow-poly" in text
    assert "prematch_authoritative_runtime.py" in text
    assert "SMARTXFLOW_MODE=server" in text
    assert "DISABLE_SCRAPER=true" in text
    assert "alarm_engine.py" in text
    assert "sinyal_engine_runtime.py" in text
    assert "live_scraper.py" in text
    assert "polymarket_scraper.py" in text
    assert "git merge --ff-only origin/main" in text
    assert "reset --hard" not in text
    assert "git rebase" not in text
    assert "git cherry-pick" not in text
