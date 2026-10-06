from pathlib import Path


SCRIPT = Path("scripts/run_fixture_uid_authoritative_activation_probe.py")


def test_activation_probe_is_guarded_and_fixture_identity_only():
    text = SCRIPT.read_text()
    assert "SMARTXFLOW_FIXTURE_UID_ACTIVATION_PROBE" in text
    assert "=APPLY required" in text
    assert "plan_provider_first_fixture_rows" in text
    assert "write_provider_authoritative_fixture_batch" in text
    assert '"fixture_source_ids"' in text
    assert '"fixtures"' in text

    forbidden_write_surfaces = (
        "append_history(",
        "insert_snapshots(",
        "sync_current_table(",
        "moneyway_1x2_history",
        "dropping_1x2_history",
        "moneyway_snapshots",
        "sinyal",
        "alarm",
        "learning_archive",
    )
    for token in forbidden_write_surfaces:
        assert token not in text


def test_activation_probe_preflights_before_authoritative_write():
    text = SCRIPT.read_text()
    preflight_call = text.index("_preflight(writer, matches)")
    write_call = text.index("stats = write_provider_authoritative_fixture_batch(writer, matches)")
    assert preflight_call < write_call


def test_activation_probe_postflights_live_provider_ids():
    text = SCRIPT.read_text()
    assert "_postflight_live_events(writer, matches)" in text
    assert "unresolved_live_events" in text
    assert "AUTHORITATIVE_ACTIVATION_RESULT=PASS" in text
