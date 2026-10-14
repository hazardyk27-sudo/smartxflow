from pathlib import Path

import poly_runtime


ROOT = Path(__file__).resolve().parents[1]


def test_registry_dedupe_prefers_verified_for_same_normalized_key():
    rows = [
        {
            "identity_type": "event",
            "identity_id": 123,
            "classification": poly_runtime._client.FOOTBALL_CLASS_UNCERTAIN,
            "event_id": "evt-123",
            "source": "first",
            "evidence": {"a": 1},
        },
        {
            "identity_type": "event",
            "identity_id": "123",
            "classification": poly_runtime._client.FOOTBALL_CLASS_NON_FOOTBALL,
            "source": "second",
        },
        {
            "identity_type": "event",
            "identity_id": "123",
            "classification": poly_runtime._client.FOOTBALL_CLASS_VERIFIED,
            "source": "third",
        },
    ]

    deduped = poly_runtime.dedupe_sport_registry_records(rows)

    assert len(deduped) == 1
    assert deduped[0]["classification"] == poly_runtime._client.FOOTBALL_CLASS_VERIFIED
    assert deduped[0]["source"] == "third"
    assert deduped[0]["event_id"] == "evt-123"
    assert deduped[0]["evidence"] == {"a": 1}


def test_registry_dedupe_non_football_beats_uncertain_and_keeps_order():
    rows = [
        {
            "identity_type": "condition",
            "identity_id": "a",
            "classification": poly_runtime._client.FOOTBALL_CLASS_UNCERTAIN,
        },
        {
            "identity_type": "condition",
            "identity_id": "b",
            "classification": poly_runtime._client.FOOTBALL_CLASS_VERIFIED,
        },
        {
            "identity_type": "condition",
            "identity_id": "a",
            "classification": poly_runtime._client.FOOTBALL_CLASS_NON_FOOTBALL,
        },
    ]

    deduped = poly_runtime.dedupe_sport_registry_records(rows)

    assert [row["identity_id"] for row in deduped] == ["a", "b"]
    assert deduped[0]["classification"] == poly_runtime._client.FOOTBALL_CLASS_NON_FOOTBALL


def test_install_guard_dedupes_before_calling_canonical_persistence(monkeypatch):
    captured = []

    def sink(records):
        captured.append(records)

    monkeypatch.setattr(poly_runtime._client, "_persist_sport_registry_records", sink)
    poly_runtime.install_registry_dedupe_guard()
    wrapped = poly_runtime._client._persist_sport_registry_records

    wrapped([
        {
            "identity_type": "event",
            "identity_id": "same",
            "classification": poly_runtime._client.FOOTBALL_CLASS_UNCERTAIN,
        },
        {
            "identity_type": "event",
            "identity_id": "same",
            "classification": poly_runtime._client.FOOTBALL_CLASS_VERIFIED,
        },
    ])

    assert len(captured) == 1
    assert len(captured[0]) == 1
    assert captured[0][0]["classification"] == poly_runtime._client.FOOTBALL_CLASS_VERIFIED

    # Installing twice must not create wrapper recursion.
    poly_runtime.install_registry_dedupe_guard()
    assert poly_runtime._client._persist_sport_registry_records is wrapped


def test_hetzner_poly_unit_runs_guard_before_canonical_scraper():
    text = (ROOT / "deploy" / "systemd" / "smartxflow-poly.service").read_text(
        encoding="utf-8"
    )
    assert "/opt/smartxflow/poly_runtime.py" in text
    assert "/opt/smartxflow/polymarket_scraper.py" in text
    assert text.index("poly_runtime.py") < text.index("polymarket_scraper.py")
