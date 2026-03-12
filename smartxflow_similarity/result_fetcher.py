import re
import json
import os


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


def _normalize_team(name):
    if not name:
        return ""
    n = name.lower().strip()
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


def update_store_results(store_path, results_by_league=None):
    from smartxflow_similarity.feature_store import load_store, save_store

    if results_by_league is None:
        results_by_league = load_cached_results()

    all_results = []
    for league, matches in results_by_league.items():
        for m in matches:
            all_results.append(m)

    if not all_results:
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

        for m in all_results:
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
