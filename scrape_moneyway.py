#!/usr/bin/env python3
import sys
import os
import re
from typing import Dict, List, Optional
import argparse
import pandas as pd
import sqlite3
# Configure stdout/stderr to UTF-8 to prevent 'charmap' encoding errors on Windows terminals
try:
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')
except Exception:
    pass

import matplotlib.pyplot as plt

import requests
from bs4 import BeautifulSoup
import datetime as dt


VERBOSE = True

def vprint(*args, **kwargs):
    if VERBOSE:
        print(*args, **kwargs)


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
            "1", "X", "2",
            "Away", "Volume",
        ],
    ),
    "dropping-ou25": (
        "extract_dropping_ou25",
        [
            "League", "Date", "Home",
            "Under", "Astar", "Over",
            "Away", "Volume",
        ],
    ),
    "dropping-btts": (
        "extract_dropping_btts",
        [
            "League", "Date", "Home",
            "Yes", "No",
            "Away", "Volume",
        ],
    ),
}
# Kullanıcının verdiği cookie stringini aynen kullanıyoruz
COOKIE_STRING = (
    "FCNEC=%5B%5B%22AKsRol_FbFM4-_5I284lzPHjFMSw_YMHo0DSgfdxUcJQS95GehnQ1B6F64_zWYBRFYEdKl7vdwPsFC6744U1tEKvMGecBWZvCEIZ0Xl3UhpSrpFwgipij-oiPExlDTLy0zOT4dOa_qXRXFx5OJJwnint5afnjqgHqA%3D%3D%22%5D%5D; "
    "FCCDCF=%5Bnull%2Cnull%2Cnull%2Cnull%2Cnull%2Cnull%2C%5B%5B32%2C%22%5B%5C%22b1888239-b3f2-4150-b8f4-60bbac8089fb%5C%22%2C%5B1762615634%2C569000000%5D%5D%22%5D%5D%5D; "
    "clever-counter-51036=0-1; PHPSESSID=b5326321ec0650ca9c1433f9a640dddd"
)


def parse_cookie_string(cookie_str: str) -> Dict[str, str]:
    cookies: Dict[str, str] = {}
    for part in cookie_str.split(";"):
        part = part.strip()
        if not part:
            continue
        if "=" in part:
            k, v = part.split("=", 1)
            cookies[k.strip()] = v.strip()
    vprint(f"[cookies] parsed {len(cookies)} cookies: {', '.join(cookies.keys())}")
    return cookies


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


def clean_table(table: BeautifulSoup) -> BeautifulSoup:
    # Geçersiz style değerlerini (örn: "background:" boş) kaldır
    removed = 0
    for tag in table.find_all(True):
        style = tag.get("style")
        if style:
            s = style.strip()
            low = s.lower()
            if low == "background:" or low.endswith("background:") or low == "background: ":
                del tag["style"]
                removed += 1
    vprint(f"[clean_table] removed invalid 'background:' style entries: {removed}")
    return table


def fetch_table(url: str) -> BeautifulSoup:
    cookies = parse_cookie_string(COOKIE_STRING)
    vprint(f"[fetch] GET {url}")
    resp = requests.get(url, headers=HEADERS, cookies=cookies, timeout=30)
    vprint(f"[fetch] status={resp.status_code} html_length={len(resp.text)}")
    resp.raise_for_status()
    html = resp.text
    soup = BeautifulSoup(html, "html.parser")
    table = soup.select_one("table#matches.table_matches")
    if not table:
        table = soup.find("table", id="matches") or soup.find("table", class_="table_matches")
    if not table:
        raise RuntimeError('Hedef tablo bulunamadı (id="matches" class="table_matches").')
    vprint("[fetch] table found")
    table = clean_table(table)
    return table


def _text(node: Optional[BeautifulSoup]) -> str:
    return node.get_text(strip=True) if node else ""


def _hidden_date(tr) -> Optional[str]:
    for td in tr.find_all("td"):
        style = td.get("style", "")
        if "display:none" in style.replace(" ",""):
            # <br>leri boşlukla birleştir
            return " ".join(list(td.stripped_strings))
    return None


def _parse_pct_amt_cell(td) -> (str, str):
    # Örn: "99.3 % £ 600" → ("99.3%", "£ 600")
    joined = " ".join(list(td.stripped_strings))
    m_pct = re.search(r"(\d+(?:\.\d+)?)\s*%", joined)
    pct = f"{m_pct.group(1)}%" if m_pct else ""
    m_amt = re.search(r"£\s*([\d\s]+)", joined)
    amt = f"£ {m_amt.group(1).strip()}" if m_amt else ""
    return pct, amt


def extract_moneyway_1x2(table: BeautifulSoup) -> List[Dict[str, str]]:
    rows: List[Dict[str, str]] = []
    for tr in table.select("tbody tr"):
        # Sadece veri satırlarını hedefleyelim
        league = _text(tr.select_one("td.tleague"))
        if not league:
            # Header veya geçersiz satır
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

        # Chart ve Bet linkleri
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
    vprint(f"[extract_moneyway_1x2] extracted rows: {len(rows)}")
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
        # Beklenen: [Under, Line, Over]
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
    vprint(f"[extract_moneyway_ou25] extracted rows: {len(rows)}")
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

        # Küçük hücrelerde Yes/No oranları
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        yes = small[0] if len(small) > 0 else ""
        no = small[1] if len(small) > 1 else ""

        # Yüzde ve miktar hücreleri
        pct_cells = tr.select("td.odds_col")
        pct_yes, amt_yes = ("", "")
        pct_no, amt_no = ("", "")
        if len(pct_cells) > 0:
            pct_yes, amt_yes = _parse_pct_amt_cell(pct_cells[0])
        if len(pct_cells) > 1:
            pct_no, amt_no = _parse_pct_amt_cell(pct_cells[1])

        # Chart ve Bet linkleri
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
    vprint(f"[extract_moneyway_btts] extracted rows: {len(rows)}")
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

        # Küçük hücrelerden (fallback) başlangıç ve güncel değerleri al
        small = [td.get_text(strip=True) for td in tr.select("td.odds_col_small")]
        vprint(f"[dropping-1x2] row_id={row_id} small fallback={small}")
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
                    # Ek güvenlik: <br> bazlı böl ve tekrar dene
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
            vprint(f"[dropping-1x2] two_line_text raw='{raw if td else ''}' nums={nums_all if td else []} parts={parts if td else []} -> start='{start}' cur='{cur}' txt='{txt}'")
            return txt, start, cur

        text1, s1, c1 = two_line_text(ocells[0] if len(ocells) > 0 else None, s1_f, c1_f)
        textx, sx, cx = two_line_text(ocells[1] if len(ocells) > 1 else None, sx_f, cx_f)
        text2, s2, c2 = two_line_text(ocells[2] if len(ocells) > 2 else None, s2_f, c2_f)
        vprint(f"[dropping-1x2] row_id={row_id} parsed cells -> 1='{text1}' (start={s1}, cur={c1}), X='{textx}' (start={sx}, cur={cx}), 2='{text2}' (start={s2}, cur={c2})")

        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            # Başlangıç/Güncel değerleri ayrıca tut (DB'de zorunlu değil)
            "Odds1_start": s1,
            "Odds1_cur": c1,
            "OddsX_start": sx,
            "OddsX_cur": cx,
            "Odds2_start": s2,
            "Odds2_cur": c2,
            # Ana sütunlarda iki satır halinde metin
            "1": text1,
            "X": textx,
            "2": text2,
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
        vprint(f"[dropping-ou25] row_id={row_id} small fallback={small}")
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
            vprint(f"[dropping-ou25] two_line_text raw='{raw if td else ''}' nums={nums_all if td else []} parts={parts if td else []} -> start='{start}' cur='{cur}' txt='{txt}'")
            return txt, start, cur

        under_text, under_start, under_cur = two_line_text(ocells[0] if len(ocells) > 0 else None, under_start_fb, under_cur_fb)
        over_text, over_start, over_cur = two_line_text(ocells[2] if len(ocells) > 2 else None, over_start_fb, over_cur_fb)
        vprint(f"[dropping-ou25] row_id={row_id} parsed cells -> Under='{under_text}' (start={under_start}, cur={under_cur}), Over='{over_text}' (start={over_start}, cur={over_cur})")

        # 'Astar' hücresini yakala (sitelerde Line yerine görünebilir)
        astar = ""
        if len(ocells) > 1:
            joined = " ".join(list(ocells[1].stripped_strings))
            astar = joined.strip()
        if not astar:
            astar = astar_fb

        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            "Under_start": under_start,
            "Under_cur": under_cur,
            "Astar": astar,
            "Over_start": over_start,
            "Over_cur": over_cur,
            # Ana sütunlarda iki satır halinde metin
            "Under": under_text,
            "Over": over_text,
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
        vprint(f"[dropping-btts] row_id={row_id} small fallback={small}")
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
            vprint(f"[dropping-btts] two_line_text raw='{raw if td else ''}' nums={nums_all if td else []} parts={parts if td else []} -> start='{start}' cur='{cur}' txt='{txt}'")
            return txt, start, cur

        yes_text, yes_start, yes_cur = two_line_text(ocells[0] if len(ocells) > 0 else None, yes_start_fb, yes_cur_fb)
        no_text, no_start, no_cur = two_line_text(ocells[1] if len(ocells) > 1 else None, no_start_fb, no_cur_fb)

        rows.append({
            "ID": row_id,
            "Flag": flag,
            "League": league,
            "Date": date,
            "Home": home,
            "Yes_start": yes_start,
            "Yes_cur": yes_cur,
            "No_start": no_start,
            "No_cur": no_cur,
            # Ana sütunlarda iki satır halinde metin
            "Yes": yes_text,
            "No": no_text,
            "Away": away,
            "Volume": volume,
        })
    return rows


def print_tsv(records: List[Dict[str, str]], headers: List[str]) -> None:
    vprint(f"[tsv] headers={headers} rows={len(records)}")
    # Başlık
    print("\t".join(headers))
    for r in records:
        row = [r.get(h, "") for h in headers]
        print("\t".join(row))


def create_matplotlib_table(records: List[Dict[str, str]], headers: List[str], limit: int, save_path: str) -> str:

    rows = records[:limit]
    vprint(f"[matplotlib] building table rows={len(rows)} headers={len(headers)} save_path={save_path}")
    cell_text = [[r.get(h, "") for h in headers] for r in rows]

    # Dinamik boyut: satır sayısına göre fig yüksekliğini ayarla
    fig_width = 14
    fig_height = max(4, 0.4 * (len(rows) + 1))
    fig, ax = plt.subplots(figsize=(fig_width, fig_height))
    ax.axis('off')

    table = ax.table(cellText=cell_text, colLabels=headers, loc='center')
    table.auto_set_font_size(False)
    table.set_fontsize(9)
    table.scale(1, 1.2)

    plt.tight_layout()
    fig.savefig(save_path, dpi=200, bbox_inches='tight')
    plt.close(fig)
    vprint(f"[matplotlib] image saved: {save_path}")
    return save_path


def create_excel_table(records: List[Dict[str, str]], headers: List[str], save_path: str) -> str:
    vprint(f"[excel] writing {len(records)} rows to {save_path}")
    rows = [[r.get(h, "") for h in headers] for r in records]
    df = pd.DataFrame(rows, columns=headers)
    df.to_excel(save_path, index=False)
    vprint(f"[excel] saved: {save_path}")
    return save_path

# --- SQLite yardımcıları ---

def _quote_ident(name: str) -> str:
    return '"' + name.replace('"', '""') + '"'


def _sanitize_table_name(name: str) -> str:
    # Kaynak anahtarını tablo adına dönüştür: '-' → '_', boşlukları temizle
    t = re.sub(r"[^0-9A-Za-z_]+", "_", name.replace("-", "_"))
    # SQLite için güvenli: harfle başlamıyorsa önek ekle
    if not re.match(r"^[A-Za-z]", t):
        t = "t_" + t
    return t


def save_records_to_sqlite(records: List[Dict[str, str]], headers: List[str], table_name: str, db_path: str) -> str:
    if not records:
        return db_path
    vprint(f"[sqlite] connect db={db_path} table={table_name} headers={len(headers)} rows={len(records)}")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Mevcut tablo şemasını kontrol et, başlıklar değişmişse tabloyu yeniden oluştur
        existing_cols: List[str] = []
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        tbl = cur.fetchone()
        if tbl:
            cur.execute(f"PRAGMA table_info({_quote_ident(table_name)})")
            info = cur.fetchall()
            existing_cols = [row[1] for row in info]
            if existing_cols != headers:
                vprint(f"[sqlite] schema mismatch for '{table_name}': existing={existing_cols} new={headers} -> recreating table")
                cur.execute(f"DROP TABLE {_quote_ident(table_name)}")
        # Yeni tabloyu oluştur
        cols_def = ", ".join(f"{_quote_ident(h)} TEXT" for h in headers)
        cur.execute(f"CREATE TABLE IF NOT EXISTS {_quote_ident(table_name)} ({cols_def})")
        # Tablodaki verileri tazele (Excel ile eş içerik)
        cur.execute(f"DELETE FROM {_quote_ident(table_name)}")
        cols = ", ".join(_quote_ident(h) for h in headers)
        placeholders = ", ".join(["?"] * len(headers))
        insert_sql = f"INSERT INTO {_quote_ident(table_name)} ({cols}) VALUES ({placeholders})"
        rows = [[r.get(h, "") for h in headers] for r in records]
        cur.executemany(insert_sql, rows)
        conn.commit()
        vprint("[sqlite] commit completed")
        return db_path
    finally:
        conn.close()


def save_records_to_sqlite_append(records: List[Dict[str, str]], headers: List[str], table_name: str, db_path: str) -> str:
    """Geçmiş tutmak için ekleme (append) modunda yaz.
    - Tablo şeması headers + ScrapedAt şeklinde olmalı
    - Varolan veriler silinmez, her scrape yeni satır olarak eklenir
    """
    if not records:
        return db_path
    # History tablosu için kolonlara ScrapedAt ekle
    hist_headers = headers + ["ScrapedAt"]
    vprint(f"[sqlite:hist] connect db={db_path} table={table_name} headers={len(hist_headers)} rows={len(records)}")
    conn = sqlite3.connect(db_path)
    try:
        cur = conn.cursor()
        # Şemayı doğrula
        cur.execute("SELECT name FROM sqlite_master WHERE type='table' AND name=?", (table_name,))
        tbl = cur.fetchone()
        if tbl:
            cur.execute(f"PRAGMA table_info({_quote_ident(table_name)})")
            info = cur.fetchall()
            existing_cols = [row[1] for row in info]
            if existing_cols != hist_headers:
                vprint(f"[sqlite:hist] schema mismatch for '{table_name}': existing={existing_cols} new={hist_headers} -> recreating table")
                cur.execute(f"DROP TABLE {_quote_ident(table_name)}")
        # Oluştur
        cols_def = ", ".join(f"{_quote_ident(h)} TEXT" for h in hist_headers)
        cur.execute(f"CREATE TABLE IF NOT EXISTS {_quote_ident(table_name)} ({cols_def})")
        # Ekle
        cols = ", ".join(_quote_ident(h) for h in hist_headers)
        placeholders = ", ".join(["?"] * len(hist_headers))
        insert_sql = f"INSERT INTO {_quote_ident(table_name)} ({cols}) VALUES ({placeholders})"
        # ScrapedAt'i şimdi zaman damgası olarak ekle
        scraped_at = dt.datetime.now().isoformat(timespec='seconds')
        rows = [[r.get(h, "") for h in headers] + [scraped_at] for r in records]
        cur.executemany(insert_sql, rows)
        conn.commit()
        vprint("[sqlite:hist] commit completed")
        return db_path
    finally:
        conn.close()


def main() -> None:
    global VERBOSE
    parser = argparse.ArgumentParser(description="Tüm dataset'leri çek ve her biri için Excel üret")
    parser.add_argument("--output-dir", type=str, default=".", help="Excel dosyalarının kaydedileceği klasör")
    parser.add_argument("--verbose", action="store_true", default=True, help="Detaylı debug çıktıları")
    args = parser.parse_args()

    VERBOSE = args.verbose
    vprint(f"[main] output_dir={args.output_dir} verbose={args.verbose}")

    for dataset_key, url in DATASETS.items():
        vprint(f"[main] Fetching dataset='{dataset_key}' url={url}")
        try:
            table = fetch_table(url)
            vprint(f"[main] Table fetched for '{dataset_key}'")
        except Exception as e:
            print(f"Hata ({dataset_key}): {e}", file=sys.stderr)
            continue

        extractor_name, headers = EXTRACTOR_MAP[dataset_key]
        extractor = globals().get(extractor_name)
        if not callable(extractor):
            print(f"Hata ({dataset_key}): extractor bulunamadı: {extractor_name}", file=sys.stderr)
            continue
        records = extractor(table)
        vprint(f"[main] Extracted {len(records)} records for '{dataset_key}'")
        # dropping dataset'leri için başlıkları sitenin gördüğü isimlerle doldur
        if dataset_key == "dropping-1x2":
            for r in records:
                r["1"] = "\n".join([x for x in [r.get("Odds1_start", ""), r.get("Odds1_cur", "")] if x])
                r["X"] = "\n".join([x for x in [r.get("OddsX_start", ""), r.get("OddsX_cur", "")] if x])
                r["2"] = "\n".join([x for x in [r.get("Odds2_start", ""), r.get("Odds2_cur", "")] if x])
            vprint(f"[main] dropping-1x2 cells normalized to 'start\\ncur' format")
        elif dataset_key == "dropping-ou25":
            for r in records:
                r["Under"] = "\n".join([x for x in [r.get("Under_start", ""), r.get("Under_cur", "")] if x])
                r["Over"]  = "\n".join([x for x in [r.get("Over_start", ""),  r.get("Over_cur", "")] if x])
            vprint(f"[main] dropping-ou25 cells normalized to 'start\\ncur' format")
            # Over sütununu doğrulama amaçlı yazdır
            for r in records[:50]:
                print(f"[dropping-ou25] Over='{r.get('Over','')}' (start={r.get('Over_start','')}, cur={r.get('Over_cur','')})")
        elif dataset_key == "dropping-btts":
            for r in records:
                r["Yes"] = "\n".join([x for x in [r.get("Yes_start", ""), r.get("Yes_cur", "")] if x])
                r["No"]  = "\n".join([x for x in [r.get("No_start", ""),  r.get("No_cur", "")] if x])
            vprint(f"[main] dropping-btts cells normalized to 'start\\ncur' format")
        if not records:
            print(f"Uyarı ({dataset_key}): Kayıt bulunamadı.", file=sys.stderr)
            continue

        out_path = os.path.join(args.output_dir, f"{dataset_key}.xlsx")
        try:
            saved = create_excel_table(records, headers, out_path)
            print(f"Excel kaydedildi: {saved}")
        except Exception as e:
            print(f"Hata ({dataset_key}) Excel kaydedilirken: {e}", file=sys.stderr)

        # SQLite'e kaydet (her kaynak için ayrı tablo)
        try:
            db_path = os.path.join(args.output_dir, "moneyway.db")
            table_name = _sanitize_table_name(dataset_key)
            vprint(f"[sqlite] Writing {len(records)} rows to table='{table_name}' db='{db_path}' headers={headers}")
            saved_db = save_records_to_sqlite(records, headers, table_name, db_path)
            print(f"SQLite'e yazıldı: {saved_db} -> tablo: {table_name}")
            # Geçmiş tablosuna da ekle
            hist_table = f"{table_name}_hist"
            save_records_to_sqlite_append(records, headers, hist_table, db_path)
            print(f"SQLite (history) eklendi: {db_path} -> tablo: {hist_table}")
        except Exception as e:
            print(f"Hata ({dataset_key}) SQLite yazılırken: {e}", file=sys.stderr)


if __name__ == "__main__":
    main()