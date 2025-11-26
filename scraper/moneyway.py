import os
import re
from typing import Dict, List, Optional, Callable
import requests
from bs4 import BeautifulSoup
import pandas as pd
import sqlite3
import datetime as dt
from core.storage import get_storage

VERBOSE_DEFAULT = True

def _vset(verbose: bool):
    def vprint(*args, **kwargs):
        if verbose:
            print(*args, **kwargs)
    return vprint

DATASETS = {
    "moneyway-1x2": "https://arbworld.net/en/moneyway/football-1-x-2",
    "moneyway-ou25": "https://arbworld.net/en/moneyway/football-over-under-2-5",
    "moneyway-btts": "https://arbworld.net/en/moneyway/football-both-teams-to-score",
    "dropping-1x2": "https://arbworld.net/en/dropping-odds/football-1-x-2",
    "dropping-ou25": "https://arbworld.net/en/dropping-odds/football-over-under-2-5",
    "dropping-btts": "https://arbworld.net/en/dropping-odds/football-both-teams-to-score",
}

EXTRACTOR_MAP = {
    "moneyway-1x2": (
        "extract_moneyway_1x2",
        [
            "League", "Date", "Home",
            "Odds1", "OddsX", "Odds2",
            "Pct1", "Amt1", "PctX", "AmtX", "Pct2", "Amt2",
            "Away", "Volume",
        ],
    ),
    "moneyway-ou25": (
        "extract_moneyway_ou25",
        [
            "League", "Date", "Home",
            "Under", "Line", "Over",
            "PctUnder", "AmtUnder", "PctOver", "AmtOver",
            "Away", "Volume",
        ],
    ),
    "moneyway-btts": (
        "extract_moneyway_btts",
        [
            "League", "Date", "Home",
            "Yes", "No",
            "PctYes", "AmtYes", "PctNo", "AmtNo",
            "Away", "Volume",
        ],
    ),
    "dropping-1x2": (
        "extract_dropping_1x2",
        [
            "League", "Date", "Home",
            "Odds1", "Odds1_prev", "OddsX", "OddsX_prev", "Odds2", "Odds2_prev",
            "Trend1", "TrendX", "Trend2",
            "Away", "Volume",
        ],
    ),
    "dropping-ou25": (
        "extract_dropping_ou25",
        [
            "League", "Date", "Home",
            "Under", "Under_prev", "Line", "Over", "Over_prev",
            "TrendUnder", "TrendOver",
            "PctUnder", "AmtUnder", "PctOver", "AmtOver",
            "Away", "Volume",
        ],
    ),
    "dropping-btts": (
        "extract_dropping_btts",
        [
            "League", "Date", "Home",
            "OddsYes", "OddsYes_prev", "OddsNo", "OddsNo_prev",
            "TrendYes", "TrendNo",
            "PctYes", "AmtYes", "PctNo", "AmtNo",
            "Away", "Volume",
        ],
    ),
}

HEADERS = {
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Sec-Fetch-Site": "none",
    "Sec-Fetch-Dest": "document",
    "Sec-Fetch-Mode": "navigate",
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15 (KHTML, like Gecko) Version/26.0.1 Safari/605.1.15",
    "Accept-Language": "tr-TR,tr;q=0.9",
    "Accept-Encoding": "gzip, deflate, br",
    "Connection": "keep-alive",
    "Priority": "u=0, i",
}

def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    return cookies

def clean_table(table: BeautifulSoup) -> BeautifulSoup:
    for tag in table.find_all(True):
        style = tag.get("style")
        if style:
            s = style.strip().lower()
            if s == "background:" or s.endswith("background:") or s == "background: ":
                del tag["style"]
    return table

def fetch_table(url: str, session: Optional[requests.Session] = None, headers: Optional[Dict[str, str]] = None, timeout: int = 30) -> BeautifulSoup:
    sess = session or requests.Session()
    h = headers or HEADERS
    resp = sess.get(url, headers=h, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    table = soup.select_one("table#matches.table_matches")
    if not table:
        table = soup.find("table", id="matches") or soup.find("table", class_="table_matches")
    if not table:
        raise RuntimeError("Hedef tablo bulunamadı")
    return clean_table(table)

def _text(node: Optional[BeautifulSoup]) -> str:
    return node.get_text(strip=True) if node else ""

def _hidden_date(tr) -> Optional[str]:
    for td in tr.find_all("td"):
        style = td.get("style", "")
        if "display:none" in style.replace(" ", ""):
            return " ".join(list(td.stripped_strings))
    return None

def _parse_pct_amt_cell(td) -> (str, str):
    joined = " ".join(list(td.stripped_strings))
    m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", joined)
    pct = f"{m_pct.group(1)}%" if m_pct else ""
    m_amt = re.search(r"£\s*([\d\s]+)", joined)
    amt = f"£ {m_amt.group(1).strip()}" if m_amt else ""
    return pct, amt

def extract_moneyway_1x2(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        flag_img = tr.select_one("td.tflag img")
        flag = ""
        if flag_img:
            flag = flag_img.get("alt") or flag_img.get("title") or ""
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        odds_small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")][:3]
        while len(odds_small) < 3:
            odds_small.append("")
        pct_cells = tr.select("td.odds_col")[:3]
        pct_amt_values = [_parse_pct_amt_cell(td) for td in pct_cells]
        while len(pct_amt_values) < 3:
            pct_amt_values.append(("", ""))
        chart_url = ""
        bet_url = ""
        tbet_td = tr.select_one("td.tbet")
        if tbet_td:
            a_tags = tbet_td.select("a")
            for a in a_tags:
                href = a.get("href", "")
                if "graphs.betfair.com" in href:
                    chart_url = href
                elif "betfair.com/exchange/plus/football/market" in href:
                    bet_url = href
        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            "Odds1": odds_small[0],
            "OddsX": odds_small[1],
            "Odds2": odds_small[2],
            "Pct1": pct_amt_values[0][0],
            "Amt1": pct_amt_values[0][1],
            "PctX": pct_amt_values[1][0],
            "AmtX": pct_amt_values[1][1],
            "Pct2": pct_amt_values[2][0],
            "Amt2": pct_amt_values[2][1],
            "Away": away,
            "Volume": volume,
            "ChartURL": chart_url,
            "BetURL": bet_url,
        })
    return rows

def extract_moneyway_ou25(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        flag_img = tr.select_one("td.tflag img")
        flag = flag_img.get("alt") or flag_img.get("title") or "" if flag_img else ""
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        under = small[0] if len(small) > 0 else ""
        line = small[1] if len(small) > 1 else ""
        over = small[2] if len(small) > 2 else ""
        pct_cells = tr.select("td.odds_col")
        pct_under, amt_under = ("", "")
        pct_over, amt_over = ("", "")
        if len(pct_cells) > 0:
            pct_under, amt_under = _parse_pct_amt_cell(pct_cells[0])
        if len(pct_cells) > 1:
            pct_over, amt_over = _parse_pct_amt_cell(pct_cells[1])
        chart_url = ""
        bet_url = ""
        tbet_td = tr.select_one("td.tbet")
        if tbet_td:
            for a in tbet_td.select("a"):
                href = a.get("href", "")
                if "graphs.betfair.com" in href:
                    chart_url = href
                elif "betfair.com/exchange/plus/football/market" in href:
                    bet_url = href
        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            "Under": under,
            "Line": line,
            "Over": over,
            "PctUnder": pct_under,
            "AmtUnder": amt_under,
            "PctOver": pct_over,
            "AmtOver": amt_over,
            "Away": away,
            "Volume": volume,
            "ChartURL": chart_url,
            "BetURL": bet_url,
        })
    return rows

def extract_moneyway_btts(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        flag_img = tr.select_one("td.tflag img")
        flag = flag_img.get("alt") or flag_img.get("title") or "" if flag_img else ""
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        yes = small[0] if len(small) > 0 else ""
        no = small[1] if len(small) > 1 else ""
        pct_cells = tr.select("td.odds_col")
        pct_yes, amt_yes = ("", "")
        pct_no, amt_no = ("", "")
        if len(pct_cells) > 0:
            pct_yes, amt_yes = _parse_pct_amt_cell(pct_cells[0])
        if len(pct_cells) > 1:
            pct_no, amt_no = _parse_pct_amt_cell(pct_cells[1])
        chart_url = ""
        bet_url = ""
        tbet_td = tr.select_one("td.tbet")
        if tbet_td:
            for a in tbet_td.select("a"):
                href = a.get("href", "")
                if "graphs.betfair.com" in href:
                    chart_url = href
                elif "betfair.com/exchange/plus/football/market" in href:
                    bet_url = href
        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            "Yes": yes,
            "No": no,
            "PctYes": pct_yes,
            "AmtYes": amt_yes,
            "PctNo": pct_no,
            "AmtNo": amt_no,
            "Away": away,
            "Volume": volume,
            "ChartURL": chart_url,
            "BetURL": bet_url,
        })
    return rows

def extract_dropping_1x2(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        flag_img = tr.select_one("td.tflag img")
        flag = flag_img.get("alt") or flag_img.get("title") or "" if flag_img else ""
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        def g(i):
            return small[i] if len(small) > i else ""
        s1_f, c1_f, sx_f, cx_f, s2_f, c2_f = g(0), g(1), g(2), g(3), g(4), g(5)
        ocells = tr.select("td.odds_col")
        def two_line_text(td, start_fb, cur_fb):
            if td:
                raw = td.get_text(separator="\n", strip=True)
                nums_all = re.findall(r"\d+(?:\.\d+)?", raw)
                parts = [p.strip() for p in raw.split("\n") if p.strip()]
                if len(nums_all) >= 2:
                    start, cur = nums_all[0], nums_all[-1]
                elif len(nums_all) == 1:
                    n = nums_all[0]
                    start, cur = (start_fb or n), n
                else:
                    def first_num(s):
                        m = re.search(r"\d+(?:\.\d+)?", s)
                        return m.group(0) if m else ""
                    if len(parts) >= 2:
                        start, cur = first_num(parts[0]), first_num(parts[-1])
                    elif len(parts) == 1:
                        n = first_num(parts[0])
                        start, cur = (start_fb or n), n
                    else:
                        start, cur = start_fb, cur_fb
            else:
                start, cur = start_fb, cur_fb
            txt = "\n".join([n for n in [start, cur] if n])
            return txt, start, cur
        text1, s1, c1 = two_line_text(ocells[0] if len(ocells) > 0 else None, s1_f, c1_f)
        textx, sx, cx = two_line_text(ocells[1] if len(ocells) > 1 else None, sx_f, cx_f)
        text2, s2, c2 = two_line_text(ocells[2] if len(ocells) > 2 else None, s2_f, c2_f)
        def calc_trend(cur, prev):
            try:
                c = float(cur) if cur else 0
                p = float(prev) if prev else 0
                if abs(c - p) < 0.001:
                    return ""
                return "↑" if c > p else "↓"
            except:
                return ""
        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            "Odds1": c1,
            "Odds1_prev": s1,
            "OddsX": cx,
            "OddsX_prev": sx,
            "Odds2": c2,
            "Odds2_prev": s2,
            "Trend1": calc_trend(c1, s1),
            "TrendX": calc_trend(cx, sx),
            "Trend2": calc_trend(c2, s2),
            "Away": away,
            "Volume": volume,
        })
    return rows

def extract_dropping_ou25(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        flag_img = tr.select_one("td.tflag img")
        flag = flag_img.get("alt") or flag_img.get("title") or "" if flag_img else ""
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        def g(i):
            return small[i] if len(small) > i else ""
        under_start_fb, under_cur_fb, over_start_fb, over_cur_fb = g(0), g(1), g(3), g(4)
        astar_fb = g(2)
        ocells = tr.select("td.odds_col")
        def two_line_text(td, start_fb, cur_fb):
            if td:
                raw = td.get_text(separator="\n", strip=True)
                nums_all = re.findall(r"\d+(?:\.\d+)?", raw)
                parts = [p.strip() for p in raw.split("\n") if p.strip()]
                if len(nums_all) >= 2:
                    start, cur = nums_all[0], nums_all[-1]
                elif len(nums_all) == 1:
                    n = nums_all[0]
                    start, cur = (start_fb or n), n
                else:
                    def first_num(s):
                        m = re.search(r"\d+(?:\.\d+)?", s)
                        return m.group(0) if m else ""
                    if len(parts) >= 2:
                        start, cur = first_num(parts[0]), first_num(parts[-1])
                    elif len(parts) == 1:
                        n = first_num(parts[0])
                        start, cur = (start_fb or n), n
                    else:
                        start, cur = start_fb, cur_fb
            else:
                start, cur = start_fb, cur_fb
            txt = "\n".join([n for n in [start, cur] if n])
            return txt, start, cur
        under_text, under_start, under_cur = two_line_text(ocells[0] if len(ocells) > 0 else None, under_start_fb, under_cur_fb)
        over_text, over_start, over_cur = two_line_text(ocells[2] if len(ocells) > 2 else None, over_start_fb, over_cur_fb)
        astar = ""
        if len(ocells) > 1:
            joined = " ".join(list(ocells[1].stripped_strings))
            astar = joined.strip()
        if not astar:
            astar = astar_fb
        pct_cells = tr.select("td.tpercent")
        pct_under, amt_under, pct_over, amt_over = "", "", "", ""
        if len(pct_cells) >= 2:
            pct_under, amt_under = _parse_pct_amt_cell(pct_cells[0])
            pct_over, amt_over = _parse_pct_amt_cell(pct_cells[1])
        def calc_trend(cur, prev):
            try:
                c = float(cur) if cur else 0
                p = float(prev) if prev else 0
                if abs(c - p) < 0.001:
                    return ""
                return "↑" if c > p else "↓"
            except:
                return ""
        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            "Under": under_cur,
            "Under_prev": under_start,
            "Line": astar,
            "Over": over_cur,
            "Over_prev": over_start,
            "TrendUnder": calc_trend(under_cur, under_start),
            "TrendOver": calc_trend(over_cur, over_start),
            "PctUnder": pct_under,
            "AmtUnder": amt_under,
            "PctOver": pct_over,
            "AmtOver": amt_over,
            "Away": away,
            "Volume": volume,
        })
    return rows

def extract_dropping_btts(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for tr in table.select("tbody tr"):
        league = _text(tr.select_one("td.tleague"))
        if not league:
            continue
        row_id = tr.get("id", "")
        flag_img = tr.select_one("td.tflag img")
        flag = flag_img.get("alt") or flag_img.get("title") or "" if flag_img else ""
        date = _hidden_date(tr) or _text(tr.select_one("td.tdate"))
        home = _text(tr.select_one("td.thome"))
        away = _text(tr.select_one("td.taway"))
        volume = _text(tr.select_one("td.tvol"))
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        def g(i):
            return small[i] if len(small) > i else ""
        yes_start_fb, yes_cur_fb, no_start_fb, no_cur_fb = g(0), g(1), g(2), g(3)
        ocells = tr.select("td.odds_col")
        def two_line_text(td, start_fb, cur_fb):
            if td:
                raw = td.get_text(separator="\n", strip=True)
                nums_all = re.findall(r"\d+(?:\.\d+)?", raw)
                parts = [p.strip() for p in raw.split("\n") if p.strip()]
                if len(nums_all) >= 2:
                    start, cur = nums_all[0], nums_all[-1]
                elif len(nums_all) == 1:
                    n = nums_all[0]
                    start, cur = (start_fb or n), n
                else:
                    def first_num(s):
                        m = re.search(r"\d+(?:\.\d+)?", s)
                        return m.group(0) if m else ""
                    if len(parts) >= 2:
                        start, cur = first_num(parts[0]), first_num(parts[-1])
                    elif len(parts) == 1:
                        n = first_num(parts[0])
                        start, cur = (start_fb or n), n
                    else:
                        start, cur = start_fb, cur_fb
            else:
                start, cur = start_fb, cur_fb
            txt = "\n".join([n for n in [start, cur] if n])
            return txt, start, cur
        yes_text, yes_start, yes_cur = two_line_text(ocells[0] if len(ocells) > 0 else None, yes_start_fb, yes_cur_fb)
        no_text, no_start, no_cur = two_line_text(ocells[1] if len(ocells) > 1 else None, no_start_fb, no_cur_fb)
        pct_cells = tr.select("td.tpercent")
        pct_yes, amt_yes, pct_no, amt_no = "", "", "", ""
        if len(pct_cells) >= 2:
            pct_yes, amt_yes = _parse_pct_amt_cell(pct_cells[0])
            pct_no, amt_no = _parse_pct_amt_cell(pct_cells[1])
        def calc_trend(cur, prev):
            try:
                c = float(cur) if cur else 0
                p = float(prev) if prev else 0
                if abs(c - p) < 0.001:
                    return ""
                return "↑" if c > p else "↓"
            except:
                return ""
        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            "OddsYes": yes_cur,
            "OddsYes_prev": yes_start,
            "OddsNo": no_cur,
            "OddsNo_prev": no_start,
            "TrendYes": calc_trend(yes_cur, yes_start),
            "TrendNo": calc_trend(no_cur, no_start),
            "PctYes": pct_yes,
            "AmtYes": amt_yes,
            "PctNo": pct_no,
            "AmtNo": amt_no,
            "Away": away,
            "Volume": volume,
        })
    return rows

def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'

def _sanitize_table_name(name: str) -> str:
    t = re.sub(r"[^0-9A-Za-z_]+", "_", name.replace("-", "_"))
    if not re.match(r"^[A-Za-z]", t):
        t = "t_" + t
    return t

def save_records_to_sqlite(records: List[Dict[str, str]], headers: List[str], table_name: str, db_path: str) -> str:
    if not records:
        return db_path
    storage = get_storage(db_path)
    storage.replace_table(table_name, headers, records)
    return db_path

def save_records_to_sqlite_append(records: List[Dict[str, str]], headers: List[str], table_name: str, db_path: str) -> str:
    if not records:
        return db_path
    storage = get_storage(db_path)
    scraped_at = dt.datetime.now().isoformat(timespec='seconds')
    storage.append_history(table_name, headers, records, scraped_at)
    return db_path

def create_excel_table(records: List[Dict[str, str]], headers: List[str], save_path: str) -> str:
    rows = [[r.get(h, "") for h in headers] for r in records]
    df = pd.DataFrame(rows, columns=headers)
    df.to_excel(save_path, index=False)
    return save_path

def scrape_all(output_dir: str, verbose: bool = VERBOSE_DEFAULT, cookie_string: Optional[str] = None, progress_cb: Optional[Callable[[str, int, int], None]] = None) -> Dict[str, object]:
    vprint = _vset(verbose)
    sess = requests.Session()
    if cookie_string:
        try:
            cookies = parse_cookie_string(cookie_string)
            sess.cookies.update(cookies)
        except Exception:
            pass
    total = len(DATASETS)
    results: List[Dict[str, object]] = []
    db_path = os.path.join(output_dir, "moneyway.db")
    for idx, (dataset_key, url) in enumerate(DATASETS.items(), 1):
        if progress_cb:
            progress_cb(f"Fetch {dataset_key}", idx, total)
        table = fetch_table(url, session=sess)
        extractor_name, headers = EXTRACTOR_MAP[dataset_key]
        extractor = globals().get(extractor_name)
        if not callable(extractor):
            raise RuntimeError(f"Extractor not found: {extractor_name}")
        records = extractor(table)
        if progress_cb:
            progress_cb(f"Extract {dataset_key} ({len(records)})", idx, total)
        out_path = os.path.join(output_dir, f"{dataset_key}.xlsx")
        create_excel_table(records, headers, out_path)
        table_name = _sanitize_table_name(dataset_key)
        save_records_to_sqlite(records, headers, table_name, db_path)
        hist_table = f"{table_name}_hist"
        save_records_to_sqlite_append(records, headers, hist_table, db_path)
        results.append({"key": dataset_key, "rows": len(records), "data": records})
        if progress_cb:
            progress_cb(f"Saved {dataset_key}", idx, total)
    return {"results": results, "db_path": db_path}