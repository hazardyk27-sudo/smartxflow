from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_first_page_rpc_is_bounded_and_not_security_definer():
    sql = (ROOT / "migrations" / "2026_10_09_app_first_page_fast_path.sql").read_text()
    assert "sxf_matches_first_page_v1" in sql
    assert "greatest(1, least(coalesce(p_limit, 20), 100))" in sql
    assert "sxf_parse_volume_v1(t.volume) desc nulls last" in sql
    assert "security invoker" in sql.lower()
    assert "security definer" not in sql.lower()
    for market in (
        "moneyway_1x2", "moneyway_ou25", "moneyway_btts",
        "dropping_1x2", "dropping_ou25", "dropping_btts",
    ):
        assert market in sql


def test_first_page_rpc_date_regex_accepts_iso_kickoffs():
    sql = (
        ROOT
        / "migrations"
        / "2026_10_09_app_first_page_fast_path_date_regex_fix.sql"
    ).read_text()
    assert "^[0-9]{4}-[0-9]{2}-[0-9]{2}T" in sql
    assert "sxf_matches_first_page_v1" in sql
    assert "security invoker" in sql.lower()
    assert "security definer" not in sql.lower()


def test_app_first_paint_uses_bounded_endpoint_before_bulk_hydration():
    src = (ROOT / "static" / "js" / "app.js.src").read_text()
    assert "date_filter=today_future&limit=20&offset=0" in src
    first_page = src.index("date_filter=today_future&limit=20&offset=0")
    bulk = src.index("date_filter=today_future&bulk=1", first_page)
    render = src.index("renderMatches(filteredMatches);", first_page)
    assert first_page < render < bulk
    assert "scheduleBackgroundMatchHydration" in src


def test_route_sends_today_future_to_uid_safe_paginated_reader():
    app = (ROOT / "app.py").read_text()
    assert "if date_filter in (None, 'today_future'):" in app
    assert "today_only=(date_filter == 'today_future')" in app
    assert "if result.get('first_page_fast')" in app
