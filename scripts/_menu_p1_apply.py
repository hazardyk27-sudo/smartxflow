from __future__ import annotations

from pathlib import Path

from rjsmin import jsmin

ROOT = Path(__file__).resolve().parents[1]


def replace_once(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count != 1:
        raise RuntimeError(f"{label}: expected exactly one match, found {count}")
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def replace_all_required(path: Path, old: str, new: str, label: str) -> None:
    text = path.read_text(encoding="utf-8")
    count = text.count(old)
    if count < 1:
        raise RuntimeError(f"{label}: expected at least one match")
    path.write_text(text.replace(old, new), encoding="utf-8")


def patch_fixture_reader() -> None:
    path = ROOT / "services" / "fixture_uid_reader_patch.py"
    text = path.read_text(encoding="utf-8")
    if "_FIRST_PAGE_RPC = \"sxf_matches_first_page_v1\"" in text:
        return

    text = text.replace(
        "from __future__ import annotations\n\nfrom collections import defaultdict",
        "from __future__ import annotations\n\nimport json\nfrom collections import defaultdict",
        1,
    )
    text = text.replace(
        "from typing import Any, Dict, Iterable, List, Mapping, Optional",
        "from typing import Any, Dict, Iterable, List, Mapping, Optional, Tuple",
        1,
    )
    text = text.replace(
        "_MAX_FIXTURES = 10000\n",
        "_MAX_FIXTURES = 10000\n_FIRST_PAGE_RPC = \"sxf_matches_first_page_v1\"\n_MAX_FIRST_PAGE = 100\n",
        1,
    )

    marker = "\ndef get_matches_paginated_uid_safe(\n"
    helper = r'''

def _fetch_first_page_rows(
    client: Any,
    market: str,
    limit: int,
    date_gte: str,
) -> Optional[Tuple[List[Dict[str, Any]], int]]:
    """Fetch only the globally highest-volume first page from the current table.

    The RPC performs numeric volume ordering inside Postgres and returns at most
    ``limit`` current-table rows plus the filtered total count.  No fixture table
    scan and no full market payload crosses the network on this path.
    """
    if not getattr(client, "is_available", False):
        return None

    safe_limit = max(1, min(int(limit or 20), _MAX_FIRST_PAGE))
    url = client._rest_url(f"rpc/{_FIRST_PAGE_RPC}")
    body = {
        "p_market": market,
        "p_limit": safe_limit,
        "p_date_gte": f"{date_gte}T00:00:00+00:00" if date_gte else None,
    }
    try:
        response = client._get_http_client().post(
            url,
            headers=client._headers(),
            json=body,
            timeout=10,
        )
        if response.status_code != 200:
            print(f"[FixtureUIDReader] first-page RPC unavailable: {response.status_code}")
            return None
        payload = response.json()
        if not isinstance(payload, list):
            return None

        rows: List[Dict[str, Any]] = []
        total = 0
        for item in payload:
            if not isinstance(item, dict):
                continue
            row = item.get("row_data")
            if isinstance(row, str):
                try:
                    row = json.loads(row)
                except Exception:
                    row = None
            if isinstance(row, dict):
                rows.append(row)
            try:
                total = max(total, int(item.get("total_count") or 0))
            except (TypeError, ValueError):
                pass
        if rows and total <= 0:
            total = len(rows)
        return rows, total
    except Exception as exc:
        print(f"[FixtureUIDReader] first-page RPC failed: {exc}")
        return None


def _current_row_to_match(client: Any, row: Mapping[str, Any], market: str, tr_tz: Any) -> Dict[str, Any]:
    kickoff_utc = row.get("date", "")
    date_display = kickoff_utc
    if kickoff_utc:
        try:
            kickoff_dt = (
                datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00"))
                if isinstance(kickoff_utc, str)
                else kickoff_utc
            )
            date_display = kickoff_dt.astimezone(tr_tz).strftime("%d.%b %H:%M")
        except Exception:
            pass

    try:
        latest = client._normalize_history_row(dict(row), market)
    except Exception:
        latest = client._get_empty_odds(market)

    match: Dict[str, Any] = {
        "fixture_uid": row.get("fixture_uid"),
        "home_team": row.get("home", ""),
        "away_team": row.get("away", ""),
        "league": row.get("league", ""),
        "date": date_display,
        "kickoff_utc": kickoff_utc,
        "latest": latest,
    }
    match_hash = str(row.get("match_id_hash") or "").strip()
    if match_hash:
        match["match_id_hash"] = match_hash
    return match
'''
    if marker not in text:
        raise RuntimeError("fixture reader insertion marker missing")
    text = text.replace(marker, helper + marker, 1)

    old = '''        date_gte = (
            (today_date - timedelta(days=1)).strftime("%Y-%m-%d")
            if today_only
            else seven_days_ago
        )

        fixtures = _fetch_fixture_rows(client, date_gte=date_gte)
'''
    new = '''        date_gte = (
            (today_date - timedelta(days=1)).strftime("%Y-%m-%d")
            if today_only
            else seven_days_ago
        )

        # Critical first paint: use the current-table RPC so a 20-row screen never
        # waits for the full fixture/current-market snapshot to cross the network.
        # Offset pages remain on the legacy path until Menu Part 2 introduces real
        # UID-safe pagination for background hydration.
        if offset == 0 and 0 < limit <= _MAX_FIRST_PAGE:
            first_page = _fetch_first_page_rows(client, market, limit, date_gte)
            if first_page is not None:
                current_rows, total = first_page
                matches = [
                    _current_row_to_match(client, row, market, tr_tz)
                    for row in current_rows
                ]
                return {
                    "matches": matches,
                    "total": total,
                    "has_more": total > len(matches),
                    "first_page_fast": True,
                }

        fixtures = _fetch_fixture_rows(client, date_gte=date_gte)
'''
    if text.count(old) != 1:
        raise RuntimeError(f"fixture fast-path marker count={text.count(old)}")
    text = text.replace(old, new, 1)
    path.write_text(text, encoding="utf-8")


def patch_app_py() -> None:
    path = ROOT / "app.py"
    old = '''    # PAGINATED MODE (legacy): Use for non-bulk requests
    # Use new paginated function for ALL/no date_filter (most common case)
    if date_filter is None:
        result = db.get_matches_paginated(market, limit=limit, offset=offset)
'''
    new = '''    # FIRST-PAGE/PAGINATED MODE: the default app view must never wait for
    # bulk hydration before it can paint its first rows. today_future stays
    # UID-safe through the active reader patch and returns the true volume top-N.
    if date_filter in (None, 'today_future'):
        result = db.get_matches_paginated(
            market,
            limit=limit,
            offset=offset,
            today_only=(date_filter == 'today_future'),
        )
'''
    replace_once(path, old, new, "app paginated today_future route")

    old_scores = '''        ft_scores = _get_finished_scores_map()
        _enrich_ft_scores_with_match_hashes(ft_scores, enriched)
        resp_data = {
'''
    new_scores = '''        # A cold finished-score lookup must not re-block the fast first paint.
        # Reuse it when already warm; the background bulk hydration carries the
        # full score payload shortly afterwards.
        if result.get('first_page_fast'):
            cached_ft = _ft_scores_cache.get('data')
            ft_scores = cached_ft.get('scores', {}) if isinstance(cached_ft, dict) else {}
        else:
            ft_scores = _get_finished_scores_map()
        _enrich_ft_scores_with_match_hashes(ft_scores, enriched)
        resp_data = {
'''
    replace_once(path, old_scores, new_scores, "app nonblocking first-page scores")


def patch_app_src_and_runtime() -> None:
    src_path = ROOT / "static" / "js" / "app.js.src"
    runtime_path = ROOT / "static" / "js" / "app.js"
    src = src_path.read_text(encoding="utf-8")

    src = src.replace(
        "apiUrl = `/api/matches?market=${requestMarket}&date_filter=today_future&bulk=1${srcParam}`;",
        "apiUrl = `/api/matches?market=${requestMarket}&date_filter=today_future&limit=${matchesDisplayCount}&offset=0${srcParam}`;",
    )
    if src.count("date_filter=today_future&limit=${matchesDisplayCount}&offset=0") != 2:
        raise RuntimeError("expected two default first-page URLs in app.js.src")

    old_cache = '''        matches = cached.matches;
        totalMatchCount = cached.total;
        hasMoreMatches = false;
        currentOffset = matches.length;
'''
    new_cache = '''        matches = cached.matches;
        totalMatchCount = cached.total;
        hasMoreMatches = Boolean(cached.hasMore);
        currentOffset = matches.length;
'''
    if src.count(old_cache) != 1:
        raise RuntimeError("cached load state marker mismatch")
    src = src.replace(old_cache, new_cache, 1)

    old_cache_tail = '''        if (requestMarket.startsWith('dropping')) {
            attachTrendTooltipListeners();
        }
        _loadMatchesLock = false;
'''
    new_cache_tail = '''        if (requestMarket.startsWith('dropping')) {
            attachTrendTooltipListeners();
        }
        if (hasMoreMatches && requestDateFilter === 'ALL') {
            scheduleBackgroundMatchHydration();
        }
        _loadMatchesLock = false;
'''
    if src.count(old_cache_tail) != 1:
        raise RuntimeError("cached hydration scheduling marker mismatch")
    src = src.replace(old_cache_tail, new_cache_tail, 1)

    old_state = '''            matches = responseMatches;
            totalMatchCount = result && !Array.isArray(result) && Number.isFinite(result.total)
                ? result.total
                : matches.length;
            hasMoreMatches = false;
            currentOffset = matches.length;
            
            _matchesMarketCache[cacheKey] = { matches: matches, total: totalMatchCount, ts: Date.now() };
            
            filteredMatches = applySorting(matches);
            renderMatches(filteredMatches);
            
            if (currentMarket.startsWith('dropping')) {
                attachTrendTooltipListeners();
            }
'''
    new_state = '''            matches = responseMatches;
            totalMatchCount = result && !Array.isArray(result) && Number.isFinite(result.total)
                ? result.total
                : matches.length;
            hasMoreMatches = Boolean(result && !Array.isArray(result) && result.has_more);
            currentOffset = matches.length;
            
            _matchesMarketCache[cacheKey] = {
                matches: matches,
                total: totalMatchCount,
                hasMore: hasMoreMatches,
                ts: Date.now()
            };
            
            filteredMatches = applySorting(matches);
            renderMatches(filteredMatches);
            
            if (currentMarket.startsWith('dropping')) {
                attachTrendTooltipListeners();
            }
            if (hasMoreMatches && requestDateFilter === 'ALL') {
                scheduleBackgroundMatchHydration();
            }
'''
    if src.count(old_state) != 1:
        raise RuntimeError("first-page state marker mismatch")
    src = src.replace(old_state, new_state, 1)

    background_marker = "// Background load all remaining matches after initial page - NO re-render during load\nasync function loadAllRemainingMatches() {\n"
    scheduler = r'''let _backgroundMatchHydrationTimer = null;
function scheduleBackgroundMatchHydration() {
    if (!hasMoreMatches || dateFilterMode !== 'ALL' || _liveMode) return;
    if (_backgroundMatchHydrationTimer !== null) return;

    const scheduledMarket = currentMarket;
    const scheduledSource = currentSource;
    const run = () => {
        _backgroundMatchHydrationTimer = null;
        if (_liveMode || dateFilterMode !== 'ALL') return;
        if (currentMarket !== scheduledMarket || currentSource !== scheduledSource) return;
        loadAllRemainingMatches();
    };

    if (typeof window.requestIdleCallback === 'function') {
        _backgroundMatchHydrationTimer = window.requestIdleCallback(run, { timeout: 2500 });
    } else {
        _backgroundMatchHydrationTimer = setTimeout(run, 1200);
    }
}

// Background hydration preserves full-list search/filter behavior without blocking first paint.
async function loadAllRemainingMatches() {
'''
    if src.count(background_marker) != 1:
        raise RuntimeError("background loader marker mismatch")
    src = src.replace(background_marker, scheduler, 1)

    loader_start = src.index("async function loadAllRemainingMatches() {")
    max_pages_marker = "    const maxPages = 50; // Safety limit\n"
    max_pages_at = src.index(max_pages_marker, loader_start)
    if max_pages_at < 0:
        raise RuntimeError("background max-pages marker missing")
    fast_background = r'''    if (dateFilterMode === 'ALL') {
        const hydrationMarket = currentMarket;
        const hydrationSource = currentSource;
        const hydrationKey = `${hydrationMarket}|ALL|${hydrationSource}`;
        const srcParam = hydrationSource !== 'betfair' ? `&source=${hydrationSource}` : '';
        const apiUrl = `/api/matches?market=${hydrationMarket}&date_filter=today_future&bulk=1${srcParam}`;
        try {
            const payload = await _fetchMatchesWithTimeout(apiUrl, 20000);
            if (!payload.response.ok) throw new Error(`HTTP ${payload.response.status}`);
            if (_liveMode || dateFilterMode !== 'ALL') return;
            if (currentMarket !== hydrationMarket || currentSource !== hydrationSource) return;

            const result = payload.result;
            const hydrated = result && Array.isArray(result.matches) ? result.matches : null;
            if (!hydrated) return;

            if (result.finished_scores) _finishedScores = result.finished_scores;
            matches = hydrated;
            totalMatchCount = Number.isFinite(result.total) ? result.total : hydrated.length;
            hasMoreMatches = false;
            currentOffset = hydrated.length;
            _matchesMarketCache[hydrationKey] = {
                matches: hydrated,
                total: totalMatchCount,
                hasMore: false,
                ts: Date.now()
            };
            filteredMatches = applySorting(matches);
            renderMatches(filteredMatches);
            if (currentMarket.startsWith('dropping')) attachTrendTooltipListeners();
        } catch (error) {
            console.warn('[Background] bulk hydration failed; keeping fast first page', error);
        }
        return;
    }

'''
    src = src[:max_pages_at] + fast_background + src[max_pages_at:]
    src_path.write_text(src, encoding="utf-8")

    # Preserve every runtime byte outside the scoped loader/hydration block.
    runtime = runtime_path.read_text(encoding="utf-8")
    src_start = src.index("async function loadMatches(")
    src_end = src.index("function updateTableHeaders()", src_start)
    runtime_start = runtime.index("async function loadMatches(")
    runtime_end = runtime.index("function updateTableHeaders()", runtime_start)
    source_block = src[src_start:src_end]
    minified_block = jsmin(source_block)
    new_runtime = runtime[:runtime_start] + minified_block + "\n" + runtime[runtime_end:]
    if runtime[:runtime_start] != new_runtime[:runtime_start]:
        raise RuntimeError("runtime prefix changed outside scoped block")
    if runtime[runtime_end:] != new_runtime[runtime_start + len(minified_block) + 1:]:
        raise RuntimeError("runtime suffix changed outside scoped block")
    runtime_path.write_text(new_runtime, encoding="utf-8")


def patch_bootstrap_test() -> None:
    path = ROOT / "tests" / "test_app_bootstrap.js"
    text = path.read_text(encoding="utf-8")
    if "matchesDisplayCount: 20," not in text:
        marker = "    currentOffset: 0,\n"
        if text.count(marker) != 1:
            raise RuntimeError("bootstrap context currentOffset marker mismatch")
        text = text.replace(marker, marker + "    matchesDisplayCount: 20,\n", 1)

    text = text.replace(
        "/api/matches?market=moneyway_1x2&date_filter=today_future&bulk=1",
        "/api/matches?market=moneyway_1x2&date_filter=today_future&limit=20&offset=0",
    )
    path.write_text(text, encoding="utf-8")


def patch_fixture_tests() -> None:
    path = ROOT / "tests" / "test_fixture_uid_reader_patch.py"
    text = path.read_text(encoding="utf-8")
    if "test_first_page_fast_path_uses_rpc_without_full_fixture_fetch" in text:
        return

    text = text.replace(
        "class FakeResponse:\n    def __init__(self, rows, status_code=200):\n        self._rows = rows\n        self.status_code = status_code\n",
        "class FakeResponse:\n    def __init__(self, rows, status_code=200):\n        self._rows = rows\n        self.status_code = status_code\n",
        1,
    )
    text = text.replace(
        '''class FakeHttp:
    def __init__(self, fixture_rows):
        self.fixture_rows = fixture_rows
        self.urls = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if "/fixtures?" in url:
            return FakeResponse(self.fixture_rows)
        raise AssertionError(f"unexpected URL {url}")
''',
        '''class FakeHttp:
    def __init__(self, fixture_rows, rpc_rows=None, rpc_status=404):
        self.fixture_rows = fixture_rows
        self.rpc_rows = rpc_rows
        self.rpc_status = rpc_status
        self.urls = []
        self.posts = []

    def get(self, url, **kwargs):
        self.urls.append(url)
        if "/fixtures?" in url:
            return FakeResponse(self.fixture_rows)
        raise AssertionError(f"unexpected URL {url}")

    def post(self, url, **kwargs):
        self.posts.append((url, kwargs))
        return FakeResponse(self.rpc_rows or [], self.rpc_status)
''',
        1,
    )
    text = text.replace(
        '''    def __init__(self, fixture_rows, odds=None):
        self.http = FakeHttp(fixture_rows)
        self.odds = odds or {}
''',
        '''    def __init__(self, fixture_rows, odds=None, rpc_rows=None, rpc_status=404):
        self.http = FakeHttp(fixture_rows, rpc_rows=rpc_rows, rpc_status=rpc_status)
        self.odds = odds or {}
''',
        1,
    )
    text = text.replace(
        '''    def _normalize_history_row(self, row, market):
        return {"Odds1": row.get("odds1", "-")}
''',
        '''    def _normalize_history_row(self, row, market):
        return {"Odds1": row.get("odds1", "-"), "Volume": row.get("volume", "")}
''',
        1,
    )

    text += r'''


def test_first_page_fast_path_uses_rpc_without_full_fixture_fetch():
    rpc_rows = [
        {
            "row_data": {
                "fixture_uid": "uid-fast",
                "league": "Fast League",
                "home": "Fast Home",
                "away": "Fast Away",
                "date": "2026-10-09T18:00:00+00:00",
                "volume": "£ 7124.99",
                "odds1": "1.80",
            },
            "total_count": 1155,
        }
    ]
    client = FakeClient([], rpc_rows=rpc_rows, rpc_status=200)

    result = get_matches_paginated_uid_safe(
        client,
        "moneyway_1x2",
        limit=20,
        offset=0,
        today_only=True,
    )

    assert result["first_page_fast"] is True
    assert result["total"] == 1155
    assert result["has_more"] is True
    assert len(result["matches"]) == 1
    assert result["matches"][0]["fixture_uid"] == "uid-fast"
    assert result["matches"][0]["latest"]["Volume"] == "£ 7124.99"
    assert client.http.urls == [], "fast first page must not fetch the full fixtures table"
    assert len(client.http.posts) == 1
    assert client.http.posts[0][0].endswith("/rpc/sxf_matches_first_page_v1")
    assert client.http.posts[0][1]["json"]["p_limit"] == 20
'''
    path.write_text(text, encoding="utf-8")


def write_contract_test() -> None:
    path = ROOT / "tests" / "test_menu_first_page_contract.py"
    if path.exists():
        return
    path.write_text(
        '''from pathlib import Path\n\nROOT = Path(__file__).resolve().parents[1]\n\n\ndef test_first_page_rpc_is_bounded_and_not_security_definer():\n    sql = (ROOT / "migrations" / "2026_10_09_app_first_page_fast_path.sql").read_text()\n    assert "sxf_matches_first_page_v1" in sql\n    assert "greatest(1, least(coalesce(p_limit, 20), 100))" in sql\n    assert "sxf_parse_volume_v1(t.volume) desc nulls last" in sql\n    assert "security invoker" in sql.lower()\n    assert "security definer" not in sql.lower()\n    for market in (\n        "moneyway_1x2", "moneyway_ou25", "moneyway_btts",\n        "dropping_1x2", "dropping_ou25", "dropping_btts",\n    ):\n        assert market in sql\n\n\ndef test_app_first_paint_uses_bounded_endpoint_before_bulk_hydration():\n    src = (ROOT / "static" / "js" / "app.js.src").read_text()\n    assert "date_filter=today_future&limit=${matchesDisplayCount}&offset=0" in src\n    first_page = src.index("date_filter=today_future&limit=${matchesDisplayCount}&offset=0")\n    bulk = src.index("date_filter=today_future&bulk=1", first_page)\n    render = src.index("renderMatches(filteredMatches);", first_page)\n    assert first_page < render < bulk\n    assert "scheduleBackgroundMatchHydration" in src\n\n\ndef test_route_sends_today_future_to_uid_safe_paginated_reader():\n    app = (ROOT / "app.py").read_text()\n    assert "if date_filter in (None, 'today_future'):" in app\n    assert "today_only=(date_filter == 'today_future')" in app\n    assert "if result.get('first_page_fast')" in app\n''',
        encoding="utf-8",
    )


def main() -> None:
    patch_fixture_reader()
    patch_app_py()
    patch_app_src_and_runtime()
    patch_bootstrap_test()
    patch_fixture_tests()
    write_contract_test()


if __name__ == "__main__":
    main()
