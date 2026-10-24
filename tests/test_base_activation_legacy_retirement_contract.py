"""Release regression: retired legacy signal unit may not block Base activation.

Both services require the *active* web/scraper/alarm stack while asserting
the retired legacy producer is disabled. No test mutates live host/DB state.
"""
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_independent_discovery_does_not_require_retired_signal_producer():
    flow = (ROOT / ".github/workflows/base-fixture-discovery-hetzner-enable.yml").read_text()
    assert "for unit in smartxflow-scraper smartxflow-alarm smartxflow-web; do" in flow
    assert "for unit in smartxflow-scraper smartxflow-alarm smartxflow-sinyal" not in flow
    assert "systemctl is-active smartxflow-sinyal.service || true" in flow
    assert "systemctl is-enabled smartxflow-sinyal.service || true" in flow
    assert "DISCOVERY_STOP: retired_legacy_signal_active" in flow
    assert "BASE_DISCOVERY_80H_OK" in flow


def test_base_autonomous_activation_requires_retired_unit_disabled():
    flow = (ROOT / ".github/workflows/base-autonomous-hetzner-enable.yml").read_text()
    assert "smartxflow-alarm smartxflow-sinyal" not in flow
    assert flow.count("systemctl is-active smartxflow-sinyal.service || true") >= 2
    assert flow.count("systemctl is-enabled smartxflow-sinyal.service || true") >= 2
    assert "smartxflow-base-guarded-recovery.service" in flow
    assert "BASE_GUARDED_RECOVERY" not in flow  # never bypass the supervisor's gates
    assert "AUTONOMOUS_BASE_24_7_OK" in flow
