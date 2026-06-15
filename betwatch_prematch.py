"""
betwatch_prematch.py — Betwatch API v1 prematch scraper (server-side, Replit)
Betwatch /football/prematch endpoint'inden veri çeker, 6 tabloya yazar.
Markets: Match Odds (1X2), Over/Under 2.5 Goals (OU25), Both teams to Score? (BTTS)
"""

import os
import sys
import re
import requests
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "desktop", "scraper_standalone"))
sys.path.insert(0, os.path.join(_ROOT, "scraper_standalone"))

from standalone_scraper import SupabaseWriter, get_turkey_now
from betwatch_client import (
    fetch_prematch,
    normalize_kickoff,
    map_market,
)

try:
    import certifi
    SSL_VERIFY = certifi.where()
except Exception:
    SSL_VERIFY = True


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[BW-Pre {ts}] {msg}", flush=True)


# ── Utility helpers ───────────────────────────────────────────────────────────

def _coef(v) -> str:
    try:
        f = float(v)
        return f"{f:g}" if f > 0 else ""
    except Exception:
        return ""


def _vol_amt(v) -> str:
    try:
        f = float(v)
        if f <= 0:
            return ""
        return f"£ {int(f)}" if f == int(f) else f"£ {f:g}"
    except Exception:
        return ""


def _vol_pct(v: float, total: float) -> str:
    try:
        if total <= 0 or v <= 0:
            return ""
        return f"{(v / total * 100):.1f}%"
    except Exception:
        return ""


def _trend(cur, prev) -> str:
    try:
        c = float(cur) if cur not in (None, "", 0) else 0.0
        p = float(prev) if prev not in (None, "", 0) else 0.0
        if c <= 0 or p <= 0 or abs(c - p) < 0.001:
            return ""
        return "up" if c > p else "down"
    except Exception:
        return ""


def _parse_volume(vol_str: str) -> float:
    if not vol_str:
        return 0.0
    s = str(vol_str).replace("£", "").replace(",", "").strip()
    mult = 1.0
    if s.upper().endswith("M"):
        mult = 1_000_000
        s = s[:-1]
    elif s.upper().endswith("K"):
        mult = 1_000
        s = s[:-1]
    try:
        return float(s.strip()) * mult
    except Exception:
        return 0.0


def _parse_pct(pct_str: str) -> float:
    if not pct_str:
        return 0.0
    try:
        return float(str(pct_str).replace("%", "").strip())
    except Exception:
        return 0.0


def _normalize_hash_field(s: str) -> str:
    import hashlib as _hlib
    if not s:
        return ""
    return re.sub(r"\s+", " ", s.strip().lower())


def make_match_id_hash(home: str, away: str, league: str) -> str:
    import hashlib
    h = _normalize_hash_field(home)
    a = _normalize_hash_field(away)
    l = _normalize_hash_field(league)
    canonical = f"{l}|{h}|{a}"
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()[:12]


# ── Previous odds reader (for dropping trend) ─────────────────────────────────

def _read_prev_dropping(writer: SupabaseWriter, table: str, fields: list) -> dict:
    """Current DB values → dict keyed by (home, away, league, date) for prev-odds comparison."""
    sel = "home,away,league,date," + ",".join(fields)
    try:
        r = requests.get(
            f"{writer._rest_url(table)}?select={sel}",
            headers=writer._headers(),
            timeout=30,
            verify=SSL_VERIFY,
        )
        if r.status_code == 200:
            result = {}
            for row in r.json():
                key = (
                    row.get("home", ""),
                    row.get("away", ""),
                    row.get("league", ""),
                    row.get("date", ""),
                )
                result[key] = {f: row.get(f, "") for f in fields}
            return result
    except Exception as e:
        log(f"  [WARN] {table} prev-odds okunamadı: {e}")
    return {}


# ── Row builders ──────────────────────────────────────────────────────────────

def _build_mw_1x2(home, away, league, date, runners_by_sel) -> dict:
    r1 = runners_by_sel.get("1", {})
    rx = runners_by_sel.get("X", {})
    r2 = runners_by_sel.get("2", {})
    v1 = float(r1.get("volume") or 0)
    vx = float(rx.get("volume") or 0)
    v2 = float(r2.get("volume") or 0)
    total = v1 + vx + v2
    return {
        "league": league, "date": date, "home": home, "away": away,
        "odds1": _coef(r1.get("odd")), "oddsx": _coef(rx.get("odd")), "odds2": _coef(r2.get("odd")),
        "pct1": _vol_pct(v1, total), "amt1": _vol_amt(v1),
        "pctx": _vol_pct(vx, total), "amtx": _vol_amt(vx),
        "pct2": _vol_pct(v2, total), "amt2": _vol_amt(v2),
        "volume": _vol_amt(total),
    }


def _build_mw_ou25(home, away, league, date, runners_by_sel) -> dict:
    ro = runners_by_sel.get("O", {})
    ru = runners_by_sel.get("U", {})
    vo = float(ro.get("volume") or 0)
    vu = float(ru.get("volume") or 0)
    total = vo + vu
    return {
        "league": league, "date": date, "home": home, "away": away,
        "over": _coef(ro.get("odd")), "under": _coef(ru.get("odd")), "line": "2.5",
        "pctover": _vol_pct(vo, total), "amtover": _vol_amt(vo),
        "pctunder": _vol_pct(vu, total), "amtunder": _vol_amt(vu),
        "volume": _vol_amt(total),
    }


def _build_mw_btts(home, away, league, date, runners_by_sel) -> dict:
    ry = runners_by_sel.get("Y", {})
    rn = runners_by_sel.get("N", {})
    vy = float(ry.get("volume") or 0)
    vn = float(rn.get("volume") or 0)
    total = vy + vn
    return {
        "league": league, "date": date, "home": home, "away": away,
        "yes": _coef(ry.get("odd")), "no": _coef(rn.get("odd")),
        "pctyes": _vol_pct(vy, total), "amtyes": _vol_amt(vy),
        "pctno": _vol_pct(vn, total), "amtno": _vol_amt(vn),
        "volume": _vol_amt(total),
    }


def _build_do_1x2(home, away, league, date, runners_by_sel, prev: dict) -> dict:
    r1 = runners_by_sel.get("1", {})
    rx = runners_by_sel.get("X", {})
    r2 = runners_by_sel.get("2", {})
    v1 = float(r1.get("volume") or 0)
    vx = float(rx.get("volume") or 0)
    v2 = float(r2.get("volume") or 0)
    total = v1 + vx + v2
    c1, cx, c2 = _coef(r1.get("odd")), _coef(rx.get("odd")), _coef(r2.get("odd"))
    p1 = prev.get("odds1", "")
    px = prev.get("oddsx", "")
    p2 = prev.get("odds2", "")
    return {
        "league": league, "date": date, "home": home, "away": away,
        "odds1": c1, "odds1_prev": p1,
        "oddsx": cx, "oddsx_prev": px,
        "odds2": c2, "odds2_prev": p2,
        "trend1": _trend(c1, p1), "trendx": _trend(cx, px), "trend2": _trend(c2, p2),
        "volume": _vol_amt(total),
    }


def _build_do_ou25(home, away, league, date, runners_by_sel, prev: dict) -> dict:
    ro = runners_by_sel.get("O", {})
    ru = runners_by_sel.get("U", {})
    vo = float(ro.get("volume") or 0)
    vu = float(ru.get("volume") or 0)
    total = vo + vu
    co, cu = _coef(ro.get("odd")), _coef(ru.get("odd"))
    po = prev.get("over", "")
    pu = prev.get("under", "")
    return {
        "league": league, "date": date, "home": home, "away": away,
        "over": co, "over_prev": po,
        "under": cu, "under_prev": pu,
        "line": "2.5",
        "trendover": _trend(co, po), "trendunder": _trend(cu, pu),
        "pctover": _vol_pct(vo, total), "amtover": _vol_amt(vo),
        "pctunder": _vol_pct(vu, total), "amtunder": _vol_amt(vu),
        "volume": _vol_amt(total),
    }


def _build_do_btts(home, away, league, date, runners_by_sel, prev: dict) -> dict:
    ry = runners_by_sel.get("Y", {})
    rn = runners_by_sel.get("N", {})
    vy = float(ry.get("volume") or 0)
    vn = float(rn.get("volume") or 0)
    total = vy + vn
    cy, cn = _coef(ry.get("odd")), _coef(rn.get("odd"))
    py_ = prev.get("oddsyes", "")
    pn = prev.get("oddsno", "")
    return {
        "league": league, "date": date, "home": home, "away": away,
        "oddsyes": cy, "oddsyes_prev": py_,
        "oddsno": cn, "oddsno_prev": pn,
        "trendyes": _trend(cy, py_), "trendno": _trend(cn, pn),
        "pctyes": _vol_pct(vy, total), "amtyes": _vol_amt(vy),
        "pctno": _vol_pct(vn, total), "amtno": _vol_amt(vn),
        "volume": _vol_amt(total),
    }


# ── Main scrape function ──────────────────────────────────────────────────────

def run_scrape_betwatch(writer: SupabaseWriter, logger_callback=None) -> int:
    """
    Betwatch API v1 prematch → Supabase.
    Döndürür: toplam yazılan satır sayısı (0 = hata veya boş veri).
    """
    _log = logger_callback if logger_callback else log

    _log("[BW-Pre] Scrape başlıyor — Betwatch API v1 /football/prematch")

    scraped_at = get_turkey_now()
    scraped_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    # 1. Fetch
    try:
        matches = fetch_prematch(timeout=40)
    except Exception as e:
        _log(f"[BW-Pre] HATA — Betwatch API: {e}")
        return 0

    if not matches:
        _log("[BW-Pre] HATA — Betwatch API boş liste döndürdü")
        return 0

    _log(f"[BW-Pre] {len(matches)} maç alındı")

    # 2. Read previous dropping odds for trend calculation
    _log("[BW-Pre] Dropping önceki oran okunuyor...")
    prev_do_1x2 = _read_prev_dropping(writer, "dropping_1x2", ["odds1", "oddsx", "odds2"])
    prev_do_ou25 = _read_prev_dropping(writer, "dropping_ou25", ["over", "under"])
    prev_do_btts = _read_prev_dropping(writer, "dropping_btts", ["oddsyes", "oddsno"])

    # 3. Process matches
    all_fixtures = {}

    mw_1x2_rows, mw_ou25_rows, mw_btts_rows = [], [], []
    do_1x2_rows, do_ou25_rows, do_btts_rows = [], [], []
    all_snapshots = []

    skipped = 0
    for match in matches:
        home = (match.get("teams", {}) or {}).get("v1", "") or ""
        away = (match.get("teams", {}) or {}).get("v2", "") or ""
        league = match.get("league", "") or ""
        kickoff_raw = match.get("kickoff", "") or ""

        home = home.strip()
        away = away.strip()
        league = league.strip()

        if not home or not away:
            skipped += 1
            continue

        kickoff_utc = normalize_kickoff(kickoff_raw)
        date = kickoff_utc  # ISO "YYYY-MM-DDTHH:MM:SS+00:00"

        mhash = make_match_id_hash(home, away, league)

        if mhash not in all_fixtures:
            all_fixtures[mhash] = {
                "match_id_hash": mhash,
                "home_team": home[:100],
                "away_team": away[:100],
                "league": league[:150],
                "kickoff_utc": kickoff_utc,
                "fixture_date": kickoff_utc[:10] if kickoff_utc else "",
            }

        prev_key = (home, away, league, date)

        markets = match.get("markets", []) or []
        for mkt in markets:
            mkt_name = mkt.get("name", "")
            runners = mkt.get("runners", []) or []

            market_key, sels = map_market(mkt_name, runners)
            if market_key is None:
                continue

            runners_by_sel = {sel: runner for sel, runner in sels}

            if market_key == "1X2":
                mw_row = _build_mw_1x2(home, away, league, date, runners_by_sel)
                mw_1x2_rows.append(mw_row)
                prev = prev_do_1x2.get(prev_key, {})
                do_row = _build_do_1x2(home, away, league, date, runners_by_sel, prev)
                do_1x2_rows.append(do_row)

                # Snapshots (moneyway only)
                r1 = runners_by_sel.get("1", {})
                rx = runners_by_sel.get("X", {})
                r2 = runners_by_sel.get("2", {})
                v1 = float(r1.get("volume") or 0)
                vx = float(rx.get("volume") or 0)
                v2 = float(r2.get("volume") or 0)
                total = v1 + vx + v2
                for sel, r, v in [("1", r1, v1), ("X", rx, vx), ("2", r2, v2)]:
                    odd_f = r.get("odd")
                    odd_f = float(odd_f) if odd_f else None
                    vol_f = v if v > 0 else None
                    shr_f = round(v / total * 100, 1) if total > 0 and v > 0 else None
                    if odd_f or vol_f:
                        all_snapshots.append({
                            "match_id_hash": mhash,
                            "market": "1X2",
                            "selection": sel,
                            "odds": odd_f,
                            "volume": vol_f,
                            "share": shr_f,
                            "scraped_at_utc": scraped_at_utc,
                        })

            elif market_key == "OU25":
                mw_row = _build_mw_ou25(home, away, league, date, runners_by_sel)
                mw_ou25_rows.append(mw_row)
                prev = prev_do_ou25.get(prev_key, {})
                do_row = _build_do_ou25(home, away, league, date, runners_by_sel, prev)
                do_ou25_rows.append(do_row)

                ro = runners_by_sel.get("O", {})
                ru = runners_by_sel.get("U", {})
                vo = float(ro.get("volume") or 0)
                vu = float(ru.get("volume") or 0)
                total = vo + vu
                for sel, r, v in [("O", ro, vo), ("U", ru, vu)]:
                    odd_f = r.get("odd")
                    odd_f = float(odd_f) if odd_f else None
                    vol_f = v if v > 0 else None
                    shr_f = round(v / total * 100, 1) if total > 0 and v > 0 else None
                    if odd_f or vol_f:
                        all_snapshots.append({
                            "match_id_hash": mhash,
                            "market": "OU25",
                            "selection": sel,
                            "odds": odd_f,
                            "volume": vol_f,
                            "share": shr_f,
                            "scraped_at_utc": scraped_at_utc,
                        })

            elif market_key == "BTTS":
                mw_row = _build_mw_btts(home, away, league, date, runners_by_sel)
                mw_btts_rows.append(mw_row)
                prev = prev_do_btts.get(prev_key, {})
                do_row = _build_do_btts(home, away, league, date, runners_by_sel, prev)
                do_btts_rows.append(do_row)

                ry = runners_by_sel.get("Y", {})
                rn = runners_by_sel.get("N", {})
                vy = float(ry.get("volume") or 0)
                vn = float(rn.get("volume") or 0)
                total = vy + vn
                for sel, r, v in [("Y", ry, vy), ("N", rn, vn)]:
                    odd_f = r.get("odd")
                    odd_f = float(odd_f) if odd_f else None
                    vol_f = v if v > 0 else None
                    shr_f = round(v / total * 100, 1) if total > 0 and v > 0 else None
                    if odd_f or vol_f:
                        all_snapshots.append({
                            "match_id_hash": mhash,
                            "market": "BTTS",
                            "selection": sel,
                            "odds": odd_f,
                            "volume": vol_f,
                            "share": shr_f,
                            "scraped_at_utc": scraped_at_utc,
                        })

    if skipped:
        _log(f"[BW-Pre] {skipped} maç skip (eksik home/away)")

    _log(
        f"[BW-Pre] İşlendi: {len(all_fixtures)} fixture | "
        f"MW 1X2={len(mw_1x2_rows)} OU25={len(mw_ou25_rows)} BTTS={len(mw_btts_rows)} | "
        f"DO 1X2={len(do_1x2_rows)} OU25={len(do_ou25_rows)} BTTS={len(do_btts_rows)} | "
        f"Snap={len(all_snapshots)}"
    )

    # 4. Write to Supabase
    total_rows = 0
    write_errors = 0

    HISTORY_TABLE = {
        "moneyway_1x2": "moneyway_1x2_history",
        "moneyway_ou25": "moneyway_ou25_history",
        "moneyway_btts": "moneyway_btts_history",
        "dropping_1x2": "dropping_1x2_history",
        "dropping_ou25": "dropping_ou25_history",
        "dropping_btts": "dropping_btts_history",
    }

    WRITE_PLAN = [
        ("moneyway_1x2", mw_1x2_rows),
        ("moneyway_ou25", mw_ou25_rows),
        ("moneyway_btts", mw_btts_rows),
        ("dropping_1x2", do_1x2_rows),
        ("dropping_ou25", do_ou25_rows),
        ("dropping_btts", do_btts_rows),
    ]

    if all_fixtures:
        ok = writer.upsert_fixtures(list(all_fixtures.values()))
        tag = "OK" if ok else "HATA"
        _log(f"[BW-Pre]   [{tag}] Fixtures: {len(all_fixtures)}")
        if not ok:
            write_errors += 1

    for tbl, rows in WRITE_PLAN:
        if not rows:
            _log(f"[BW-Pre]   [!] {tbl}: veri yok")
            continue
        hist_tbl = HISTORY_TABLE[tbl]
        ok_main = writer.replace_table(tbl, rows)
        ok_hist = writer.append_history(hist_tbl, rows, scraped_at)
        if ok_main and ok_hist:
            _log(f"[BW-Pre]   [OK] {tbl}: {len(rows)} satır")
            total_rows += len(rows)
        else:
            _log(f"[BW-Pre]   [HATA] {tbl}: (main={ok_main}, hist={ok_hist})")
            write_errors += 1

    if all_snapshots:
        ok = writer.insert_snapshots("moneyway_snapshots", all_snapshots)
        tag = "OK" if ok else "HATA"
        _log(f"[BW-Pre]   [{tag}] moneyway_snapshots: {len(all_snapshots)}")
        if not ok:
            write_errors += 1

    _log(
        f"[BW-Pre] Tamamlandı — {total_rows} satır, "
        f"{len(all_fixtures)} fixture, {len(all_snapshots)} snapshot, "
        f"{write_errors} hata"
    )
    return total_rows
