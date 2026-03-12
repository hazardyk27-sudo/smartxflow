import re
import json
import os
import subprocess
import sys
from datetime import datetime


FLASHSCORE_LEAGUES = {
    "england/championship": "English Sky Bet Championship",
    "england/premier-league": "English Premier League",
    "spain/laliga": "Spanish La Liga",
    "germany/bundesliga": "German Bundesliga",
    "italy/serie-a": "Italian Serie A",
    "france/ligue-1": "French Ligue 1",
    "turkey/super-lig": "Turkish Super League",
    "europe/champions-league": "UEFA Champions League",
    "europe/europa-league": "UEFA Europa League",
    "europe/europa-conference-league": "UEFA Europa Conference League",
    "netherlands/eredivisie": "Dutch Eredivisie",
    "portugal/liga-portugal": "Portuguese Liga",
    "belgium/jupiler-pro-league": "Belgian First Division A",
    "scotland/premiership": "Scottish Premiership",
    "england/league-one": "English Sky Bet League One",
    "england/league-two": "English Sky Bet League Two",
    "england/fa-cup": "English FA Cup",
    "spain/laliga2": "Spanish La Liga 2",
    "germany/2-bundesliga": "German 2. Bundesliga",
    "italy/serie-b": "Italian Serie B",
    "france/ligue-2": "French Ligue 2",
    "argentina/liga-profesional": "Argentine Liga Profesional",
    "brazil/serie-a": "Brazilian Serie A",
    "mexico/liga-mx": "Mexican Liga MX",
    "usa/mls": "American Major League Soccer",
    "saudi-arabia/saudi-pro-league": "Saudi Pro League",
}

TEAM_ALIASES = {
    "man city": ["manchester city", "man city"],
    "man utd": ["manchester utd", "manchester united", "man utd"],
    "newcastle": ["newcastle utd", "newcastle united", "newcastle"],
    "wolves": ["wolverhampton", "wolves"],
    "spurs": ["tottenham", "spurs"],
    "nottm forest": ["nottingham forest", "nottm forest", "nottm fores"],
    "sheff utd": ["sheffield utd", "sheffield united", "sheff utd"],
    "sheff wed": ["sheffield wed", "sheffield wednesday", "sheff wed"],
    "west ham": ["west ham utd", "west ham united", "west ham"],
    "west brom": ["west brom", "west bromwich"],
    "oxford utd": ["oxford utd", "oxford united", "oxford"],
    "qpr": ["qpr", "queens park rangers"],
    "paris st-g": ["psg", "paris saint-germain", "paris st-g", "paris sg"],
    "atletico ma": ["atletico madrid", "atletico ma", "atl. madrid", "atl madrid"],
    "real betis": ["real betis", "betis"],
    "real madrid": ["real madrid"],
    "barcelona": ["barcelona", "fc barcelona"],
    "bayern": ["bayern munich", "bayern munchen", "bayern"],
    "leverkusen": ["bayer leverkusen", "leverkusen"],
    "dortmund": ["borussia dortmund", "dortmund"],
    "inter": ["inter milan", "internazionale", "inter"],
    "ac milan": ["ac milan", "milan"],
    "napoli": ["napoli", "ssc napoli"],
    "juventus": ["juventus"],
    "lazio": ["lazio", "ss lazio"],
    "roma": ["roma", "as roma"],
    "lyon": ["lyon", "olympique lyon"],
    "marseille": ["marseille", "olympique marseille"],
    "galatasaray": ["galatasaray"],
    "fenerbahce": ["fenerbahce"],
    "besiktas": ["besiktas"],
    "trabzonspor": ["trabzonspor"],
    "bodo glimt": ["bodo glimt", "bodo/glimt", "bodø/glimt"],
    "sporting li": ["sporting cp", "sporting lisbon", "sporting li", "sporting"],
    "porto": ["fc porto", "porto"],
    "benfica": ["benfica", "sl benfica"],
    "ajax": ["ajax", "afc ajax"],
    "stuttgart": ["stuttgart", "vfb stuttgart"],
    "celta vigo": ["celta vigo", "celta de vigo", "rc celta"],
    "bristol cit": ["bristol city", "bristol cit"],
    "middlesbrou": ["middlesbrough", "middlesbrou"],
    "birmingham": ["birmingham", "birmingham city"],
    "coventry": ["coventry", "coventry city"],
    "sunderland": ["sunderland"],
    "aston villa": ["aston villa"],
    "bournemouth": ["bournemouth", "afc bournemouth"],
    "brighton": ["brighton", "brighton & hove"],
    "crystal pala": ["crystal palace", "crystal pala"],
    "everton": ["everton"],
    "fulham": ["fulham"],
    "ipswich": ["ipswich", "ipswich town"],
    "leicester": ["leicester", "leicester city"],
    "southampton": ["southampton"],
    "brentford": ["brentford"],
    "chelsea": ["chelsea"],
    "arsenal": ["arsenal"],
    "liverpool": ["liverpool"],
}


def _normalize_team(name):
    if not name:
        return ""
    return re.sub(r'[^a-z0-9]', '', name.lower().strip())


def _teams_match(store_name, flash_name):
    sn = _normalize_team(store_name)
    fn = _normalize_team(flash_name)
    if not sn or not fn:
        return False
    if sn == fn:
        return True
    if sn in fn or fn in sn:
        return True
    if len(sn) >= 5 and len(fn) >= 5:
        if sn[:5] == fn[:5]:
            return True
    for canonical, aliases in TEAM_ALIASES.items():
        norms = [_normalize_team(a) for a in aliases]
        if sn in norms and fn in norms:
            return True
        if any(sn.startswith(_normalize_team(a)[:5]) for a in aliases) and \
           any(fn.startswith(_normalize_team(a)[:5]) for a in aliases):
            return True
    return False


def parse_flashscore_markdown(md_text):
    lines = md_text.split('\n')
    lines = [l.strip() for l in lines]
    matches = []

    i = 0
    while i < len(lines):
        time_match = re.match(r'^(\d{2})\.(\d{2})\.\s+(\d{2}:\d{2})$', lines[i])
        if not time_match:
            i += 1
            continue

        day = time_match.group(1)
        month = time_match.group(2)
        time_str = time_match.group(3)

        home = None
        away = None
        score_str = None

        for j in range(i + 1, min(i + 10, len(lines))):
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

        i += 1

    return matches


def fetch_results_from_flashscore():
    all_results = []
    script = os.path.join(os.path.dirname(__file__), '_flashscore_fetch.js')

    for fs_path, local_league in FLASHSCORE_LEAGUES.items():
        url = f"https://www.flashscore.com/football/{fs_path}/results/"
        try:
            result = subprocess.run(
                [sys.executable, '-c', f'''
import json, sys
sys.path.insert(0, "{os.path.dirname(__file__)}")
# Use webFetch via a simple HTTP approach
import urllib.request
req = urllib.request.Request(url="{url}", headers={{"User-Agent": "Mozilla/5.0"}})
# This won't work for JS-rendered pages, we need the markdown fetch
print(json.dumps({{"url": "{url}", "league": "{local_league}"}}))
'''],
                capture_output=True, text=True, timeout=10
            )
        except Exception as e:
            print(f"[ResultFetcher] Error for {fs_path}: {e}")

    return all_results


def update_store_results(store_path, results_by_league):
    from smartxflow_similarity.feature_store import load_store, save_store

    entries = load_store(store_path)
    if not entries:
        return 0

    updated = 0
    for entry in entries:
        if entry.get("result"):
            continue

        store_home = entry.get("match_name", "").split(" vs ")[0].strip() if " vs " in entry.get("match_name", "") else ""
        store_away = entry.get("match_name", "").split(" vs ")[1].strip() if " vs " in entry.get("match_name", "") else ""
        kickoff = entry.get("kickoff", "")
        if not kickoff or not store_home:
            continue

        kick_day = kickoff[8:10] if len(kickoff) >= 10 else ""
        kick_month = kickoff[5:7] if len(kickoff) >= 7 else ""

        for league_name, matches in results_by_league.items():
            for m in matches:
                if m["date_day"] == kick_day and m["date_month"] == kick_month:
                    if _teams_match(store_home, m["home"]) and _teams_match(store_away, m["away"]):
                        entry["result"] = m["result"]
                        entry["score"] = m["score"]
                        updated += 1
                        break
                    elif _teams_match(store_home, m["away"]) and _teams_match(store_away, m["home"]):
                        rev = {"HOME": "AWAY", "AWAY": "HOME", "DRAW": "DRAW"}
                        entry["result"] = rev.get(m["result"], m["result"])
                        entry["score"] = f"{m['away_goals']}-{m['home_goals']}"
                        updated += 1
                        break

    save_store(entries, store_path)
    return updated
