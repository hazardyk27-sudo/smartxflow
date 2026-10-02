from analysis_v2.live_preview import _current_cycle_rows, compute_live_cards


def test_current_cycle_keeps_latest_exact_selection():
    rows = [
        {"match_id_hash":"a","market":"1X2","selection":"1","scraped_at_utc":"2026-10-03T10:00:00Z","volume":10},
        {"match_id_hash":"a","market":"1X2","selection":"1","scraped_at_utc":"2026-10-03T11:00:00Z","volume":20},
        {"match_id_hash":"a","market":"1X2","selection":"2","scraped_at_utc":"2026-10-03T10:00:00Z","volume":15},
    ]
    current = _current_cycle_rows(rows)
    one = [r for r in current if r["selection"] == "1"][0]
    assert one["volume"] == 20
    assert len(current) == 2


def test_live_preview_contract_is_read_only_when_no_cards():
    class EmptyClient:
        def fetch_match_rows(self, **kwargs):
            return []

    result = compute_live_cards(
        snapshot_client=EmptyClient(),
        fixtures={},
        recent_snapshot_rows=[],
        as_of="2026-10-03T12:00:00Z",
    )
    assert result["available"] is True
    assert result["mode"] == "live_preview"
    assert result["read_only"] is True
    assert result["history_available"] is False
    assert result["settlement_available"] is False
    assert result["signals"] == []
