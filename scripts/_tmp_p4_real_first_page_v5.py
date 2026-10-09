from pathlib import Path
import re
from rjsmin import jsmin


def replace_once(text: str, old: str, new: str, label: str) -> str:
    count = text.count(old)
    if count != 1:
        raise SystemExit(f"{label}: expected 1 exact match, got {count}")
    return text.replace(old, new, 1)


# Reuse the already-reviewed scoped P4 patch, repairing only its generated method indentation.
workflow = Path('.github/workflows/p4-real-first-page-patch.yml').read_text(encoding='utf-8')
start_marker = "          python - <<'PY'\n"
end_marker = "          PY\n\n      - name: Validate scoped patch"
start = workflow.index(start_marker) + len(start_marker)
end = workflow.index(end_marker, start)
block = workflow[start:end]
script = '\n'.join(line[10:] if line.startswith('          ') else line for line in block.splitlines()) + '\n'
old = "text = pattern.sub(new_fn, text, count=1)"
repair = "new_fn_lines = new_fn.splitlines()\nnew_fn = new_fn_lines[0] + '\\n' + '\\n'.join(('    ' + line if line else line) for line in new_fn_lines[1:]) + '\\n'\ntext = pattern.sub(lambda _m: new_fn, text, count=1)"
if script.count(old) != 1:
    raise SystemExit(f"expected one method substitution, found {script.count(old)}")
script = script.replace(old, repair, 1)
exec(compile(script, '<p4-scoped-patch>', 'exec'), {'__name__': '__main__'})


# Runtime actually binds this UID-safe reader over SupabaseClient.get_matches_paginated.
# Make the bound reader truly paginated and preserve global VOLUME-desc first paint.
p = Path('services/fixture_uid_reader_patch.py')
text = p.read_text(encoding='utf-8')
pattern = re.compile(r"def get_matches_paginated_uid_safe\(.*?(?=\ndef _bind_history_uid_preference\()", re.S)
blocks = list(pattern.finditer(text))
if len(blocks) != 1:
    raise SystemExit(f"UID paginated reader: expected 1 block, got {len(blocks)}")

new_uid_reader = '''def get_matches_paginated_uid_safe(
    client: Any,
    market: str,
    limit: int = 20,
    offset: int = 0,
    today_only: bool = False,
) -> Dict[str, Any]:
    """UID-safe reader with a fast volume-first paint and real fixture pagination.

    Offset 0 / <=20 is the /app first-paint path. It obtains the global volume
    leaders from the compact current-state market table, then resolves fixture
    identity only for those candidates. Larger/background pages read fixtures
    with real limit/offset and fetch odds only for that page.
    """
    if not getattr(client, "is_available", False):
        return {"matches": [], "total": 0, "has_more": False}

    try:
        tr_tz = pytz.timezone("Europe/Istanbul")
        now_tr = datetime.now(tr_tz)
        today_date = now_tr.date()
        seven_days_ago = (today_date - timedelta(days=7)).strftime("%Y-%m-%d")
        date_gte = (
            (today_date - timedelta(days=1)).strftime("%Y-%m-%d")
            if today_only
            else seven_days_ago
        )
        page_limit = max(1, min(int(limit or 20), 200))
        page_offset = max(0, int(offset or 0))

        def _volume_number(value: Any) -> float:
            if value in (None, "", "-"):
                return 0.0
            if isinstance(value, (int, float)):
                return float(value)
            raw = str(value).replace("£", "").replace("€", "").replace("$", "").replace(",", "").replace(" ", "")
            multiplier = 1.0
            upper = raw.upper()
            if "M" in upper:
                multiplier = 1_000_000.0
                raw = re.sub("M", "", raw, flags=re.IGNORECASE)
            elif "K" in upper:
                multiplier = 1_000.0
                raw = re.sub("K", "", raw, flags=re.IGNORECASE)
            try:
                return float(raw) * multiplier
            except (TypeError, ValueError):
                return 0.0

        def _parse_total(response: Any, fallback: int) -> int:
            headers = getattr(response, "headers", {}) or {}
            content_range = headers.get("Content-Range", "") if hasattr(headers, "get") else ""
            if "/" in content_range:
                try:
                    total_part = content_range.rsplit("/", 1)[1]
                    if total_part != "*":
                        return int(total_part)
                except Exception:
                    pass
            return fallback

        def _fixture_page(page_size: int, page_start: int):
            headers = dict(client._headers())
            headers["Prefer"] = "count=exact"
            url = (
                f"{client._rest_url('fixtures')}"
                "?select=fixture_uid,match_id_hash,home_team,away_team,league,kickoff_utc,fixture_date"
                f"&fixture_date=gte.{quote(date_gte, safe='')}"
                "&order=kickoff_utc.asc"
                f"&limit={page_size}&offset={page_start}"
            )
            response = client._get_http_client().get(url, headers=headers, timeout=20)
            if response.status_code not in (200, 206):
                return [], 0, 0
            payload = response.json()
            raw_rows = payload if isinstance(payload, list) else []
            total = _parse_total(response, page_start + len(raw_rows) + (1 if len(raw_rows) >= page_size else 0))
            return client._dedupe_fixtures(raw_rows), total, len(raw_rows)

        def _fetch_fixture_candidates(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
            fixtures: List[Dict[str, Any]] = []
            batch_size = 20
            for index in range(0, len(rows), batch_size):
                filters = []
                for row in rows[index:index + batch_size]:
                    home = str(row.get("home") or "").strip()
                    away = str(row.get("away") or "").strip()
                    kickoff = str(row.get("date") or "").strip()
                    league = str(row.get("league") or "").strip()
                    if not home or not away or not kickoff:
                        continue
                    parts = [
                        f"home_team.eq.{quote(home, safe='')}",
                        f"away_team.eq.{quote(away, safe='')}",
                        f"kickoff_utc.eq.{quote(kickoff, safe='')}",
                    ]
                    if league:
                        parts.append(f"league.eq.{quote(league, safe='')}")
                    filters.append("and(" + ",".join(parts) + ")")
                if not filters:
                    continue
                url = (
                    f"{client._rest_url('fixtures')}"
                    "?select=fixture_uid,match_id_hash,home_team,away_team,league,kickoff_utc,fixture_date"
                    f"&or=({','.join(filters)})"
                    f"&limit={max(40, len(filters) * 2)}"
                )
                response = client._get_http_client().get(url, headers=client._headers(), timeout=20)
                if response.status_code == 200:
                    payload = response.json()
                    if isinstance(payload, list):
                        fixtures.extend(payload)
            return client._dedupe_fixtures(fixtures)

        def _fetch_page_odds(fixtures: List[Dict[str, Any]]) -> Dict[tuple, Dict[str, Any]]:
            rows: List[Dict[str, Any]] = []
            batch_size = 25
            for index in range(0, len(fixtures), batch_size):
                filters = []
                for fixture in fixtures[index:index + batch_size]:
                    home = str(fixture.get("home_team") or "").strip()
                    away = str(fixture.get("away_team") or "").strip()
                    kickoff = str(fixture.get("kickoff_utc") or "").strip()
                    if not home or not away or not kickoff:
                        continue
                    filters.append(
                        "and("
                        f"home.eq.{quote(home, safe='')},"
                        f"away.eq.{quote(away, safe='')},"
                        f"date.eq.{quote(kickoff, safe='')}"
                        ")"
                    )
                if not filters:
                    continue
                url = (
                    f"{client._rest_url(market)}?select=*"
                    f"&or=({','.join(filters)})"
                    f"&limit={max(100, len(filters) * 4)}"
                )
                response = client._get_http_client().get(url, headers=client._headers(), timeout=20)
                if response.status_code == 200:
                    payload = response.json()
                    if isinstance(payload, list):
                        rows.extend(payload)
            result: Dict[tuple, Dict[str, Any]] = {}
            for row in rows:
                result[(row.get("home", ""), row.get("away", ""), row.get("date", ""))] = row
            return result

        def _build_match(fixture: Dict[str, Any], row: Optional[Dict[str, Any]]) -> Dict[str, Any]:
            kickoff_utc = fixture.get("kickoff_utc", "")
            date_display = fixture.get("fixture_date", "")
            if kickoff_utc:
                try:
                    kickoff_dt = datetime.fromisoformat(str(kickoff_utc).replace("Z", "+00:00"))
                    date_display = kickoff_dt.astimezone(tr_tz).strftime("%d.%b %H:%M")
                except Exception:
                    pass
            latest = client._normalize_history_row(row, market) if row else client._get_empty_odds(market)
            return {
                "fixture_uid": fixture.get("fixture_uid"),
                "home_team": fixture.get("home_team", ""),
                "away_team": fixture.get("away_team", ""),
                "league": fixture.get("league", ""),
                "date": date_display,
                "match_id_hash": fixture.get("match_id_hash", ""),
                "kickoff_utc": kickoff_utc,
                "latest": latest,
            }

        # First paint: preserve the UI's default global VOLUME ↓ order without
        # building every fixture. The main market table is the compact current snapshot.
        if page_offset == 0 and page_limit <= 20:
            main_odds = client._fetch_main_table_odds(market, date_gte=date_gte)
            if main_odds:
                ranked_rows = sorted(
                    main_odds.values(),
                    key=lambda row: _volume_number(row.get("volume")),
                    reverse=True,
                )
                candidate_rows = ranked_rows[:max(page_limit * 4, 80)]
                candidate_fixtures = _fetch_fixture_candidates(candidate_rows)
                fixture_by_physical = {
                    _physical_key(fixture): fixture
                    for fixture in candidate_fixtures
                    if _physical_key(fixture) is not None
                }
                seed_fixtures, total, _ = _fixture_page(page_limit, 0)
                selected: List[Dict[str, Any]] = []
                selected_keys = set()
                for row in candidate_rows:
                    key = _physical_key(row)
                    fixture = fixture_by_physical.get(key)
                    if fixture is None or key in selected_keys:
                        continue
                    selected.append(_build_match(fixture, row))
                    selected_keys.add(key)
                    if len(selected) >= page_limit:
                        break

                # If the current market has fewer than 20 populated rows, fill the
                # remainder with zero-volume fixtures so the first paint stays full.
                for fixture in seed_fixtures:
                    if len(selected) >= page_limit:
                        break
                    key = _physical_key(fixture)
                    if key in selected_keys:
                        continue
                    row = main_odds.get((
                        fixture.get("home_team", ""),
                        fixture.get("away_team", ""),
                        fixture.get("kickoff_utc", ""),
                    ))
                    selected.append(_build_match(fixture, row))
                    selected_keys.add(key)

                selected.sort(
                    key=lambda match: _volume_number((match.get("latest") or {}).get("Volume")),
                    reverse=True,
                )
                if selected:
                    return {
                        "matches": selected[:page_limit],
                        "total": max(total, len(selected)),
                        "has_more": max(total, len(selected)) > len(selected[:page_limit]),
                    }

        fixtures, total, raw_count = _fixture_page(page_limit, page_offset)
        if not fixtures and raw_count == 0:
            return {"matches": [], "total": total, "has_more": False}
        page_odds = _fetch_page_odds(fixtures)
        matches = [
            _build_match(
                fixture,
                page_odds.get((
                    fixture.get("home_team", ""),
                    fixture.get("away_team", ""),
                    fixture.get("kickoff_utc", ""),
                )),
            )
            for fixture in fixtures
        ]
        return {
            "matches": matches,
            "total": total,
            "has_more": page_offset + raw_count < total,
        }
    except Exception as exc:
        print(f"[FixtureUIDReader] paginated reader error: {exc}")
        return {"matches": [], "total": 0, "has_more": False}

'''
text = pattern.sub(new_uid_reader, text, count=1)
p.write_text(text, encoding='utf-8')


# Background hydration must start at raw fixture offset 0 because first paint came
# from volume-ranked market rows, then merge UID/physical identities instead of append.
p = Path('static/js/app.js.src')
src = p.read_text(encoding='utf-8')
src = replace_once(src, '    let pageOffset = currentOffset;\n', '    let pageOffset = 0;\n', 'background raw offset')
src = replace_once(
    src,
    '                allNewMatches = allNewMatches.concat(newMatches);\n                pageOffset += newMatches.length;\n                currentOffset = pageOffset;\n',
    '                allNewMatches = allNewMatches.concat(newMatches);\n                pageOffset += pageSize;\n                currentOffset = pageOffset;\n',
    'background raw-page advance',
)
old_merge = '''        if (allNewMatches.length > 0) {
            matches = matches.concat(allNewMatches);
            filteredMatches = applySorting(matches);
            renderMatches(filteredMatches);

            if (!hasMoreMatches) {
                _matchesMarketCache[cacheKey] = {
                    matches: matches,
                    total: totalMatchCount,
                    ts: Date.now()
                };
            }
'''
new_merge = '''        if (allNewMatches.length > 0) {
            const byIdentity = new Map();
            const identityKey = (match) => {
                const uid = String((match && match.fixture_uid) || '').trim();
                if (uid) return `uid:${uid}`;
                const home = String((match && match.home_team) || '').trim();
                const away = String((match && match.away_team) || '').trim();
                const league = String((match && match.league) || '').trim();
                const kickoff = String((match && (match.kickoff_utc || match.date)) || '').trim();
                if (home || away || league || kickoff) return `physical:${home}|${away}|${league}|${kickoff}`;
                return `legacy:${String((match && match.match_id_hash) || '')}`;
            };
            for (const match of matches.concat(allNewMatches)) {
                byIdentity.set(identityKey(match), match);
            }
            matches = Array.from(byIdentity.values());
            filteredMatches = applySorting(matches);
            renderMatches(filteredMatches);

            if (!hasMoreMatches) {
                totalMatchCount = matches.length;
                _matchesMarketCache[cacheKey] = {
                    matches: matches,
                    total: totalMatchCount,
                    ts: Date.now()
                };
            }
'''
src = replace_once(src, old_merge, new_merge, 'background UID merge')
p.write_text(src, encoding='utf-8')

# Re-splice only the background function into the served runtime.
source_bg_start = src.index('async function loadAllRemainingMatches()')
source_bg_end = src.index('function updateTableHeaders()', source_bg_start)
bg_min = jsmin(src[source_bg_start:source_bg_end]).strip()
p = Path('static/js/app.js')
runtime = p.read_text(encoding='utf-8')
runtime_bg_start = runtime.index('async function loadAllRemainingMatches()')
runtime_bg_end = runtime.index('function updateTableHeaders()', runtime_bg_start)
runtime = runtime[:runtime_bg_start] + bg_min + runtime[runtime_bg_end:]
p.write_text(runtime, encoding='utf-8')


# Bring bootstrap VM tests to the real runtime globals and new first-page URL.
p = Path('tests/test_app_bootstrap.js')
text = p.read_text(encoding='utf-8')
needle = '      totalMatchCount: 0,\n      hasMoreMatches: false,\n'
replacement = '      totalMatchCount: 0,\n      matchesDisplayCount: 20,\n      hasMoreMatches: false,\n'
count = text.count(needle)
if count < 2:
    raise SystemExit(f'bootstrap harness: expected >=2 match-state blocks, got {count}')
text = text.replace(needle, replacement)
text = text.replace(
    '/api/matches?market=moneyway_1x2&date_filter=today_future&bulk=1',
    '/api/matches?market=moneyway_1x2&date_filter=today_future&limit=20&offset=0',
)
p.write_text(text, encoding='utf-8')


# Strengthen P4 static regression so the runtime-bound UID wrapper cannot regress to full fetch.
p = Path('tests/test_real_first_page_path.js')
text = p.read_text(encoding='utf-8')
if "fixture_uid_reader_patch.py" not in text:
    text = text.replace(
        "const appPy = fs.readFileSync(path.join(root, 'app.py'), 'utf8');\n",
        "const appPy = fs.readFileSync(path.join(root, 'app.py'), 'utf8');\nconst uidReader = fs.readFileSync(path.join(root, 'services/fixture_uid_reader_patch.py'), 'utf8');\n",
        1,
    )
    text += '''\n\ntest('runtime-bound UID reader keeps volume-first paint and real fixture pages', () => {\n  const fn = between(uidReader, 'def get_matches_paginated_uid_safe(', 'def _bind_history_uid_preference()');\n  assert.match(fn, /page_offset == 0 and page_limit <= 20/);\n  assert.match(fn, /_volume_number/);\n  assert.match(fn, /ranked_rows/);\n  assert.match(fn, /limit=\\{page_size\\}&offset=\\{page_start\\}/);\n  assert.match(fn, /_fetch_page_odds/);\n  assert.doesNotMatch(fn, /_fetch_fixture_rows\\(client/);\n});\n\ntest('background hydration restarts from raw offset zero and dedupes physical identity', () => {\n  const bg = between(source, 'async function loadAllRemainingMatches()', 'function updateTableHeaders()');\n  assert.match(bg, /let pageOffset = 0/);\n  assert.match(bg, /pageOffset \\+= pageSize/);\n  assert.match(bg, /fixture_uid/);\n  assert.match(bg, /physical:/);\n  assert.match(bg, /totalMatchCount = matches\\.length/);\n});\n'''
p.write_text(text, encoding='utf-8')
