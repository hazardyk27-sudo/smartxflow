import json

from scripts.remap_duplicate_fixture_references import (
    plan_snapshot_collision,
    plan_volumeshock_collision,
)


def test_snapshot_collision_dedupes_identical_overlap_and_remaps_rest():
    stale = [
        {
            "id": 1,
            "match_id_hash": "aaaaaaaaaaaa",
            "scraped_at_utc": "2026-10-04T10:00:00+00:00",
            "market": "1X2",
            "selection": "1",
            "odds": 2.1,
            "volume": 100,
            "share": 40,
        },
        {
            "id": 2,
            "match_id_hash": "aaaaaaaaaaaa",
            "scraped_at_utc": "2026-10-04T10:05:00+00:00",
            "market": "1X2",
            "selection": "1",
            "odds": 2.0,
            "volume": 120,
            "share": 42,
        },
    ]
    canonical = [
        {
            "id": 9,
            "match_id_hash": "bbbbbbbbbbbb",
            "scraped_at_utc": "2026-10-04T10:00:00+00:00",
            "market": "1X2",
            "selection": "1",
            "odds": 2.1,
            "volume": 100,
            "share": 40,
        }
    ]

    operation, errors = plan_snapshot_collision(
        "aaaaaaaaaaaa", "bbbbbbbbbbbb", stale, canonical
    )

    assert errors == []
    assert operation is not None
    assert operation["duplicate_stale_ids"] == [1]
    assert operation["remap_count"] == 1


def test_snapshot_collision_blocks_nonidentical_overlap():
    stale = [
        {
            "id": 1,
            "scraped_at_utc": "2026-10-04T10:00:00+00:00",
            "market": "1X2",
            "selection": "1",
            "odds": 2.1,
            "volume": 100,
            "share": 40,
        }
    ]
    canonical = [
        {
            "id": 9,
            "scraped_at_utc": "2026-10-04T10:00:00+00:00",
            "market": "1X2",
            "selection": "1",
            "odds": 2.2,
            "volume": 100,
            "share": 40,
        }
    ]

    operation, errors = plan_snapshot_collision(
        "aaaaaaaaaaaa", "bbbbbbbbbbbb", stale, canonical
    )

    assert operation is None
    assert len(errors) == 1
    assert "moneyway_nonidentical_overlap" in errors[0]


def test_volumeshock_collision_keeps_latest_state_and_preserves_history():
    stale = [
        {
            "id": 1,
            "market": "1X2",
            "selection": "1",
            "trigger_at": "2026-10-04T10:10:00+00:00",
            "incoming_money": 900,
            "avg_previous": 100,
            "volume_shock_value": 9.0,
            "alarm_history": json.dumps([
                {
                    "incoming_money": 500,
                    "trigger_at": "2026-10-04T09:50:00+00:00",
                    "volume_shock_value": 5.0,
                }
            ]),
        }
    ]
    canonical = [
        {
            "id": 2,
            "market": "1X2",
            "selection": "1",
            "trigger_at": "2026-10-04T10:00:00+00:00",
            "incoming_money": 700,
            "avg_previous": 100,
            "volume_shock_value": 7.0,
            "alarm_history": [],
        }
    ]

    operation, errors = plan_volumeshock_collision(
        "aaaaaaaaaaaa", "bbbbbbbbbbbb", stale, canonical
    )

    assert errors == []
    assert operation is not None
    assert operation["canonical_id"] == 2
    assert operation["stale_id"] == 1
    assert operation["merged_payload"]["trigger_at"] == "2026-10-04T10:10:00+00:00"
    assert operation["merged_payload"]["incoming_money"] == 900
    history = operation["merged_payload"]["alarm_history"]
    assert len(history) == 2
    assert history[-1]["trigger_at"] == "2026-10-04T10:00:00+00:00"


def test_volumeshock_collision_blocks_key_mismatch():
    stale = [{
        "id": 1,
        "market": "1X2",
        "selection": "1",
        "trigger_at": "2026-10-04T10:10:00+00:00",
    }]
    canonical = [{
        "id": 2,
        "market": "1X2",
        "selection": "2",
        "trigger_at": "2026-10-04T10:00:00+00:00",
    }]

    operation, errors = plan_volumeshock_collision(
        "aaaaaaaaaaaa", "bbbbbbbbbbbb", stale, canonical
    )

    assert operation is None
    assert len(errors) == 1
    assert "volumeshock_key_mismatch" in errors[0]
