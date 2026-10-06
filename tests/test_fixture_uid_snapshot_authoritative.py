from core.fixture_uid_snapshot_authoritative import attach_provider_fixture_uids_to_snapshots


class FakeWriter:
    def _rest_url(self, table):
        return f"https://example.invalid/{table}"

    def _headers(self):
        return {"Authorization": "Bearer test"}


class FakeResponse:
    def __init__(self, rows, status_code=200):
        self._rows = rows
        self.status_code = status_code

    def json(self):
        return self._rows


def test_provider_snapshot_binding_tags_rows_and_removes_transient_event_id():
    snapshots = [
        {
            "match_id_hash": "legacy-same",
            "market": "1X2",
            "selection": "1",
            "_fixture_source_event_id": "1001",
        },
        {
            "match_id_hash": "legacy-same",
            "market": "1X2",
            "selection": "2",
            "_fixture_source_event_id": "1002",
        },
    ]

    def fake_get(*args, **kwargs):
        return FakeResponse(
            [
                {"source_event_id": "1001", "fixture_uid": "uid-a"},
                {"source_event_id": "1002", "fixture_uid": "uid-b"},
            ]
        )

    stats = attach_provider_fixture_uids_to_snapshots(
        FakeWriter(), snapshots, request_get=fake_get
    )

    assert stats["error"] is None
    assert stats["provider_events"] == 2
    assert stats["resolved_events"] == 2
    assert stats["tagged_rows"] == 2
    assert stats["unresolved_rows"] == 0
    assert snapshots[0]["fixture_uid"] == "uid-a"
    assert snapshots[1]["fixture_uid"] == "uid-b"
    assert "_fixture_source_event_id" not in snapshots[0]
    assert "_fixture_source_event_id" not in snapshots[1]


def test_provider_snapshot_binding_fails_closed_when_event_is_unresolved():
    snapshots = [
        {
            "match_id_hash": "legacy",
            "market": "BTTS",
            "selection": "Y",
            "_fixture_source_event_id": "9999",
        }
    ]

    def fake_get(*args, **kwargs):
        return FakeResponse([])

    stats = attach_provider_fixture_uids_to_snapshots(
        FakeWriter(), snapshots, request_get=fake_get
    )

    assert stats["error"] == "snapshot_provider_identity_unresolved"
    assert stats["tagged_rows"] == 0
    assert stats["unresolved_rows"] == 1
    assert "fixture_uid" not in snapshots[0]
    assert "_fixture_source_event_id" not in snapshots[0]


def test_provider_snapshot_binding_rejects_multiple_uids_for_same_event():
    snapshots = [
        {
            "match_id_hash": "legacy",
            "market": "OU25",
            "selection": "O",
            "_fixture_source_event_id": "2001",
        }
    ]

    def fake_get(*args, **kwargs):
        return FakeResponse(
            [
                {"source_event_id": "2001", "fixture_uid": "uid-a"},
                {"source_event_id": "2001", "fixture_uid": "uid-b"},
            ]
        )

    stats = attach_provider_fixture_uids_to_snapshots(
        FakeWriter(), snapshots, request_get=fake_get
    )

    assert stats["error"] == "snapshot_provider_event_maps_to_multiple_uids"
    assert stats["tagged_rows"] == 0
    assert stats["unresolved_rows"] == 1
    assert "_fixture_source_event_id" not in snapshots[0]
