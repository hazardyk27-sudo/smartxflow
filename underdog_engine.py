#!/usr/bin/env python3
"""
SmartXFlow Underdog Engine v1.1
Periyodik olarak maçları tarayarak Underdog Pressure sinyallerini bulur ve Supabase'e kaydeder.

Çalışma aralığı: 15 dakika
Kriterler: odds >= 3.00, pct >= 50%, volume >= 1,000 GBP

Sinyal kaydı:
  - İlk tetiklenme: odds/pct/amt/volume alanlarına ilk değer yazılır (created_at ile birlikte)
  - Sonraki taramalar: current_odds/current_pct/current_amt/current_volume + last_updated_at güncellenir
    (Bu alanların Supabase tablosunda mevcut olması gerekir — bkz. MIGRATION SQL)

MIGRATION SQL (Supabase SQL Editor'da çalıştır):
    ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_odds text;
    ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_pct text;
    ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_amt text;
    ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_volume text;
    ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS last_updated_at timestamptz;
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone
from urllib.parse import quote as url_quote

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', '')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

SCAN_INTERVAL = 15 * 60
ERROR_WAIT = 60

ODDS_THRESHOLD = 3.00
PCT_THRESHOLD = 50.0
VOLUME_THRESHOLD = 1000.0

MIGRATION_SQL = """
-- Supabase SQL Editor'da çalıştırın:
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_odds text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_pct text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_amt text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_volume text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS last_updated_at timestamptz;
"""

_columns_verified = False


def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M')
    print(f"[{ts}] {msg}", flush=True)


def _headers_read():
    key = SUPABASE_ANON_KEY
    return {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}


def _headers_write(prefer='return=minimal'):
    key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    return {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Prefer': prefer}


def check_columns_exist():
    """Yeni kolonların mevcut olup olmadığını kontrol et."""
    global _columns_verified
    if _columns_verified:
        return True
    try:
        url = f"{SUPABASE_URL}/rest/v1/underdog_signals?select=current_odds,current_pct,current_amt,current_volume,last_updated_at&limit=1"
        r = requests.get(url, headers=_headers_read(), timeout=8)
        if r.status_code == 200:
            _columns_verified = True
            log("[Columns] Yeni kolonlar mevcut — current_* güncellemeleri aktif")
            return True
        elif r.status_code == 400 and 'column' in r.text.lower():
            return False
        return False
    except Exception:
        return False


def parse_odds_pct(val):
    """Odds/yüzde için: virgül ondalık ayırıcı olarak kabul edilir (3,40 → 3.40)."""
    try:
        s = str(val).replace('£', '').replace('%', '').replace(' ', '').strip()
        s = s.replace(',', '.')
        return float(s)
    except Exception:
        return 0.0


def parse_volume_amt(val):
    """Hacim/miktar için: virgül binlik ayırıcı olarak kaldırılır (£1,000 → 1000)."""
    try:
        s = str(val).replace('£', '').replace('%', '').replace(',', '').replace(' ', '').strip()
        return float(s)
    except Exception:
        return 0.0


def fetch_latest_snapshots():
    """moneyway_1x2_history tablosundan her maç için en son snapshot'ı çek."""
    try:
        headers = _headers_read()
        url = (
            f"{SUPABASE_URL}/rest/v1/moneyway_1x2_history"
            "?select=home,away,league,date,odds1,oddsx,odds2,pct1,pctx,pct2,amt1,amtx,amt2,volume,scraped_at,match_id_hash"
            "&order=scraped_at.desc&limit=15000"
        )
        r = requests.get(url, headers=headers, timeout=25)
        if r.status_code != 200:
            log(f"[Fetch] HTTP {r.status_code}: {r.text[:200]}")
            return {}
        rows = r.json()
        latest = {}
        for row in rows:
            h = row.get('match_id_hash', '')
            if h and h not in latest:
                latest[h] = row
        log(f"[Fetch] {len(latest)} benzersiz maç için son snapshot çekildi")
        return latest
    except Exception as e:
        log(f"[Fetch] Hata: {e}")
        return {}


def find_signals(snapshots):
    """Underdog kriterlerini karşılayan sinyalleri bul."""
    signals = []
    for _hash, row in snapshots.items():
        home = row.get('home', '')
        away = row.get('away', '')
        league = row.get('league', '')
        date = row.get('date', '')

        volume_str = row.get('volume', '')
        volume_val = parse_volume_amt(volume_str)
        if volume_val < VOLUME_THRESHOLD:
            continue

        candidates = [
            ('1', 'Ev Sahibi',   row.get('odds1'), row.get('pct1'), row.get('amt1')),
            ('X', 'Beraberlik',  row.get('oddsx'), row.get('pctx'), row.get('amtx')),
            ('2', 'Deplasman',   row.get('odds2'), row.get('pct2'), row.get('amt2')),
        ]

        for code, label, raw_odds, raw_pct, raw_amt in candidates:
            odds_val = parse_odds_pct(raw_odds)
            pct_val = parse_odds_pct(raw_pct)

            if odds_val >= ODDS_THRESHOLD and pct_val >= PCT_THRESHOLD:
                signals.append({
                    'home_team': home,
                    'away_team': away,
                    'league': league,
                    'date': date,
                    'match_key': f"{home}|{away}|{date}",
                    'selection_code': code,
                    'selection_label': label,
                    'odds': str(raw_odds) if raw_odds is not None else '',
                    'pct': str(raw_pct) if raw_pct is not None else '',
                    'amt': str(raw_amt) if raw_amt is not None else '',
                    'volume': volume_str,
                })

    return signals


def save_new_signals(signals, with_current_cols):
    """Yeni sinyalleri ekle — UNIQUE conflict'te mevcut kayıt korunur (initial değerler değişmez)."""
    if not signals:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for s in signals:
        rec = {
            'match_key': s['match_key'],
            'home_team': s['home_team'],
            'away_team': s['away_team'],
            'league': s['league'],
            'match_date': s['date'],
            'selection_code': s['selection_code'],
            'selection_label': s['selection_label'],
            'odds': s['odds'],
            'pct': s['pct'],
            'amt': s['amt'],
            'volume': s['volume'],
            'created_at': now,
        }
        if with_current_cols:
            rec['current_odds'] = s['odds']
            rec['current_pct'] = s['pct']
            rec['current_amt'] = s['amt']
            rec['current_volume'] = s['volume']
            rec['last_updated_at'] = now
        records.append(rec)

    headers = _headers_write('resolution=ignore-duplicates,return=representation')
    url = f"{SUPABASE_URL}/rest/v1/underdog_signals?on_conflict=match_key,selection_code"
    r = requests.post(url, headers=headers, json=records, timeout=15)
    if r.status_code in (200, 201):
        try:
            inserted = len(r.json()) if r.text else 0
        except Exception:
            inserted = 0
        return inserted
    log(f"[UnderdogEngine] INSERT hatası: {r.status_code} {r.text[:200]}")
    return 0


def update_current_values(signals):
    """Bulunan tüm sinyallerin current_* alanlarını güncelle."""
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    failed = 0
    wh = _headers_write()
    for s in signals:
        try:
            mk = url_quote(s['match_key'], safe='')
            sc = url_quote(s['selection_code'], safe='')
            url = f"{SUPABASE_URL}/rest/v1/underdog_signals?match_key=eq.{mk}&selection_code=eq.{sc}"
            data = {
                'current_odds': s['odds'],
                'current_pct': s['pct'],
                'current_amt': s['amt'],
                'current_volume': s['volume'],
                'last_updated_at': now,
            }
            r = requests.patch(url, headers=wh, json=data, timeout=10)
            if r.status_code in (200, 204):
                updated += 1
            else:
                failed += 1
        except Exception as e:
            log(f"[Update] Hata: {e}")
            failed += 1
    if failed and not updated:
        log(f"[UnderdogEngine] current_* kolonları yok — Supabase SQL Editor'da migration çalıştırın.")
    return updated


def update_heartbeat(status):
    try:
        now = datetime.now(timezone.utc).isoformat()
        key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
        headers = {
            'apikey': key,
            'Authorization': f'Bearer {key}',
            'Content-Type': 'application/json',
            'Prefer': 'return=representation,resolution=merge-duplicates'
        }
        data = {'source': 'underdog_engine', 'last_heartbeat': now, 'status': status, 'updated_at': now}
        requests.post(f"{SUPABASE_URL}/rest/v1/scraper_heartbeat?on_conflict=source",
                      json=data, headers=headers, timeout=5)
    except Exception:
        pass


def run_scan():
    log("[UnderdogEngine] Tarama başlıyor...")
    snapshots = fetch_latest_snapshots()
    if not snapshots:
        log("[UnderdogEngine] Veri çekilemedi, tarama atlandı")
        return 0, 0

    signals = find_signals(snapshots)

    if not signals:
        log(f"[UnderdogEngine] found=0 updated=0")
        return 0, 0

    has_cols = check_columns_exist()
    new_count = save_new_signals(signals, with_current_cols=has_cols)
    updated_count = update_current_values(signals) if has_cols else 0

    log(f"[UnderdogEngine] found={len(signals)} inserted={new_count} updated={updated_count}")
    return new_count, updated_count


def run_engine():
    print("=" * 60)
    print("SMARTXFLOW UNDERDOG ENGINE v1.1")
    print(f"Tarama aralığı : {SCAN_INTERVAL // 60} dakika")
    print(f"Kriterler      : odds>={ODDS_THRESHOLD}, pct>={PCT_THRESHOLD}%, volume>={VOLUME_THRESHOLD:,.0f}")
    print(f"Supabase URL   : {SUPABASE_URL[:40]}..." if SUPABASE_URL else "Supabase URL: NOT SET")
    print("=" * 60)

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        log("[FATAL] SUPABASE_URL veya SUPABASE_ANON_KEY ayarlanmamış!")
        sys.exit(1)

    # Kolon kontrolü — yoksa migration SQL'i göster
    if not check_columns_exist():
        print("\n" + "=" * 60)
        print("UYARI: Yeni kolonlar henüz Supabase'de yok.")
        print("Supabase SQL Editor'da aşağıdaki SQL'i çalıştırın:")
        print(MIGRATION_SQL)
        print("=" * 60 + "\n")
        print("Engine migration olmadan da çalışmaya devam eder.")
        print("Kolonlar eklendikten sonra current_* güncellemeleri otomatik aktif olur.\n")

    update_heartbeat("started")
    log("Engine başlatıldı — ilk tarama hemen çalışıyor...")
    last_scan = 0
    consecutive_errors = 0

    while True:
        try:
            now = time.time()
            if now - last_scan >= SCAN_INTERVAL:
                run_scan()
                update_heartbeat("idle")
                last_scan = time.time()
                consecutive_errors = 0

            time.sleep(30)

        except KeyboardInterrupt:
            log("Durduruldu (Ctrl+C)")
            update_heartbeat("stopped")
            break

        except Exception as e:
            consecutive_errors += 1
            wait_time = min(ERROR_WAIT * consecutive_errors, 300)
            log(f"Beklenmeyen hata ({consecutive_errors}): {e}")
            import traceback
            traceback.print_exc()
            update_heartbeat("error")
            time.sleep(wait_time)


if __name__ == '__main__':
    run_engine()
