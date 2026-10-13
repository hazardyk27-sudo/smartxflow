from __future__ import annotations

from core import current_table_sync as sync


class Writer:
    def __init__(self):
        self._fixture_identity_authoritative_active = True
        self.last_write_errors = []
        self.calls = []

    def upsert_rows(self, table, rows, on_conflict="home,away,date"):
        self.calls.append((table, [dict(row) for row in rows], on_conflict))
        return True


def _row(home: str, fixture_uid: str):
    return {
        "league": "League",
        "home": home,
        "away": "Away",
        "date": "2026-10-13T18:00:00+00:00",
        "fixture_uid": fixture_uid,
        "odds1": "2.10",
    }


def test_authoritative_sync_homogenizes_bulk_object_keys_before_postgrest(monkeypatch):
    writer = Writer()
    rows = [
        _row("Home A", "11111111-1111-1111-1111-111111111111"),
        {
            **_row("Home B", "22222222-2222-2222-2222-222222222222"),
            "oddsx": "3.20",
        },
    ]

    monkeypatch.setattr(sync, "_flush_identity_shadow", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sync,
        "_attach_fixture_uid_dual_write",
        lambda *args, **kwargs: {
            "tagged_rows": 2,
            "unresolved_rows": 0,
            "identity_mismatch_rows": 0,
            "conflicting_existing_uid": 0,
            "error": None,
        },
    )
    monkeypatch.setattr(sync, "_read_current_index", lambda *args, **kwargs: {})
    monkeypatch.setattr(sync, "_delete_stale_ids", lambda *args, **kwargs: True)

    assert sync.sync_current_table(writer, "moneyway_1x2", rows) is True
    assert len(writer.calls) == 1

    sent_rows = writer.calls[0][1]
    assert set(sent_rows[0]) == set(sent_rows[1])
    assert sent_rows[0]["oddsx"] is None
    assert sent_rows[1]["oddsx"] == "3.20"

    # Original rows are normalized too because history reuses these objects.
    assert set(rows[0]) == set(rows[1])
    assert rows[0]["oddsx"] is None


def test_authoritative_sync_never_synthesizes_missing_fixture_uid(monkeypatch):
    writer = Writer()
    rows = [
        _row("Home A", "11111111-1111-1111-1111-111111111111"),
        {
            "league": "League",
            "home": "Home B",
            "away": "Away",
            "date": "2026-10-13T18:00:00+00:00",
            "odds1": "2.20",
        },
    ]

    monkeypatch.setattr(sync, "_flush_identity_shadow", lambda *args, **kwargs: None)
    monkeypatch.setattr(
        sync,
        "_attach_fixture_uid_dual_write",
        lambda *args, **kwargs: {
            "tagged_rows": 2,
            "unresolved_rows": 0,
            "identity_mismatch_rows": 0,
            "conflicting_existing_uid": 0,
            "error": None,
        },
    )

    assert sync.sync_current_table(writer, "moneyway_1x2", rows) is False
    assert writer.calls == []
    assert any("missing_uid=1" in error for error in writer.last_write_errors)
    assert "fixture_uid" not in rows[1]
