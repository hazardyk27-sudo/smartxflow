import re
import json
import os
import time
import urllib.request
import urllib.parse
import urllib.error


ALIAS_MAP = {
    'atleticoma': 'atleticomadrid', 'atlmadrid': 'atleticomadrid', 'atleticodemadrid': 'atleticomadrid',
    'parisstg': 'psg', 'parissaintgermain': 'psg', 'parissg': 'psg',
    'mancity': 'manchestercity', 'manchestercity': 'manchestercity',
    'manutd': 'manchesterunited', 'manchesterunited': 'manchesterunited',
    'manchesterutd': 'manchesterunited', 'manunited': 'manchesterunited',
    'newcastleutd': 'newcastle', 'newcastleunited': 'newcastle',
    'tottenham': 'tottenham', 'spurs': 'tottenham',
    'intermilan': 'inter', 'internazionale': 'inter',
    'acmilan': 'milan',
    'bayernmunich': 'bayernmunchen', 'bayernmunchen': 'bayernmunchen', 'bayern': 'bayernmunchen',
    'bayerleverkusen': 'leverkusen', 'leverkusen': 'leverkusen',
    'borussiadortmund': 'dortmund', 'dortmund': 'dortmund',
    'sportingcp': 'sportingcp', 'sportinglisbon': 'sportingcp',
    'bodoglimt': 'bodoglimt', 'bodogli': 'bodoglimt',
    'sheffieldutd': 'sheffieldunited', 'sheffieldunited': 'sheffieldunited', 'sheffutd': 'sheffieldunited',
    'sheffieldwed': 'sheffieldwednesday', 'sheffieldwednesday': 'sheffieldwednesday',
    'westhamutd': 'westham', 'westhamunited': 'westham', 'westham': 'westham',
    'westbrom': 'westbrom', 'westbromwich': 'westbrom',
    'qpr': 'qpr', 'queensparkrangers': 'qpr',
    'oxfordutd': 'oxford', 'oxfordunited': 'oxford',
    'nottmforest': 'nottinghamforest', 'nottinghamforest': 'nottinghamforest', 'nottmfores': 'nottinghamforest',
    'wolverhampton': 'wolves', 'wolves': 'wolves',
    'crystalpala': 'crystalpalace', 'crystalpalace': 'crystalpalace',
    'bournemouth': 'bournemouth', 'afcbournemouth': 'bournemouth',
    'brighton': 'brighton', 'brightonhove': 'brighton',
    'galatasaray': 'galatasaray', 'fenerbahce': 'fenerbahce', 'besiktas': 'besiktas',
    'deportivop': 'pereira', 'deportivopereira': 'pereira', 'pereira': 'pereira',
    'americade': 'americadecali', 'americadecali': 'americadecali',
    'juniorfcb': 'junior', 'juniorbarranquilla': 'junior', 'junior': 'junior',
    'atleticona': 'atleticonacional', 'atleticonacional': 'atleticonacional', 'atlnacional': 'atleticonacional',
    'sportingcr': 'sportingcristal', 'sportingcristal': 'sportingcristal',
    'carabobofc': 'carabobo', 'carabobo': 'carabobo',
    'universidaddechile': 'udechile', 'universidad': 'udechile',
    'univdecon': 'uconcepcion', 'universidadconcepcion': 'uconcepcion',
    'elgeish': 'elgaish', 'elgaish': 'elgaish',
    'alahlycai': 'alahly', 'alahlycairo': 'alahly', 'alahly': 'alahly',
    'alianzalim': 'alianzalima', 'alianzalima': 'alianzalima',
    'philadelphi': 'philadelphiaunion', 'philadelphiaunion': 'philadelphiaunion',
    'cfamerica': 'clubamerica', 'clubamerica': 'clubamerica',
    'santoslagu': 'santoslaguna', 'santoslaguna': 'santoslaguna',
    'panaitoliko': 'panetolikos', 'panetolikos': 'panetolikos',
    'veresrivne': 'veresrivne',
    'rukhvynnyk': 'rukhlviv', 'rukhlviv': 'rukhlviv',
    'metalist19': 'metalist1925', 'metalist1925': 'metalist1925',
    'lnzlebedyn': 'lnzcherkasy', 'lnzcherkasy': 'lnzcherkasy',
    'leedsunite': 'leedsunited', 'leedsunited': 'leedsunited', 'leeds': 'leedsunited',
    'bristolcit': 'bristolcity', 'bristolcity': 'bristolcity',
    'buriramutd': 'buriramunited', 'buriramunited': 'buriramunited',
}

LEAGUE_MAP = {
    "English Premier League": ["English Premier League"],
    "English Sky Bet Championship": ["English Sky Bet Championship"],
    "English Sky Bet League 1": ["English Sky Bet League 1"],
    "English Sky Bet League 2": ["English Sky Bet League 2"],
    "English FA Cup": ["English FA Cup"],
    "English National League": ["English National League"],
    "Spanish La Liga": ["Spanish La Liga"],
    "Spanish Segunda Division": ["Spanish La Liga 2"],
    "German Bundesliga": ["German Bundesliga"],
    "German Bundesliga 2": ["German 2. Bundesliga"],
    "Italian Serie A": ["Italian Serie A"],
    "Italian Serie B": ["Italian Serie B"],
    "French Ligue 1": ["French Ligue 1"],
    "French Ligue 2": ["French Ligue 2"],
    "Turkish Super League": ["Turkish Super League"],
    "Turkish 1 Lig": ["Turkish 1. Lig"],
    "Dutch Eredivisie": ["Dutch Eredivisie"],
    "Dutch Eerste Divisie": ["Dutch Eerste Divisie"],
    "Portuguese Primeira Liga": ["Portuguese Liga"],
    "Belgian Challenger Pro League": ["Belgian First Division A"],
    "Scottish Premiership": ["Scottish Premiership"],
    "Scottish Championship": ["Scottish Championship"],
    "Argentinian Primera Division": ["Argentine Liga Profesional"],
    "Brazilian Serie A": ["Brazilian Serie A"],
    "Brazilian Gaucho Matches": ["Brazilian Gaucho"],
    "Brazilian Mineiro Matches": ["Brazilian Mineiro"],
    "Colombian Primera A": ["Colombian Primera A"],
    "Mexican Liga MX": ["Mexican Liga MX"],
    "US MLS": ["American MLS"],
    "Peruvian Primera Division": ["Peruvian Primera Division"],
    "Chilean Primera Division": ["Chilean Primera Division"],
    "Greek Super League": ["Greek Super League"],
    "Polish Ekstraklasa": ["Polish Ekstraklasa"],
    "Romanian Liga I": ["Romanian Liga 1"],
    "Danish Superliga": ["Danish Superliga"],
    "Danish 1st Division": ["Danish 1st Division"],
    "Hungarian NB II": ["Hungarian NB II"],
    "Ukrainian Premier League": ["Ukrainian Premier League"],
    "Australian A-League Men": ["Australian A-League"],
    "Egyptian Premier": ["Egyptian Premier"],
    "UAE Arabian Gulf League": ["UAE Arabian Gulf League"],
    "Indian Super League": ["Indian Super League"],
    "Indonesian Super League": ["Indonesian Super League"],
    "Icelandic League Cup": ["Icelandic League Cup"],
    "Irish Premier Division": ["Irish Premier Division"],
    "Lithuanian A Lyga": ["Lithuanian A Lyga"],
    "Swedish Cup": ["Swedish Cup"],
    "Croatian Cup": ["Croatian First Football League"],
    "Slovenian Premier League": ["Slovenian Premier League"],
    "Czech U19": ["Czech First League"],
    "UEFA Champions League": ["UEFA Champions League"],
    "UEFA Europa League": ["UEFA Europa League"],
    "UEFA Europa Conference League": ["UEFA Europa Conference League"],
    "CONMEBOL Copa Libertadores": ["CONMEBOL Copa Libertadores"],
    "CONCACAF Champions League": ["CONCACAF Champions League"],
    "AFC Champions League": ["AFC Champions League Elite", "AFC Champions League"],
    "AFC Champions League Two": ["AFC Champions League Two"],
    "Bulgarian A League": ["Bulgarian First League"],
    "Uruguayan Primera Division": ["Uruguayan Primera Division"],
    "Venezuelan Primera Division": ["Venezuelan Primera Division"],
    "Paraguayan Primera Division": ["Paraguayan Primera Division"],
    "Norwegian Cup": ["Norwegian Cup"],
    "Serbian Super League": ["Serbian Super Liga", "Serbian Super League"],
    "Albanian Superliga": ["Albanian Superliga"],
    "Russian Premier League": ["Russian Premier League"],
    "Azerbaijan Premier League": ["Azerbaijan Premier League"],
}


def _normalize_league(name):
    if not name:
        return ""
    return re.sub(r'[^a-z0-9]', '', name.lower().strip())


def _leagues_match(store_league, flash_league):
    if not store_league or not flash_league:
        return False

    sn = _normalize_league(store_league)
    fn = _normalize_league(flash_league)

    if sn == fn:
        return True

    if sn in fn or fn in sn:
        return True

    flash_targets = LEAGUE_MAP.get(store_league, [])
    for target in flash_targets:
        if _normalize_league(target) == fn:
            return True

    for store_key, flash_list in LEAGUE_MAP.items():
        if _normalize_league(store_key) == sn:
            for fl in flash_list:
                if _normalize_league(fl) == fn:
                    return True

    return False


def _normalize_team(name):
    if not name:
        return ""
    import unicodedata
    n = unicodedata.normalize('NFKD', name)
    n = ''.join(c for c in n if not unicodedata.combining(c))
    n = n.lower().strip()
    n = re.sub(r'\([a-z]{2,4}\)', '', n)
    return re.sub(r'[^a-z0-9]', '', n)


def _resolve_alias(normed):
    if normed in ALIAS_MAP:
        return ALIAS_MAP[normed]
    for key, val in ALIAS_MAP.items():
        if len(key) >= 6 and len(normed) >= 6 and normed.startswith(key[:6]):
            return val
    return normed


def _teams_match(store_name, flash_name):
    sn = _normalize_team(store_name)
    fn = _normalize_team(flash_name)
    if not sn or not fn:
        return False
    if sn == fn:
        return True
    rs, rf = _resolve_alias(sn), _resolve_alias(fn)
    if rs == rf:
        return True
    if len(sn) >= 4 and len(fn) >= 4:
        if sn in fn or fn in sn:
            return True
    if len(rs) >= 4 and len(rf) >= 4:
        if rs in rf or rf in rs:
            return True
    if len(sn) >= 5 and len(fn) >= 5 and sn[:5] == fn[:5]:
        return True
    return False


def parse_flashscore_markdown(md_text):
    lines = md_text.split('\n')
    lines = [l.strip() for l in lines if l.strip()]
    matches = []

    for i in range(len(lines)):
        time_match = re.match(r'^(\d{2})\.(\d{2})\.\s+(\d{2}:\d{2})$', lines[i])
        if not time_match:
            continue

        day = time_match.group(1)
        month = time_match.group(2)
        time_str = time_match.group(3)

        home = None
        away = None
        score_str = None

        next_block = len(lines)
        for k in range(i + 1, len(lines)):
            if re.match(r'^\d{2}\.\d{2}\.\s+\d{2}:\d{2}$', lines[k]):
                next_block = k
                break

        for j in range(i + 1, next_block):
            team_match = re.match(r'!\[.*?\]\(.*?\)(.+)$', lines[j])
            if team_match:
                name = team_match.group(1).strip()
                if not home:
                    home = name
                elif not away:
                    away = name

            if re.match(r'^\d{1,4}$', lines[j]) and home and not score_str:
                s = lines[j]
                if len(s) == 2:
                    score_str = f"{s[0]}-{s[1]}"
                elif len(s) == 3:
                    score_str = f"{s[0]}-{s[1:]}"
                elif len(s) == 4:
                    score_str = f"{s[:2]}-{s[2:]}"
                elif len(s) == 1:
                    score_str = f"{s}-0"

        if home and away and score_str:
            parts = score_str.split('-')
            hg = int(parts[0])
            ag = int(parts[1])
            if hg > ag:
                result = "HOME"
            elif hg < ag:
                result = "AWAY"
            else:
                result = "DRAW"

            matches.append({
                "date_day": day,
                "date_month": month,
                "time": time_str,
                "home": home,
                "away": away,
                "score": score_str,
                "home_goals": hg,
                "away_goals": ag,
                "result": result,
            })

    return matches


def load_cached_results(results_path=None):
    if results_path is None:
        results_path = os.path.join(os.path.dirname(__file__), 'data', 'flashscore_results.json')
    if not os.path.exists(results_path):
        return {}
    with open(results_path) as f:
        return json.load(f)


def save_cached_results(results_by_league, results_path=None):
    if results_path is None:
        results_path = os.path.join(os.path.dirname(__file__), 'data', 'flashscore_results.json')
    with open(results_path, 'w') as f:
        json.dump(results_by_league, f, ensure_ascii=False, indent=2)


def _try_match_entry(store_home, store_away, kick_day, kick_month, matches_for_league):
    for m in matches_for_league:
        if m["date_day"] != kick_day or m["date_month"] != kick_month:
            continue
        if _teams_match(store_home, m["home"]) and _teams_match(store_away, m["away"]):
            return m["result"], m["score"]
        if _teams_match(store_home, m["away"]) and _teams_match(store_away, m["home"]):
            rev = {"HOME": "AWAY", "AWAY": "HOME", "DRAW": "DRAW"}
            return rev.get(m["result"], m["result"]), f"{m['away_goals']}-{m['home_goals']}"
    return None, None


def update_store_results(store_path, results_by_league=None):
    from smartxflow_similarity.feature_store import load_store, save_store

    if results_by_league is None:
        results_by_league = load_cached_results()

    if not results_by_league:
        return 0

    entries = load_store(store_path)
    if not entries:
        return 0

    updated = 0
    for entry in entries:
        if entry.get("result"):
            continue

        mn = entry.get("match_name", "")
        if " vs " not in mn:
            continue

        first_vs = mn.index(" vs ")
        store_home = mn[:first_vs].strip()
        store_away = mn[first_vs + 4:].strip()

        kickoff = entry.get("kickoff", "")
        if not kickoff:
            continue

        kick_day = kickoff[8:10] if len(kickoff) >= 10 else ""
        kick_month = kickoff[5:7] if len(kickoff) >= 7 else ""
        if not kick_day or not kick_month:
            continue

        store_league = entry.get("league", "")

        result_val = None
        score_val = None

        for flash_league, matches in results_by_league.items():
            if not _leagues_match(store_league, flash_league):
                continue
            result_val, score_val = _try_match_entry(
                store_home, store_away, kick_day, kick_month, matches
            )
            if result_val:
                break

        if not result_val:
            all_results = []
            for matches in results_by_league.values():
                all_results.extend(matches)
            result_val, score_val = _try_match_entry(
                store_home, store_away, kick_day, kick_month, all_results
            )

        if result_val:
            entry["result"] = result_val
            entry["score"] = score_val
            updated += 1

    save_store(entries, store_path)
    return updated


SPORTSDB_API = "https://www.thesportsdb.com/api/v1/json/3"
SPORTSDB_SEASON = "2025-2026"

_TEAM_PREFIXES = {
    "fc", "fk", "cd", "ca", "sc", "pfc", "cf", "nk", "sd", "sv", "tsv", "ssv",
    "as", "us", "ss", "ac", "al", "cs", "rc", "rcd", "ud", "uc", "ec", "se",
    "afc", "bsc", "vfb", "vfl", "bv", "if", "ik", "gd", "gk",
}


def _extract_search_name(team_name):
    words = team_name.strip().split()
    meaningful = [w for w in words if w.lower().rstrip(".") not in _TEAM_PREFIXES and len(w) > 1]
    if meaningful:
        return " ".join(meaningful)
    return team_name.strip()


_sportsdb_rate_limited = False


def _sportsdb_search(home, away):
    global _sportsdb_rate_limited
    if _sportsdb_rate_limited:
        return []
    query = f"{home}_vs_{away}"
    url = f"{SPORTSDB_API}/searchevents.php?e={urllib.parse.quote(query)}&s={SPORTSDB_SEASON}"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "SmartXFlow/1.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        data = json.loads(resp.read())
        time.sleep(2)
        return data.get("event") or []
    except urllib.error.HTTPError as e:
        if e.code == 429:
            print(f"[ResultAPI] 429 rate limit, bu batch durduruldu")
            _sportsdb_rate_limited = True
            return []
        return []
    except Exception:
        return []


def _multi_search(home, away):
    clean_h = _extract_search_name(home)
    clean_a = _extract_search_name(away)

    queries_to_try = [(home, away)]
    if clean_h != home or clean_a != away:
        queries_to_try.append((clean_h, clean_a))
    queries_to_try.append((away, home))
    if clean_h != home or clean_a != away:
        queries_to_try.append((clean_a, clean_h))

    seen = set()
    for h, a in queries_to_try:
        key = (h, a)
        if key in seen:
            continue
        seen.add(key)
        events = _sportsdb_search(h, a)
        if events:
            return events

    return []


def _match_sportsdb_event(store_home, store_away, kick_day, kick_month, events):
    for ev in events:
        ev_home = ev.get("strHomeTeam", "")
        ev_away = ev.get("strAwayTeam", "")
        ev_date = ev.get("dateEvent", "")
        ev_home_score = ev.get("intHomeScore")
        ev_away_score = ev.get("intAwayScore")

        if ev_home_score is None or ev_away_score is None:
            continue

        ev_day = ev_date[8:10] if len(ev_date) >= 10 else ""
        ev_month = ev_date[5:7] if len(ev_date) >= 7 else ""
        if ev_day != kick_day or ev_month != kick_month:
            continue

        if _teams_match(store_home, ev_home) and _teams_match(store_away, ev_away):
            hg, ag = int(ev_home_score), int(ev_away_score)
            result = "HOME" if hg > ag else ("AWAY" if ag > hg else "DRAW")
            return result, f"{hg}-{ag}"

        if _teams_match(store_home, ev_away) and _teams_match(store_away, ev_home):
            hg, ag = int(ev_home_score), int(ev_away_score)
            result = "HOME" if ag > hg else ("AWAY" if hg > ag else "DRAW")
            return result, f"{ag}-{hg}"

    return None, None


def _parse_kickoff_utc(kickoff_str):
    from datetime import datetime, timezone
    try:
        if kickoff_str.endswith("Z"):
            kickoff_str = kickoff_str[:-1] + "+00:00"
        dt = datetime.fromisoformat(kickoff_str)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except Exception:
        return None


def fetch_results_from_api(store_path, max_queries=50, skip_attempted=False):
    global _sportsdb_rate_limited
    _sportsdb_rate_limited = False
    from datetime import datetime, timezone
    from smartxflow_similarity.feature_store import load_store, save_store

    entries = load_store(store_path)
    if not entries:
        return 0, 0

    now_utc = datetime.now(timezone.utc)

    pending = []
    for entry in entries:
        if entry.get("result"):
            continue
        if skip_attempted and entry.get("_api_attempted"):
            continue
        mn = entry.get("match_name", "")
        if " vs " not in mn:
            continue
        kickoff = entry.get("kickoff", "")
        if not kickoff or len(kickoff) < 10:
            continue
        kick_dt = _parse_kickoff_utc(kickoff)
        if kick_dt is None or kick_dt > now_utc:
            continue
        pending.append(entry)

    if not pending:
        return 0, 0

    pending = pending[:max_queries]
    updated = 0
    queried = 0
    cache_additions = []

    for entry in pending:
        mn = entry["match_name"]
        first_vs = mn.index(" vs ")
        store_home = mn[:first_vs].strip()
        store_away = mn[first_vs + 4:].strip()
        kickoff = entry["kickoff"]
        kick_day = kickoff[8:10]
        kick_month = kickoff[5:7]

        events = _multi_search(store_home, store_away)

        if _sportsdb_rate_limited:
            break

        queried += 1
        entry["_api_attempted"] = True

        result_val, score_val = _match_sportsdb_event(
            store_home, store_away, kick_day, kick_month, events
        )

        if result_val:
            entry["result"] = result_val
            entry["score"] = score_val
            updated += 1
            hg, ag = score_val.split("-")
            cache_additions.append({
                "home": store_home,
                "away": store_away,
                "date_day": kick_day,
                "date_month": kick_month,
                "score": score_val,
                "home_goals": int(hg),
                "away_goals": int(ag),
                "result": result_val,
                "league": entry.get("league", "TheSportsDB"),
            })

    if queried > 0:
        save_store(entries, store_path)
    if updated > 0:
        _update_flashscore_cache(cache_additions)
        print(f"[ResultAPI] {updated}/{queried} maç sonucu TheSportsDB'den çekildi")

    return updated, queried


_BACKFILL_FLAG = os.path.join(os.path.dirname(__file__), 'data', '.backfill_done')


def backfill_all_results(store_path):
    if os.path.exists(_BACKFILL_FLAG):
        return 0

    from smartxflow_similarity.feature_store import load_store, save_store
    entries = load_store(store_path)
    cleared = 0
    for entry in entries:
        if not entry.get("result") and entry.get("_api_attempted"):
            del entry["_api_attempted"]
            cleared += 1
    if cleared > 0:
        save_store(entries, store_path)
        print(f"[ResultAPI Backfill] {cleared} maçın _api_attempted bayrağı temizlendi")

    total_matched = 0
    total_queried = 0
    batch = 1
    while True:
        matched, queried = fetch_results_from_api(store_path, max_queries=50, skip_attempted=True)
        total_matched += matched
        total_queried += queried
        print(f"[ResultAPI Backfill] Batch {batch}: {matched}/{queried} eşleşti (toplam: {total_matched})")
        if queried == 0 or _sportsdb_rate_limited:
            break
        batch += 1

    if _sportsdb_rate_limited:
        print(f"[ResultAPI Backfill] Rate limit, sonraki çalışmada devam edecek ({total_matched} çekildi, {total_queried} sorgulandı)")
    else:
        with open(_BACKFILL_FLAG, 'w') as f:
            f.write("done")
        print(f"[ResultAPI Backfill] Tamamlandı: {total_matched}/{total_queried} sonuç çekildi")

    return total_matched


def _update_flashscore_cache(additions):
    if not additions:
        return
    cache = load_cached_results()
    for item in additions:
        league = item.get("league", "TheSportsDB")
        if league not in cache:
            cache[league] = []
        exists = False
        for m in cache[league]:
            if (m.get("home") == item["home"] and m.get("away") == item["away"]
                    and m.get("date_day") == item["date_day"]
                    and m.get("date_month") == item["date_month"]):
                exists = True
                break
        if not exists:
            cache[league].append(item)
    save_cached_results(cache)
