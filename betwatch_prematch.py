"""
betwatch_prematch.py — Betwatch API v1 prematch scraper.

Betwatch /football/prematch endpoint'inden veri çeker ve SmartXFlow'a yazar.
Provider-backed markets:
- Match Odds (1X2)
- Draw no Bet (DNB)
- Over/Under 2.5 Goals (OU25)
- Both teams to Score? (BTTS)

Double Chance provider tarafından gelmiyorsa 1X2'den sentetik üretilmez.
"""

import os
import sys
import requests
from datetime import datetime, timezone

_ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(_ROOT, "desktop", "scraper_standalone"))
sys.path.insert(0, os.path.join(_ROOT, "scraper_standalone"))

from core.hash_utils import make_match_id_hash
from standalone_scraper import SupabaseWriter, get_turkey_now
from betwatch_client import fetch_prematch, normalize_kickoff, map_market

try:
    import certifi
    SSL_VERIFY = certifi.where()
except Exception:
    SSL_VERIFY = True


def log(msg: str):
    ts = datetime.now().strftime("%H:%M:%S")
    print(f"[BW-Pre {ts}] {msg}", flush=True)


def _coef(value) -> str:
    try:
        number = float(value)
        return f"{number:g}" if number > 0 else ""
    except Exception:
        return ""


def _vol_amt(value) -> str:
    try:
        number = float(value)
        if number <= 0:
            return ""
        return f"£ {int(number)}" if number == int(number) else f"£ {number:g}"
    except Exception:
        return ""


def _vol_pct(value: float, total: float) -> str:
    try:
        if total <= 0 or value <= 0:
            return ""
        return f"{(value / total * 100):.1f}%"
    except Exception:
        return ""


def _trend(current, previous) -> str:
    try:
        cur = float(current) if current not in (None, "", 0) else 0.0
        prev = float(previous) if previous not in (None, "", 0) else 0.0
        if cur <= 0 or prev <= 0 or abs(cur - prev) < 0.001:
            return ""
        return "up" if cur > prev else "down"
    except Exception:
        return ""


def _read_prev_rows(writer: SupabaseWriter, table: str, fields: list[str]) -> dict:
    """Current DB values keyed by exact match identity for trend calculation."""
    select = "home,away,league,date," + ",".join(fields)
    try:
        response = requests.get(
            f"{writer._rest_url(table)}?select={select}",
            headers=writer._headers(),
            timeout=30,
            verify=SSL_VERIFY,
        )
        if response.status_code == 200:
            result = {}
            for row in response.json():
                key = (
                    row.get("home", ""),
                    row.get("away", ""),
                    row.get("league", ""),
                    row.get("date", ""),
                )
                result[key] = {field: row.get(field, "") for field in fields}
            return result
    except Exception as exc:
        log(f"  [WARN] {table} previous odds okunamadı: {exc}")
    return {}


# Backward-compatible name used by older tests/callers.
_read_prev_dropping = _read_prev_rows


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


def _build_mw_dnb(home, away, league, date, runners_by_sel, prev: dict) -> dict:
    r1 = runners_by_sel.get("1", {})
    r2 = runners_by_sel.get("2", {})
    v1 = float(r1.get("volume") or 0)
    v2 = float(r2.get("volume") or 0)
    total = v1 + v2
    c1 = _coef(r1.get("odd"))
    c2 = _coef(r2.get("odd"))
    p1 = prev.get("odds1", "")
    p2 = prev.get("odds2", "")
    return {
        "league": league, "date": date, "home": home, "away": away,
        "odds1": c1, "odds2": c2,
        "trend1": _trend(c1, p1), "trend2": _trend(c2, p2),
        "pct1": _vol_pct(v1, total), "amt1": _vol_amt(v1),
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
    p1, px, p2 = prev.get("odds1", ""), prev.get("oddsx", ""), prev.get("odds2", "")
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
    po, pu = prev.get("over", ""), prev.get("under", "")
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
    py_, pn = prev.get("oddsyes", ""), prev.get("oddsno", "")
    return {
        "league": league, "date": date, "home": home, "away": away,
        "oddsyes": cy, "oddsyes_prev": py_,
        "oddsno": cn, "oddsno_prev": pn,
        "trendyes": _trend(cy, py_), "trendno": _trend(cn, pn),
        "pctyes": _vol_pct(vy, total), "amtyes": _vol_amt(vy),
        "pctno": _vol_pct(vn, total), "amtno": _vol_amt(vn),
        "volume": _vol_amt(total),
    }


def _market_with_context(name, runners, home, away):
    """Pass team context to new clients while keeping old test/runtime stubs compatible."""
    try:
        return map_market(name, runners, home=home, away=away)
    except TypeError:
        return map_market(name, runners)


def _snapshot(match_hash, market, selection, runner, volume, total, scraped_at_utc):
    odd = runner.get("odd")
    odd = float(odd) if odd else None
    vol = volume if volume > 0 else None
    share = round(volume / total * 100, 1) if total > 0 and volume > 0 else None
    if not odd and not vol:
        return None
    return {
        "match_id_hash": match_hash,
        "market": market,
        "selection": selection,
        "odds": odd,
        "volume": vol,
        "share": share,
        "scraped_at_utc": scraped_at_utc,
    }


def run_scrape_betwatch(writer: SupabaseWriter, logger_callback=None) -> int:
    """Betwatch prematch → Supabase. Returns count of successful current-table rows."""
    _log = logger_callback if logger_callback else log
    writer.last_write_errors = []
    writer.last_scrape_stats = {
        "match_count": 0,
        "snapshot_count": 0,
        "row_count": 0,
        "scraped_at_utc": None,
        "write_errors": 0,
    }

    _log("[BW-Pre] Scrape başlıyor — Betwatch API v1 /football/prematch")
    scraped_at = get_turkey_now()
    scraped_at_utc = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S+00:00")

    try:
        matches = fetch_prematch(timeout=40)
    except Exception as exc:
        _log(f"[BW-Pre] HATA — Betwatch API: {exc}")
        return 0
    if not matches:
        _log("[BW-Pre] HATA — Betwatch API boş liste döndürdü")
        return 0
    _log(f"[BW-Pre] {len(matches)} maç alındı")

    _log("[BW-Pre] Previous odds okunuyor...")
    prev_do_1x2 = _read_prev_rows(writer, "dropping_1x2", ["odds1", "oddsx", "odds2"])
    prev_do_ou25 = _read_prev_rows(writer, "dropping_ou25", ["over", "under"])
    prev_do_btts = _read_prev_rows(writer, "dropping_btts", ["oddsyes", "oddsno"])
    prev_mw_dnb = _read_prev_rows(writer, "moneyway_draw_no_bet", ["odds1", "odds2"])

    all_fixtures = {}
    mw_1x2_rows, mw_dnb_rows, mw_ou25_rows, mw_btts_rows = [], [], [], []
    do_1x2_rows, do_ou25_rows, do_btts_rows = [], [], []
    all_snapshots = []
    skipped = 0

    for match in matches:
        home = ((match.get("teams", {}) or {}).get("v1", "") or "").strip()
        away = ((match.get("teams", {}) or {}).get("v2", "") or "").strip()
        league = (match.get("league", "") or "").strip()
        kickoff_raw = match.get("kickoff", "") or ""
        if not home or not away:
            skipped += 1
            continue

        kickoff_utc = normalize_kickoff(kickoff_raw)
        date = kickoff_utc
        match_hash = make_match_id_hash(home, away, league, kickoff_utc)
        all_fixtures.setdefault(match_hash, {
            "match_id_hash": match_hash,
            "home_team": home[:100],
            "away_team": away[:100],
            "league": league[:150],
            "kickoff_utc": kickoff_utc,
            "fixture_date": kickoff_utc[:10] if kickoff_utc else "",
        })
        prev_key = (home, away, league, date)

        for market in match.get("markets", []) or []:
            market_name = market.get("name", "")
            runners = market.get("runners", []) or []
            market_key, selections = _market_with_context(market_name, runners, home, away)
            if market_key is None:
                continue
            runners_by_sel = {selection: runner for selection, runner in selections}

            if market_key == "1X2":
                mw_1x2_rows.append(_build_mw_1x2(home, away, league, date, runners_by_sel))
                do_1x2_rows.append(_build_do_1x2(
                    home, away, league, date, runners_by_sel, prev_do_1x2.get(prev_key, {})
                ))
                triple = [("1", runners_by_sel.get("1", {})), ("X", runners_by_sel.get("X", {})), ("2", runners_by_sel.get("2", {}))]
                volumes = [float(runner.get("volume") or 0) for _, runner in triple]
                total = sum(volumes)
                for (selection, runner), volume in zip(triple, volumes):
                    row = _snapshot(match_hash, "1X2", selection, runner, volume, total, scraped_at_utc)
                    if row:
                        all_snapshots.append(row)

            elif market_key == "DNB":
                mw_dnb_rows.append(_build_mw_dnb(
                    home, away, league, date, runners_by_sel, prev_mw_dnb.get(prev_key, {})
                ))
                pair = [("1", runners_by_sel.get("1", {})), ("2", runners_by_sel.get("2", {}))]
                volumes = [float(runner.get("volume") or 0) for _, runner in pair]
                total = sum(volumes)
                for (selection, runner), volume in zip(pair, volumes):
                    row = _snapshot(match_hash, "DNB", selection, runner, volume, total, scraped_at_utc)
                    if row:
                        all_snapshots.append(row)

            elif market_key == "OU25":
                mw_ou25_rows.append(_build_mw_ou25(home, away, league, date, runners_by_sel))
                do_ou25_rows.append(_build_do_ou25(
                    home, away, league, date, runners_by_sel, prev_do_ou25.get(prev_key, {})
                ))
                pair = [("O", runners_by_sel.get("O", {})), ("U", runners_by_sel.get("U", {}))]
                volumes = [float(runner.get("volume") or 0) for _, runner in pair]
                total = sum(volumes)
                for (selection, runner), volume in zip(pair, volumes):
                    row = _snapshot(match_hash, "OU25", selection, runner, volume, total, scraped_at_utc)
                    if row:
                        all_snapshots.append(row)

            elif market_key == "BTTS":
                mw_btts_rows.append(_build_mw_btts(home, away, league, date, runners_by_sel))
                do_btts_rows.append(_build_do_btts(
                    home, away, league, date, runners_by_sel, prev_do_btts.get(prev_key, {})
                ))
                pair = [("Y", runners_by_sel.get("Y", {})), ("N", runners_by_sel.get("N", {}))]
                volumes = [float(runner.get("volume") or 0) for _, runner in pair]
                total = sum(volumes)
                for (selection, runner), volume in zip(pair, volumes):
                    row = _snapshot(match_hash, "BTTS", selection, runner, volume, total, scraped_at_utc)
                    if row:
                        all_snapshots.append(row)

    if skipped:
        _log(f"[BW-Pre] {skipped} maç skip (eksik home/away)")

    def _dedup(rows):
        seen = {}
        for row in rows:
            date_value = row.get("date", "")
            key = (
                row.get("league", ""), row.get("home", ""), row.get("away", ""),
                date_value[:10] if date_value else "",
            )
            seen[key] = row
        return list(seen.values())

    row_groups = [mw_1x2_rows, mw_dnb_rows, mw_ou25_rows, mw_btts_rows,
                  do_1x2_rows, do_ou25_rows, do_btts_rows]
    pre_total = sum(len(rows) for rows in row_groups)
    mw_1x2_rows = _dedup(mw_1x2_rows)
    mw_dnb_rows = _dedup(mw_dnb_rows)
    mw_ou25_rows = _dedup(mw_ou25_rows)
    mw_btts_rows = _dedup(mw_btts_rows)
    do_1x2_rows = _dedup(do_1x2_rows)
    do_ou25_rows = _dedup(do_ou25_rows)
    do_btts_rows = _dedup(do_btts_rows)
    post_total = sum(len(rows) for rows in [mw_1x2_rows, mw_dnb_rows, mw_ou25_rows, mw_btts_rows,
                                            do_1x2_rows, do_ou25_rows, do_btts_rows])
    if pre_total != post_total:
        _log(f"[BW-Pre] Dedup: {pre_total - post_total} duplicate satır kaldırıldı")

    _log(
        f"[BW-Pre] İşlendi: {len(all_fixtures)} fixture | "
        f"MW 1X2={len(mw_1x2_rows)} DNB={len(mw_dnb_rows)} OU25={len(mw_ou25_rows)} BTTS={len(mw_btts_rows)} | "
        f"DO 1X2={len(do_1x2_rows)} OU25={len(do_ou25_rows)} BTTS={len(do_btts_rows)} | "
        f"Snap={len(all_snapshots)}"
    )

    history_table = {
        "moneyway_1x2": "moneyway_1x2_history",
        "moneyway_draw_no_bet": "moneyway_draw_no_bet_history",
        "moneyway_ou25": "moneyway_ou25_history",
        "moneyway_btts": "moneyway_btts_history",
        "dropping_1x2": "dropping_1x2_history",
        "dropping_ou25": "dropping_ou25_history",
        "dropping_btts": "dropping_btts_history",
    }
    write_plan = [
        ("moneyway_1x2", mw_1x2_rows),
        ("moneyway_draw_no_bet", mw_dnb_rows),
        ("moneyway_ou25", mw_ou25_rows),
        ("moneyway_btts", mw_btts_rows),
        ("dropping_1x2", do_1x2_rows),
        ("dropping_ou25", do_ou25_rows),
        ("dropping_btts", do_btts_rows),
    ]

    total_rows = 0
    write_errors = 0
    if all_fixtures:
        ok = writer.upsert_fixtures(list(all_fixtures.values()))
        _log(f"[BW-Pre]   [{'OK' if ok else 'HATA'}] Fixtures: {len(all_fixtures)}")
        if not ok:
            write_errors += 1

    for table, rows in write_plan:
        if not rows:
            _log(f"[BW-Pre]   [!] {table}: veri yok")
            continue
        ok_main = writer.replace_table(table, rows)
        ok_history = writer.append_history(history_table[table], rows, scraped_at)
        if ok_main:
            total_rows += len(rows)
        if ok_main and ok_history:
            _log(f"[BW-Pre]   [OK] {table}: {len(rows)} satır")
        else:
            _log(f"[BW-Pre]   [HATA] {table}: (main={ok_main}, hist={ok_history})")
            write_errors += 1

    if all_snapshots:
        ok = writer.insert_snapshots("moneyway_snapshots", all_snapshots)
        _log(f"[BW-Pre]   [{'OK' if ok else 'HATA'}] moneyway_snapshots: {len(all_snapshots)}")
        if not ok:
            write_errors += 1

    writer.last_scrape_stats = {
        "match_count": len(all_fixtures),
        "snapshot_count": len(all_snapshots),
        "row_count": total_rows,
        "scraped_at_utc": scraped_at_utc,
        "write_errors": write_errors,
    }
    _log(
        f"[BW-Pre] Tamamlandı — {total_rows} satır, {len(all_fixtures)} fixture, "
        f"{len(all_snapshots)} snapshot, {write_errors} hata"
    )
    return total_rows
