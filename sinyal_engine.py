#!/usr/bin/env python3
"""
SmartXFlow Sinyal Engine v1.2
İki sinyal tipini aynı anda tarar:
  1. Underdog Pressure: odds >= 2.90, pct >= 50%, volume >= £2,000
  2. Confirmed Money: pct > 80%, oran >= %4 düşüş (10 saat), volume >= £2,000, stabilite onaylı

Çalışma aralığı: 15 dakika

Tablolar:
  - underdog_signals (mevcut)
  - confirmed_money_signals (yeni — migrations/create_confirmed_money_signals.sql)
"""

import os
import sys
import time
import requests
from datetime import datetime, timezone, timedelta
from urllib.parse import quote as url_quote

SUPABASE_URL = os.environ.get('SUPABASE_URL', '')
SUPABASE_ANON_KEY = os.environ.get('SUPABASE_ANON_KEY', '')
SUPABASE_SERVICE_KEY = os.environ.get('SUPABASE_SERVICE_ROLE_KEY', '')

SCAN_INTERVAL = 15 * 60
ERROR_WAIT = 60

# Underdog Pressure kriterleri
ODDS_THRESHOLD = 2.90
PCT_THRESHOLD = 50.0
VOLUME_THRESHOLD = 200.0

# Confirmed Money kriterleri
CM_PCT_THRESHOLD = 80.0
CM_ODDS_DROP_PCT = 0.04      # %4 düşüş (göreli)
CM_VOLUME_THRESHOLD = 2000.0
CM_COOLDOWN_HOURS = 3
CM_STABILITY_SNAPSHOTS = 3   # Son 3 ardışık snapshot'ta pct > %80
CM_MIN_ODDS = 1.35           # Seçim oranı alt sınırı
CM_MAX_ODDS = 2.20           # Seçim oranı üst sınırı

# Confirmed Money V2 kriterleri (araştırma tabanlı, %100 başarı bölgesi)
CMV2_PCT_THRESHOLD       = 88.0
CMV2_ODDS_DROP_PCT       = 0.07   # %7 düşüş
CMV2_VOLUME_THRESHOLD    = 2000.0
CMV2_COOLDOWN_HOURS      = 3
CMV2_STABILITY_SNAPSHOTS = 3
CMV2_MIN_ODDS            = 1.55   # Kısa oranlar hariç
CMV2_MAX_ODDS            = 2.20

# Fake Sharp kriterleri
FS_PCT_THRESHOLD = 75.0
FS_ODDS_RISE_PCT = 0.04      # %4 yükseliş (göreli)
FS_VOLUME_THRESHOLD = 2000.0
FS_COOLDOWN_HOURS = 3
FS_STABILITY_SNAPSHOTS = 3   # Son 3 ardışık snapshot'ta pct > %80
FS_MIN_ODDS = 1.35           # Seçim oranı alt sınırı
FS_MAX_ODDS = 2.20           # Seçim oranı üst sınırı

MIGRATION_SQL = """
-- underdog_signals current kolonları (zaten çalıştırıldıysa atla):
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_odds text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_pct text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_amt text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS current_volume text;
ALTER TABLE underdog_signals ADD COLUMN IF NOT EXISTS last_updated_at timestamptz;
"""

CM_MIGRATION_SQL = """
-- confirmed_money_signals tablosu (migrations/create_confirmed_money_signals.sql):
CREATE TABLE IF NOT EXISTS confirmed_money_signals (
    id bigserial PRIMARY KEY,
    match_key text NOT NULL,
    home_team text,
    away_team text,
    league text,
    match_date text,
    selection_code text NOT NULL,
    selection_label text,
    odds_16h text,
    odds_now text,
    current_odds text,
    pct_now text,
    current_pct text,
    volume_now text,
    current_volume text,
    odds_drop_pct real,
    created_at timestamptz DEFAULT now(),
    last_updated_at timestamptz,
    result text
);
ALTER TABLE confirmed_money_signals ADD COLUMN IF NOT EXISTS result text;
"""

CMV2_MIGRATION_SQL = """
-- confirmed_money_v2_signals tablosu:
CREATE TABLE IF NOT EXISTS confirmed_money_v2_signals (
    id              bigserial PRIMARY KEY,
    match_key       text NOT NULL,
    home_team       text,
    away_team       text,
    league          text,
    match_date      text,
    selection_code  text NOT NULL,
    selection_label text,
    odds_16h        text,
    odds_now        text,
    current_odds    text,
    pct_now         text,
    current_pct     text,
    volume_now      text,
    current_volume  text,
    odds_drop_pct   numeric,
    created_at      timestamptz DEFAULT now(),
    last_updated_at timestamptz,
    result          text,
    UNIQUE (match_key, selection_code)
);
ALTER TABLE confirmed_money_v2_signals ADD COLUMN IF NOT EXISTS result text;
"""

_columns_verified = False
_cm_table_verified = False
_cm_v2_table_verified = False
_fs_table_verified = False


def log(msg):
    ts = datetime.now(timezone.utc).strftime('%H:%M')
    print(f"[{ts}] {msg}", flush=True)


def _headers_read():
    key = SUPABASE_ANON_KEY
    return {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}


def _headers_write(prefer='return=minimal'):
    key = SUPABASE_SERVICE_KEY or SUPABASE_ANON_KEY
    return {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': 'application/json', 'Prefer': prefer}


# ============================================================
# SHARED UTILITIES
# ============================================================

def parse_odds_pct(val):
    """Odds/yüzde için: virgül ondalık ayırıcı olarak kabul edilir (3,40 -> 3.40)."""
    try:
        s = str(val).replace('£', '').replace('%', '').replace(' ', '').strip()
        s = s.replace(',', '.')
        return float(s)
    except Exception:
        return 0.0


def parse_volume_amt(val):
    """Hacim/miktar için: virgül binlik ayırıcı olarak kaldırılır (1,000 -> 1000)."""
    try:
        s = str(val).replace('£', '').replace('%', '').replace(',', '').replace(' ', '').strip()
        return float(s)
    except Exception:
        return 0.0


def fetch_latest_snapshots():
    """moneyway_1x2 tablosundan her maç için en son snapshot'ı çek.
    moneyway_1x2: scheduled scraper tarafından her 15dk'da sıfırlanıp yeniden yazılan
    güncel tablo (~1987 maç) — history tablosundan çok daha kapsamlı.
    Kolonlar: home,away,league,date,volume,odds1,oddsx,odds2,amt1,amtx,amt2,pct1,pctx,pct2
    Anahtar: tabloda gerçek match_id_hash varsa onu kullan; yoksa home|away|date
    (fetch_history_16h() da aynı formatı kullanır — lookup tutarlılığı sağlanır).

    EK: moneyway_1x2_history'den son 2 saatin en güncel snapshot'ları da eklenir
    (history fallback). Bu sayede maç başladıktan sonra canlı tablodan düşen maçlar
    için de FakeSharp sinyali üretilebilir. Canlı tablo her zaman önceliklidir.
    """
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/moneyway_1x2"
            "?select=home,away,league,date,odds1,oddsx,odds2,pct1,pctx,pct2,amt1,amtx,amt2,volume"
            "&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=25)
        if r.status_code != 200:
            log(f"[Fetch] HTTP {r.status_code}: {r.text[:200]}")
            return {}
        rows = r.json()
        latest = {}
        for row in rows:
            home = row.get('home', '')
            away = row.get('away', '')
            date = row.get('date', '')
            if not home or not away:
                continue
            real_hash = row.get('match_id_hash', '')
            key = real_hash if real_hash else f"{home}|{away}|{date}"
            if key not in latest:
                row['match_id_hash'] = key
                latest[key] = row
        live_count = len(latest)

        # --- History fallback: son 2 saatteki maçların en güncel snapshot'ı ---
        # Maç başladıktan sonra moneyway_1x2'den düşen maçlar için FakeSharp
        # sinyalinin üretilebilmesi amacıyla history tablosundan ek snapshot çekilir.
        try:
            cutoff_2h = (datetime.now(timezone.utc) - timedelta(hours=2)).isoformat()
            hist_url = (
                f"{SUPABASE_URL}/rest/v1/moneyway_1x2_history"
                f"?select=home,away,league,date,odds1,oddsx,odds2,pct1,pctx,pct2,amt1,amtx,amt2,volume,scraped_at"
                f"&scraped_at=gte.{cutoff_2h}"
                f"&order=scraped_at.desc"
                f"&limit=20000"
            )
            hr = requests.get(hist_url, headers=_headers_read(), timeout=20)
            if hr.status_code == 200:
                hist_rows = hr.json()
                # Her maç için sadece en güncel (desc sıralı, ilk gelen) snapshot'ı al
                hist_latest = {}
                for row in hist_rows:
                    home = row.get('home', '')
                    away = row.get('away', '')
                    date = row.get('date', '')
                    if not home or not away:
                        continue
                    key = f"{home}|{away}|{date}"
                    if key not in hist_latest:
                        row['match_id_hash'] = key
                        hist_latest[key] = row
                # Canlı tabloda olmayan maçları ekle (canlı tablo öncelikli)
                fallback_count = 0
                for key, row in hist_latest.items():
                    if key not in latest:
                        latest[key] = row
                        fallback_count += 1
                log(f"[Fetch] {live_count} maç (live) + {fallback_count} maç (history fallback, son 2sa)")
            else:
                log(f"[Fetch] History fallback HTTP {hr.status_code} — atlandı")
                log(f"[Fetch] {live_count} maç (live) + 0 maç (history fallback)")
        except Exception as he:
            log(f"[Fetch] History fallback hata: {he} — atlandı")
            log(f"[Fetch] {live_count} maç (live) + 0 maç (history fallback)")

        return latest
    except Exception as e:
        log(f"[Fetch] Hata: {e}")
        return {}


def build_snapshot_lookup(snapshots):
    """Snapshot listesini match_key bazlı dict'e çevir (home|away|date -> row).
    Her maç için hem UTC (eski kayıtlar) hem UTC+3 (yeni kayıtlar) key eklenir.
    """
    lookup = {}
    for _hash, row in snapshots.items():
        home = row.get('home', '')
        away = row.get('away', '')
        date = row.get('date', '')
        mk_utc = f"{home}|{away}|{date}"
        lookup[mk_utc] = row
        mk_tr = f"{home}|{away}|{_normalize_date_key(date)}"
        if mk_tr != mk_utc:
            lookup[mk_tr] = row
    return lookup


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
        data = {'source': 'sinyal_engine', 'last_heartbeat': now, 'status': status, 'updated_at': now}
        requests.post(f"{SUPABASE_URL}/rest/v1/scraper_heartbeat?on_conflict=source",
                      json=data, headers=headers, timeout=5)
    except Exception:
        pass


# ============================================================
# UNDERDOG PRESSURE ENGINE
# ============================================================

def check_columns_exist():
    """underdog_signals current_* kolonlarının mevcut olup olmadığını kontrol et."""
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
        return False
    except Exception:
        return False


def _normalize_date_key(date_str):
    """Arbworld UTC tarihini UTC+3 (Türkiye) saatine çevirir, saniyesiz.
    '14.Apr 18:00:00' → '14.Apr 21:00'  (app.py cache ile aynı format)
    """
    try:
        import re as _re
        s = str(date_str)
        dm = _re.search(r'(\d{1,2})\.(\w{3})', s)
        tm = _re.search(r'(\d{2}):(\d{2})(?::\d{2})?', s)
        if dm and tm:
            h_utc = int(tm.group(1))
            mi = tm.group(2)
            day = int(dm.group(1))
            h_tr = (h_utc + 3) % 24
            if h_utc + 3 >= 24:
                day += 1
            return f"{day:02d}.{dm.group(2)} {h_tr:02d}:{mi}"
    except Exception:
        pass
    return str(date_str)


def find_signals(snapshots):
    """Underdog Pressure kriterlerini karşılayan sinyalleri bul."""
    signals = []
    for _hash, row in snapshots.items():
        home = row.get('home', '')
        away = row.get('away', '')
        league = row.get('league', '')
        date = row.get('date', '')
        volume_str = row.get('volume', '')
        if parse_volume_amt(volume_str) < VOLUME_THRESHOLD:
            continue
        for code, label, raw_odds, raw_pct, raw_amt in [
            ('1', 'Ev Sahibi',  row.get('odds1'), row.get('pct1'), row.get('amt1')),
            ('2', 'Deplasman',  row.get('odds2'), row.get('pct2'), row.get('amt2')),
        ]:
            if parse_odds_pct(raw_odds) >= ODDS_THRESHOLD and parse_odds_pct(raw_pct) >= PCT_THRESHOLD:
                signals.append({
                    'home_team': home, 'away_team': away, 'league': league, 'date': date,
                    'match_key': f"{home}|{away}|{_normalize_date_key(date)}",
                    'selection_code': code, 'selection_label': label,
                    'odds': str(raw_odds) if raw_odds is not None else '',
                    'pct': str(raw_pct) if raw_pct is not None else '',
                    'amt': str(raw_amt) if raw_amt is not None else '',
                    'volume': volume_str,
                })
    return signals


def save_new_signals(signals, with_current_cols):
    """Yeni underdog sinyallerini ekle — UNIQUE conflict'te mevcut kayıt korunur."""
    if not signals:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for s in signals:
        rec = {
            'match_key': s['match_key'], 'home_team': s['home_team'], 'away_team': s['away_team'],
            'league': s['league'], 'match_date': _betwatch_to_iso_datetime(s['date']),
            'selection_code': s['selection_code'], 'selection_label': s['selection_label'],
            'odds': s['odds'], 'pct': s['pct'], 'amt': s['amt'], 'volume': s['volume'],
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
            return len(r.json()) if r.text else 0
        except Exception:
            return 0
    log(f"[SinyalEngine] INSERT hatası: {r.status_code} {r.text[:200]}")
    return 0


def fetch_existing_signals():
    """DB'deki mevcut tüm underdog sinyallerini çek."""
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/underdog_signals"
            "?select=match_key,selection_code,home_team,away_team,date:match_date"
            "&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=12)
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        log(f"[FetchExisting] Hata: {e}")
        return []


def update_current_values_for_existing(existing_signals, snapshot_lookup):
    """
    DB'deki tüm underdog sinyallerinin current_* değerlerini güncelle.
    Kriterler karşılanmasa bile güncellenir — ilk tetiklenme sabit, şu anki takip edilir.
    """
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    failed = 0
    not_found = 0
    wh = _headers_write()
    code_map = {
        '1': ('odds1', 'pct1', 'amt1'),
        'X': ('oddsx', 'pctx', 'amtx'),
        '2': ('odds2', 'pct2', 'amt2'),
    }
    for sig in existing_signals:
        match_key = sig.get('match_key', '')
        sel_code = sig.get('selection_code', '')
        row = snapshot_lookup.get(match_key)
        if not row:
            not_found += 1
            continue
        fields = code_map.get(sel_code)
        if not fields:
            continue
        try:
            mk = url_quote(match_key, safe='')
            sc = url_quote(sel_code, safe='')
            patch_url = f"{SUPABASE_URL}/rest/v1/underdog_signals?match_key=eq.{mk}&selection_code=eq.{sc}"
            data = {
                'current_odds': str(row.get(fields[0]) or ''),
                'current_pct': str(row.get(fields[1]) or ''),
                'current_amt': str(row.get(fields[2]) or ''),
                'current_volume': str(row.get('volume') or ''),
                'last_updated_at': now,
            }
            r = requests.patch(patch_url, headers=wh, json=data, timeout=10)
            if r.status_code in (200, 204):
                updated += 1
            else:
                failed += 1
        except Exception as e:
            log(f"[Update] Hata: {e}")
            failed += 1
    if failed and not updated:
        log(f"[SinyalEngine] current_* kolonları yok — migrations/underdog_signals_current_columns.sql çalıştırın.")
    return updated, not_found


def cleanup_low_volume_signals():
    """underdog_signals tablosundan VOLUME_THRESHOLD altındaki eski/hatalı kayıtları sil.
    Eşik 1000'den 2000'e yükseltilmeden önce kaydedilmiş düşük hacimli kayıtları temizler.
    """
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/underdog_signals"
            "?select=match_key,selection_code,volume&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=12)
        if r.status_code != 200:
            return
        rows = r.json()
        to_delete = [
            row for row in rows
            if parse_volume_amt(row.get('volume', '')) < VOLUME_THRESHOLD
        ]
        if not to_delete:
            return
        wh = _headers_write()
        deleted = 0
        for row in to_delete:
            mk = url_quote(row.get('match_key', ''), safe='')
            sc = url_quote(row.get('selection_code', ''), safe='')
            del_url = (
                f"{SUPABASE_URL}/rest/v1/underdog_signals"
                f"?match_key=eq.{mk}&selection_code=eq.{sc}"
            )
            dr = requests.delete(del_url, headers=wh, timeout=10)
            if dr.status_code in (200, 204):
                deleted += 1
        log(f"[Cleanup] {deleted}/{len(to_delete)} düşük hacimli underdog kaydı silindi (eşik: {VOLUME_THRESHOLD:,.0f})")
    except Exception as e:
        log(f"[Cleanup] Hata: {e}")


def run_underdog_scan(snapshots, snapshot_lookup):
    """Underdog Pressure taraması."""
    has_cols = check_columns_exist()
    cleanup_low_volume_signals()
    new_triggers = find_signals(snapshots)
    new_count = save_new_signals(new_triggers, with_current_cols=has_cols) if new_triggers else 0
    if has_cols:
        existing = fetch_existing_signals()
        updated_count, not_found = update_current_values_for_existing(existing, snapshot_lookup)
        log(f"[SinyalEngine] found={len(new_triggers)} inserted={new_count} "
            f"updated={updated_count} (existing={len(existing)} no_snapshot={not_found})")
    else:
        log(f"[SinyalEngine] found={len(new_triggers)} inserted={new_count} updated=0 (migration gerekli)")


# ============================================================
# CONFIRMED MONEY ENGINE
# ============================================================

def check_cm_table_exists():
    """confirmed_money_signals tablosunun mevcut olup olmadığını kontrol et."""
    global _cm_table_verified
    if _cm_table_verified:
        return True
    try:
        url = f"{SUPABASE_URL}/rest/v1/confirmed_money_signals?select=id&limit=1"
        r = requests.get(url, headers=_headers_read(), timeout=8)
        if r.status_code == 200:
            _cm_table_verified = True
            log("[CM] confirmed_money_signals tablosu mevcut")
            return True
        return False
    except Exception:
        return False


def check_cm_v2_table_exists():
    """confirmed_money_v2_signals tablosunun mevcut olup olmadığını kontrol et."""
    global _cm_v2_table_verified
    if _cm_v2_table_verified:
        return True
    try:
        url = f"{SUPABASE_URL}/rest/v1/confirmed_money_v2_signals?select=id&limit=1"
        r = requests.get(url, headers=_headers_read(), timeout=8)
        if r.status_code == 200:
            _cm_v2_table_verified = True
            log("[CMv2] confirmed_money_v2_signals tablosu mevcut")
            return True
        return False
    except Exception:
        return False


def fetch_history_16h():
    """Son 10 saatin tüm snapshot'larını çek, home|away|date bazlı grupla.
    NOT: match_id_hash (UUID) yerine home|away|date anahtarı kullanılır çünkü
    fetch_latest_snapshots() moneyway_1x2'den aynı format anahtarı üretiyor."""
    cutoff = (datetime.now(timezone.utc) - timedelta(hours=10, minutes=5)).isoformat()
    url = (
        f"{SUPABASE_URL}/rest/v1/moneyway_1x2_history"
        f"?select=home,away,date,odds1,oddsx,odds2,pct1,pctx,pct2,volume,scraped_at"
        f"&scraped_at=gte.{cutoff}"
        f"&order=scraped_at.desc&limit=50000"
    )
    r = requests.get(url, headers=_headers_read(), timeout=30)
    if r.status_code != 200:
        log(f"[CM-Fetch] HTTP {r.status_code}: {r.text[:200]}")
        return {}
    rows = r.json()
    history = {}
    for row in rows:
        home = row.get('home', '')
        away = row.get('away', '')
        date = row.get('date', '')
        if not home or not away:
            continue
        h = f"{home}|{away}|{date}"
        if h not in history:
            history[h] = []
        history[h].append(row)
    log(f"[CM-Fetch] {len(history)} maç için 10 saatlik geçmiş çekildi ({len(rows)} satır)")
    return history


def _normalize_mk(mk):
    """Match_key'in tarih kısmını UTC+3'e normalize eder (cooldown kontrol tutarlılığı).
    'home|away|14.Apr 18:45:00' → 'home|away|14.Apr 21:45'
    """
    parts = mk.split('|')
    if len(parts) == 3:
        return f"{parts[0]}|{parts[1]}|{_normalize_date_key(parts[2])}"
    return mk


def fetch_cm_recent_cooldowns():
    """Son CM_COOLDOWN_HOURS saatteki confirmed_money_signals kayıtlarını çek."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=CM_COOLDOWN_HOURS)).isoformat()
        url = (
            f"{SUPABASE_URL}/rest/v1/confirmed_money_signals"
            f"?select=match_key,selection_code"
            f"&created_at=gte.{cutoff}"
            f"&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=10)
        if r.status_code == 200:
            rows = r.json()
            result = set()
            for row in rows:
                mk = row['match_key']
                sc = row['selection_code']
                result.add((mk, sc))
                mk_norm = _normalize_mk(mk)
                if mk_norm != mk:
                    result.add((mk_norm, sc))
            return result
        return set()
    except Exception:
        return set()


def fetch_cm_v2_recent_cooldowns():
    """Son CMV2_COOLDOWN_HOURS saatteki confirmed_money_v2_signals kayıtlarını çek."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=CMV2_COOLDOWN_HOURS)).isoformat()
        url = (
            f"{SUPABASE_URL}/rest/v1/confirmed_money_v2_signals"
            f"?select=match_key,selection_code"
            f"&created_at=gte.{cutoff}"
            f"&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=10)
        if r.status_code == 200:
            rows = r.json()
            result = set()
            for row in rows:
                mk = row['match_key']
                sc = row['selection_code']
                result.add((mk, sc))
                mk_norm = _normalize_mk(mk)
                if mk_norm != mk:
                    result.add((mk_norm, sc))
            return result
        return set()
    except Exception:
        return set()


def _find_ref_snapshot(history, hours=10):
    """Geçmişten tam olarak 'hours' saat öncesine en yakın snapshot'ı döndür.
    Pct veya başka bir kritere BAKMAZ — sadece zamana göre seçer."""
    target = datetime.now(timezone.utc) - timedelta(hours=hours)
    best = None
    best_diff = float('inf')
    for r in history:
        raw = r.get('scraped_at', '')
        if not raw:
            continue
        try:
            t = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            diff = abs((t - target).total_seconds())
            if diff < best_diff:
                best_diff = diff
                best = r
        except Exception:
            pass
    return best


def find_confirmed_money(latest_snapshots, history_by_hash, cooldown_set):
    """Confirmed Money kriterlerini kontrol et.
    Her kriter bağımsız olarak değerlendirilir:
      1. Hacim >= CM_VOLUME_THRESHOLD
      2. Anlık pct > CM_PCT_THRESHOLD
      3. Son CM_STABILITY_SNAPSHOTS ardışık history'de pct > CM_PCT_THRESHOLD
      4. Anlık odds 1.35-2.20 aralığında
      5. Oran düşüşü: tam 10 saat önceki snapshot'a göre >= %4 düşüş (pct'den bağımsız)
    """
    signals = []

    for h, latest in latest_snapshots.items():
        # Kriter 1: Hacim
        if parse_volume_amt(latest.get('volume', '')) < CM_VOLUME_THRESHOLD:
            continue
        match_history = history_by_hash.get(h, [])
        if not match_history:
            continue
        match_history_sorted = sorted(match_history, key=lambda r: r.get('scraped_at', ''), reverse=True)

        for code, label, o_field, p_field in [
            ('1', 'Ev Sahibi',  'odds1', 'pct1'),
            ('X', 'Beraberlik', 'oddsx', 'pctx'),
            ('2', 'Deplasman',  'odds2', 'pct2'),
        ]:
            mk = f"{latest.get('home', '')}|{latest.get('away', '')}|{_normalize_date_key(latest.get('date', ''))}"

            if (mk, code) in cooldown_set:
                continue

            # Kriter 2: Anlık para yüzdesi
            pct_now = parse_odds_pct(latest.get(p_field))
            if pct_now <= CM_PCT_THRESHOLD:
                continue

            # Kriter 3: Stabilite — son N snapshot'ta pct > eşik
            last_snaps = match_history_sorted[:CM_STABILITY_SNAPSHOTS]
            if len(last_snaps) < CM_STABILITY_SNAPSHOTS:
                continue
            if not all(parse_odds_pct(r.get(p_field)) > CM_PCT_THRESHOLD for r in last_snaps):
                continue

            # Kriter 4: Anlık oran aralığı
            odds_0 = parse_odds_pct(latest.get(o_field))
            if not (CM_MIN_ODDS <= odds_0 <= CM_MAX_ODDS):
                continue

            # Kriter 5: Oran düşüşü — tam 10 saat öncesine en yakın snapshot (pct'den bağımsız)
            ref_snap = _find_ref_snapshot(match_history, hours=10)
            if not ref_snap:
                continue
            odds_ref = parse_odds_pct(ref_snap.get(o_field))
            if odds_0 <= 0 or odds_ref <= 0:
                continue
            drop_pct = (odds_ref - odds_0) / odds_ref
            if drop_pct < CM_ODDS_DROP_PCT:
                continue

            signals.append({
                'match_key': mk,
                'home_team': latest.get('home', ''),
                'away_team': latest.get('away', ''),
                'league': latest.get('league', ''),
                'date': latest.get('date', ''),
                'selection_code': code,
                'selection_label': label,
                'odds_16h': str(round(odds_ref, 4)),
                'odds_now': str(round(odds_0, 4)),
                'pct_now': str(round(pct_now, 2)),
                'volume_now': str(int(parse_volume_amt(latest.get('volume', '')))),
                'odds_drop_pct': round(drop_pct * 100, 2),
            })

    return signals


def find_confirmed_money_v2(latest_snapshots, history_by_hash, cooldown_set):
    """Confirmed Money V2 kriterlerini kontrol et (araştırma tabanlı, sıkılaştırılmış).
    V1'den farklar:
      - Pct eşiği: >%80 → ≥%88
      - Oran aralığı: 1.35-2.20 → 1.55-2.20 (kısa oranlar hariç)
      - Oran düşüşü: ≥%4 → ≥%7
      - X (beraberlik) seçimi yoktur (sadece '1' ve '2')
    """
    signals = []

    for h, latest in latest_snapshots.items():
        if parse_volume_amt(latest.get('volume', '')) < CMV2_VOLUME_THRESHOLD:
            continue
        match_history = history_by_hash.get(h, [])
        if not match_history:
            continue
        match_history_sorted = sorted(match_history, key=lambda r: r.get('scraped_at', ''), reverse=True)

        for code, label, o_field, p_field in [
            ('1', 'Ev Sahibi', 'odds1', 'pct1'),
            ('2', 'Deplasman', 'odds2', 'pct2'),
        ]:
            mk = f"{latest.get('home', '')}|{latest.get('away', '')}|{_normalize_date_key(latest.get('date', ''))}"

            if (mk, code) in cooldown_set:
                continue

            pct_now = parse_odds_pct(latest.get(p_field))
            if pct_now < CMV2_PCT_THRESHOLD:
                continue

            last_snaps = match_history_sorted[:CMV2_STABILITY_SNAPSHOTS]
            if len(last_snaps) < CMV2_STABILITY_SNAPSHOTS:
                continue
            if not all(parse_odds_pct(r.get(p_field)) >= CMV2_PCT_THRESHOLD for r in last_snaps):
                continue

            odds_0 = parse_odds_pct(latest.get(o_field))
            if not (CMV2_MIN_ODDS <= odds_0 <= CMV2_MAX_ODDS):
                continue

            ref_snap = _find_ref_snapshot(match_history, hours=10)
            if not ref_snap:
                continue
            odds_ref = parse_odds_pct(ref_snap.get(o_field))
            if odds_0 <= 0 or odds_ref <= 0:
                continue
            drop_pct = (odds_ref - odds_0) / odds_ref
            if drop_pct < CMV2_ODDS_DROP_PCT:
                continue

            signals.append({
                'match_key': mk,
                'home_team': latest.get('home', ''),
                'away_team': latest.get('away', ''),
                'league': latest.get('league', ''),
                'date': latest.get('date', ''),
                'selection_code': code,
                'selection_label': label,
                'odds_16h': str(round(odds_ref, 4)),
                'odds_now': str(round(odds_0, 4)),
                'pct_now': str(round(pct_now, 2)),
                'volume_now': str(int(parse_volume_amt(latest.get('volume', '')))),
                'odds_drop_pct': round(drop_pct * 100, 2),
            })

    return signals


def _betwatch_date_to_iso(date_str):
    """'08.Apr 14:00:00' formatını '2026-04-08' ISO'ya çevirir."""
    try:
        import re as _re
        from datetime import date as _d
        m = _re.search(r'(\d{2})\.(\w{3})', str(date_str))
        if m:
            months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5,
                      'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10,
                      'Nov': 11, 'Dec': 12}
            day = int(m.group(1))
            mon = months.get(m.group(2), 0)
            if mon:
                return _d(_d.today().year, mon, day).isoformat()
    except Exception:
        pass
    return str(date_str)[:10] if date_str else ''


def _betwatch_to_iso_datetime(date_str):
    """'08.Apr 14:00:00' formatını '2026-04-08T14:00' ISO datetime'a çevirir.
    substring(0,10) ile '2026-04-08' verir (admin panel uyumlu).
    str karşılaştırmasında '2026-04-08T14:00' >= '2026-04-08' → True (_is_today_or_future uyumlu).
    _extractKickoffTime ile '14:00' verir (JS saat uyumlu).
    """
    try:
        import re as _re
        from datetime import date as _d
        s = str(date_str)
        m = _re.search(r'(\d{2})\.(\w{3})', s)
        if m:
            months = {'Jan': 1, 'Feb': 2, 'Mar': 3, 'Apr': 4, 'May': 5,
                      'Jun': 6, 'Jul': 7, 'Aug': 8, 'Sep': 9, 'Oct': 10,
                      'Nov': 11, 'Dec': 12}
            day = int(m.group(1))
            mon = months.get(m.group(2).capitalize(), 0)
            if mon:
                iso_date = _d(_d.today().year, mon, day).isoformat()
                t = _re.search(r'(\d{2}):(\d{2})(?::\d{2})?', s)
                if t:
                    return f"{iso_date}T{t.group(1)}:{t.group(2)}:00+03:00"
                return iso_date
    except Exception:
        pass
    return str(date_str)[:10] if date_str else ''


def save_confirmed_money_signals(signals):
    """Yeni Confirmed Money sinyallerini kaydet."""
    if not signals:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for s in signals:
        records.append({
            'match_key': s['match_key'],
            'home_team': s['home_team'],
            'away_team': s['away_team'],
            'league': s['league'],
            'match_date': _betwatch_to_iso_datetime(s['date']),
            'selection_code': s['selection_code'],
            'selection_label': s['selection_label'],
            'odds_16h': s['odds_16h'],
            'odds_now': s['odds_now'],
            'current_odds': s['odds_now'],
            'pct_now': s['pct_now'],
            'current_pct': s['pct_now'],
            'volume_now': s['volume_now'],
            'current_volume': s['volume_now'],
            'odds_drop_pct': s['odds_drop_pct'],
            'created_at': now,
            'last_updated_at': now,
        })
    url = f"{SUPABASE_URL}/rest/v1/confirmed_money_signals"
    headers = _headers_write('return=minimal')
    r = requests.post(url, headers=headers, json=records, timeout=15)
    if r.status_code in (200, 201):
        log(f"[ConfirmedMoney] INSERT OK ({len(records)} yeni sinyal)")
        return len(records)
    log(f"[ConfirmedMoney] INSERT hatası: {r.status_code} {r.text[:200]}")
    return 0


def save_confirmed_money_v2_signals(signals):
    """Yeni Confirmed Money V2 sinyallerini kaydet."""
    if not signals:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for s in signals:
        records.append({
            'match_key': s['match_key'],
            'home_team': s['home_team'],
            'away_team': s['away_team'],
            'league': s['league'],
            'match_date': _betwatch_to_iso_datetime(s['date']),
            'selection_code': s['selection_code'],
            'selection_label': s['selection_label'],
            'odds_16h': s['odds_16h'],
            'odds_now': s['odds_now'],
            'current_odds': s['odds_now'],
            'pct_now': s['pct_now'],
            'current_pct': s['pct_now'],
            'volume_now': s['volume_now'],
            'current_volume': s['volume_now'],
            'odds_drop_pct': s['odds_drop_pct'],
            'created_at': now,
            'last_updated_at': now,
        })
    url = f"{SUPABASE_URL}/rest/v1/confirmed_money_v2_signals"
    headers = _headers_write('return=minimal')
    r = requests.post(url, headers=headers, json=records, timeout=15)
    if r.status_code in (200, 201):
        log(f"[CMv2] INSERT OK ({len(records)} yeni sinyal)")
        return len(records)
    log(f"[CMv2] INSERT hatası: {r.status_code} {r.text[:200]}")
    return 0


def fetch_existing_cm_v2_signals():
    """DB'deki mevcut confirmed_money_v2_signals listesini çek."""
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/confirmed_money_v2_signals"
            "?select=match_key,selection_code,home_team,away_team,match_date"
            "&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=12)
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        log(f"[CMv2-FetchExisting] Hata: {e}")
        return []


def fetch_existing_cm_signals():
    """DB'deki mevcut confirmed_money_signals listesini çek."""
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/confirmed_money_signals"
            "?select=match_key,selection_code,home_team,away_team,match_date,odds_now"
            "&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=12)
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        log(f"[CM-FetchExisting] Hata: {e}")
        return []


def delete_invalid_cm_signals(invalid_signals):
    """Geçersizleşen Confirmed Money sinyallerini DB'den sil.
    Geçersizlik koşulu: 10 saat önceki orana göre mevcut düşüş CM_ODDS_DROP_PCT eşiğinin altında."""
    if not invalid_signals:
        return 0
    deleted = 0
    wh = _headers_write()
    for sig in invalid_signals:
        try:
            mk = sig.get('match_key', '')
            sc = sig.get('selection_code', '')
            mk_enc = url_quote(mk, safe='')
            sc_enc = url_quote(sc, safe='')
            del_url = f"{SUPABASE_URL}/rest/v1/confirmed_money_signals?match_key=eq.{mk_enc}&selection_code=eq.{sc_enc}"
            r = requests.delete(del_url, headers=wh, timeout=10)
            if r.status_code in (200, 204):
                deleted += 1
                log(f"[CM-Invalidate] Silindi: {sig.get('home_team')} vs {sig.get('away_team')} [{sc}] — düşüş eşiğin altına düştü")
        except Exception as e:
            log(f"[CM-Invalidate] Hata: {e}")
    return deleted


def delete_invalid_cm_v2_signals(invalid_signals):
    """Geçersizleşen Confirmed Money V2 sinyallerini DB'den sil.
    Geçersizlik koşulu: güncel 10 saatlik referansa göre mevcut düşüş CMV2_ODDS_DROP_PCT eşiğinin altında."""
    if not invalid_signals:
        return 0
    deleted = 0
    wh = _headers_write()
    for sig in invalid_signals:
        try:
            mk = sig.get('match_key', '')
            sc = sig.get('selection_code', '')
            mk_enc = url_quote(mk, safe='')
            sc_enc = url_quote(sc, safe='')
            del_url = f"{SUPABASE_URL}/rest/v1/confirmed_money_v2_signals?match_key=eq.{mk_enc}&selection_code=eq.{sc_enc}"
            r = requests.delete(del_url, headers=wh, timeout=10)
            if r.status_code in (200, 204):
                deleted += 1
                log(f"[CMv2-Invalidate] Silindi: {sig.get('home_team')} vs {sig.get('away_team')} [{sc}] — düşüş eşiğin altına düştü")
        except Exception as e:
            log(f"[CMv2-Invalidate] Hata: {e}")
    return deleted


def update_cm_current_values(existing_cm, snapshot_lookup):
    """
    DB'deki tüm CM sinyallerinin current_* değerlerini güncelle.
    Kriterler karşılanmasa bile güncellenir.
    """
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    not_found = 0
    wh = _headers_write()
    code_map = {
        '1': ('odds1', 'pct1'),
        'X': ('oddsx', 'pctx'),
        '2': ('odds2', 'pct2'),
    }
    for sig in existing_cm:
        mk = sig.get('match_key', '')
        sc = sig.get('selection_code', '')
        row = snapshot_lookup.get(mk)
        if not row:
            not_found += 1
            continue
        fields = code_map.get(sc)
        if not fields:
            continue
        try:
            mk_enc = url_quote(mk, safe='')
            sc_enc = url_quote(sc, safe='')
            patch_url = f"{SUPABASE_URL}/rest/v1/confirmed_money_signals?match_key=eq.{mk_enc}&selection_code=eq.{sc_enc}"
            data = {
                'current_odds': str(row.get(fields[0]) or ''),
                'current_pct': str(row.get(fields[1]) or ''),
                'current_volume': str(row.get('volume') or ''),
                'last_updated_at': now,
            }
            raw_date = row.get('date', '')
            existing_date = sig.get('match_date', '')
            if raw_date and ':' in raw_date and len(existing_date) <= 10:
                data['match_date'] = _betwatch_to_iso_datetime(raw_date)
            r = requests.patch(patch_url, headers=wh, json=data, timeout=10)
            if r.status_code in (200, 204):
                updated += 1
        except Exception as e:
            log(f"[CM-Update] Hata: {e}")
    return updated, not_found


def run_cm_scan(snapshots, snapshot_lookup):
    """Confirmed Money taraması."""
    if not check_cm_table_exists():
        log(f"[ConfirmedMoney] Tablo yok — migrations/create_confirmed_money_signals.sql çalıştırın")
        return
    try:
        history = fetch_history_16h()
        cooldown_set = fetch_cm_recent_cooldowns()
        signals = find_confirmed_money(snapshots, history, cooldown_set)

        # Önce DB'deki mevcut kayıtları çek
        existing_cm = fetch_existing_cm_signals()

        # (home_team, away_team, selection_code) üçlüsüne göre var olanları belirle
        existing_keys = {
            (r.get('home_team', '').strip().lower(),
             r.get('away_team', '').strip().lower(),
             r.get('selection_code', ''))
            for r in existing_cm
        }

        # Sadece DB'de olmayan sinyalleri kaydet (duplicate önleme)
        new_signals = [
            s for s in signals
            if (s.get('home_team', '').strip().lower(),
                s.get('away_team', '').strip().lower(),
                s.get('selection_code', '')) not in existing_keys
        ]

        inserted = save_confirmed_money_signals(new_signals) if new_signals else 0

        # Mevcut tüm CM kayıtlarının current_* değerlerini güncelle
        cm_updated, cm_not_found = update_cm_current_values(existing_cm, snapshot_lookup)

        # Geçersizleşen sinyalleri tespit et ve sil:
        # Anlık oran, 10 saat önceki orana göre artık yeterli düşüşü göstermiyorsa → sil
        code_map_cm = {'1': 'odds1', 'X': 'oddsx', '2': 'odds2'}
        invalid_cm = []
        for sig in existing_cm:
            mk = sig.get('match_key', '')
            sc = sig.get('selection_code', '')
            o_field = code_map_cm.get(sc)
            if not o_field:
                continue
            row = snapshot_lookup.get(mk)
            if not row:
                continue
            match_history = history.get(mk, [])
            ref_snap = _find_ref_snapshot(match_history, hours=10)
            if not ref_snap:
                continue
            try:
                odds_ref = parse_odds_pct(ref_snap.get(o_field))
                odds_cur = parse_odds_pct(row.get(o_field))
                if odds_ref <= 0 or odds_cur <= 0:
                    continue
                drop_pct = (odds_ref - odds_cur) / odds_ref
                if drop_pct < CM_ODDS_DROP_PCT:
                    invalid_cm.append(sig)
            except Exception:
                continue

        cm_deleted = delete_invalid_cm_signals(invalid_cm)
        log(f"[ConfirmedMoney] found={len(signals)} new={len(new_signals)} inserted={inserted} "
            f"updated={cm_updated} deleted_invalid={cm_deleted} (existing={len(existing_cm)} no_snapshot={cm_not_found})")
    except Exception as e:
        log(f"[ConfirmedMoney] Tarama hatası: {e}")
        import traceback
        traceback.print_exc()


def run_cm_v2_scan(snapshots, snapshot_lookup):
    """Confirmed Money V2 taraması (araştırma tabanlı, sıkılaştırılmış kriterler)."""
    if not check_cm_v2_table_exists():
        log(f"[CMv2] Tablo yok — CMV2_MIGRATION_SQL çalıştırın")
        return
    try:
        history = fetch_history_16h()
        cooldown_set_v2 = fetch_cm_v2_recent_cooldowns()
        signals = find_confirmed_money_v2(snapshots, history, cooldown_set_v2)

        existing_v2 = fetch_existing_cm_v2_signals()

        existing_keys = {
            (r.get('home_team', '').strip().lower(),
             r.get('away_team', '').strip().lower(),
             r.get('selection_code', ''))
            for r in existing_v2
        }

        new_signals = [
            s for s in signals
            if (s.get('home_team', '').strip().lower(),
                s.get('away_team', '').strip().lower(),
                s.get('selection_code', '')) not in existing_keys
        ]

        inserted = save_confirmed_money_v2_signals(new_signals) if new_signals else 0

        # Geçersizleşen CMv2 sinyallerini tespit et ve sil:
        # Güncel 10 saatlik referansa göre düşüş eşiği artık sağlanmıyorsa → sil
        code_map_v2 = {'1': 'odds1', '2': 'odds2'}
        invalid_v2 = []
        for sig in existing_v2:
            mk = sig.get('match_key', '')
            sc = sig.get('selection_code', '')
            o_field = code_map_v2.get(sc)
            if not o_field:
                continue
            row = snapshot_lookup.get(mk)
            if not row:
                continue
            match_history = history.get(mk, [])
            ref_snap = _find_ref_snapshot(match_history, hours=10)
            if not ref_snap:
                continue
            try:
                odds_ref = parse_odds_pct(ref_snap.get(o_field))
                odds_cur = parse_odds_pct(row.get(o_field))
                if odds_ref <= 0 or odds_cur <= 0:
                    continue
                drop_pct = (odds_ref - odds_cur) / odds_ref
                if drop_pct < CMV2_ODDS_DROP_PCT:
                    invalid_v2.append(sig)
            except Exception:
                continue

        v2_deleted = delete_invalid_cm_v2_signals(invalid_v2)
        log(f"[CMv2] found={len(signals)} new={len(new_signals)} inserted={inserted} "
            f"deleted_invalid={v2_deleted} (existing={len(existing_v2)})")
    except Exception as e:
        log(f"[CMv2] Tarama hatası: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# FAKE SHARP ENGINE
# ============================================================


def check_fs_table_exists():
    """fake_sharp_signals tablosunun mevcut olup olmadığını kontrol et."""
    global _fs_table_verified
    if _fs_table_verified:
        return True
    try:
        url = f"{SUPABASE_URL}/rest/v1/fake_sharp_signals?select=id&limit=1"
        r = requests.get(url, headers=_headers_read(), timeout=8)
        if r.status_code == 200:
            _fs_table_verified = True
            log("[FS] fake_sharp_signals tablosu mevcut")
            return True
        return False
    except Exception:
        return False


def fetch_fs_cooldown():
    """Son FS_COOLDOWN_HOURS saatteki fake_sharp_signals kayıtlarını çek."""
    try:
        cutoff = (datetime.now(timezone.utc) - timedelta(hours=FS_COOLDOWN_HOURS)).isoformat()
        url = (
            f"{SUPABASE_URL}/rest/v1/fake_sharp_signals"
            f"?select=match_key,selection_code"
            f"&created_at=gte.{cutoff}"
            f"&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=10)
        if r.status_code == 200:
            rows = r.json()
            result = set()
            for row in rows:
                mk = row['match_key']
                sc = row['selection_code']
                result.add((mk, sc))
                mk_norm = _normalize_mk(mk)
                if mk_norm != mk:
                    result.add((mk_norm, sc))
            return result
        return set()
    except Exception:
        return set()


def find_fake_sharp(latest_snapshots, history_by_hash, cooldown_set):
    """Fake Sharp kriterlerini kontrol et.
    Her kriter bağımsız olarak değerlendirilir:
      1. Hacim >= FS_VOLUME_THRESHOLD
      2. Anlık pct > FS_PCT_THRESHOLD
      3. Son FS_STABILITY_SNAPSHOTS ardışık history'de pct > FS_PCT_THRESHOLD
      4. Anlık odds 1.35-2.20 aralığında
      5. Oran yükselişi: tam 10 saat önceki snapshot'a göre >= %4 yükseliş (pct'den bağımsız)
    CM'in tam tersi: pct yüksekken oran da yükselmişse sahte sharp baskısı."""
    signals = []

    for h, latest in latest_snapshots.items():
        # Kriter 1: Hacim
        if parse_volume_amt(latest.get('volume', '')) < FS_VOLUME_THRESHOLD:
            continue
        match_history = history_by_hash.get(h, [])
        if not match_history:
            continue
        match_history_sorted = sorted(match_history, key=lambda r: r.get('scraped_at', ''), reverse=True)

        for code, label, o_field, p_field in [
            ('1', 'Ev Sahibi', 'odds1', 'pct1'),
            ('2', 'Deplasman', 'odds2', 'pct2'),
        ]:
            mk = f"{latest.get('home', '')}|{latest.get('away', '')}|{_normalize_date_key(latest.get('date', ''))}"

            if (mk, code) in cooldown_set:
                continue

            # Kriter 2: Anlık para yüzdesi
            pct_now = parse_odds_pct(latest.get(p_field))
            if pct_now <= FS_PCT_THRESHOLD:
                continue

            # Kriter 3: Stabilite — son N snapshot'ta pct > eşik
            last_snaps = match_history_sorted[:FS_STABILITY_SNAPSHOTS]
            if len(last_snaps) < FS_STABILITY_SNAPSHOTS:
                continue
            if not all(parse_odds_pct(r.get(p_field)) > FS_PCT_THRESHOLD for r in last_snaps):
                continue

            # Kriter 4: Anlık oran aralığı
            odds_0 = parse_odds_pct(latest.get(o_field))
            if not (FS_MIN_ODDS <= odds_0 <= FS_MAX_ODDS):
                continue

            # Kriter 5: Oran yükselişi — tam 10 saat öncesine en yakın snapshot (pct'den bağımsız)
            ref_snap = _find_ref_snapshot(match_history, hours=10)
            if not ref_snap:
                continue
            odds_ref = parse_odds_pct(ref_snap.get(o_field))
            if odds_0 <= 0 or odds_ref <= 0:
                continue
            rise_pct = (odds_0 - odds_ref) / odds_ref
            if rise_pct < FS_ODDS_RISE_PCT:
                continue

            signals.append({
                'match_key': mk,
                'home_team': latest.get('home', ''),
                'away_team': latest.get('away', ''),
                'league': latest.get('league', ''),
                'date': latest.get('date', ''),
                'selection_code': code,
                'selection_label': label,
                'odds_16h': str(round(odds_ref, 4)),
                'odds_now': str(round(odds_0, 4)),
                'pct_now': str(round(pct_now, 2)),
                'volume_now': str(int(parse_volume_amt(latest.get('volume', '')))),
                'odds_rise_pct': round(rise_pct * 100, 2),
            })

    return signals


def save_fake_sharp_signals(signals):
    """Yeni Fake Sharp sinyallerini kaydet."""
    if not signals:
        return 0
    now = datetime.now(timezone.utc).isoformat()
    records = []
    for s in signals:
        records.append({
            'match_key': s['match_key'],
            'home_team': s['home_team'],
            'away_team': s['away_team'],
            'league': s['league'],
            'match_date': _betwatch_to_iso_datetime(s['date']),
            'selection_code': s['selection_code'],
            'selection_label': s['selection_label'],
            'odds_16h': s['odds_16h'],
            'odds_now': s['odds_now'],
            'current_odds': s['odds_now'],
            'pct_now': s['pct_now'],
            'current_pct': s['pct_now'],
            'volume_now': s['volume_now'],
            'current_volume': s['volume_now'],
            'odds_rise_pct': s['odds_rise_pct'],
            'created_at': now,
            'last_updated_at': now,
        })
    url = f"{SUPABASE_URL}/rest/v1/fake_sharp_signals"
    headers = _headers_write('return=minimal')
    r = requests.post(url, headers=headers, json=records, timeout=15)
    if r.status_code in (200, 201):
        log(f"[FakeSharp] INSERT OK ({len(records)} yeni sinyal)")
        return len(records)
    log(f"[FakeSharp] INSERT hatası: {r.status_code} {r.text[:200]}")
    return 0


def fetch_existing_fs_signals():
    """DB'deki mevcut fake_sharp_signals listesini çek."""
    try:
        url = (
            f"{SUPABASE_URL}/rest/v1/fake_sharp_signals"
            "?select=match_key,selection_code,home_team,away_team,match_date,odds_16h"
            "&limit=5000"
        )
        r = requests.get(url, headers=_headers_read(), timeout=12)
        if r.status_code == 200:
            return r.json()
        return []
    except Exception as e:
        log(f"[FS-FetchExisting] Hata: {e}")
        return []


def delete_invalid_fs_signals(invalid_signals):
    """Geçersizleşen Fake Sharp sinyallerini DB'den sil.
    Geçersizlik koşulu: mevcut oran yükselişi artık FS_ODDS_RISE_PCT eşiğinin altında."""
    if not invalid_signals:
        return 0
    deleted = 0
    wh = _headers_write()
    for sig in invalid_signals:
        try:
            mk = sig.get('match_key', '')
            sc = sig.get('selection_code', '')
            mk_enc = url_quote(mk, safe='')
            sc_enc = url_quote(sc, safe='')
            del_url = f"{SUPABASE_URL}/rest/v1/fake_sharp_signals?match_key=eq.{mk_enc}&selection_code=eq.{sc_enc}"
            r = requests.delete(del_url, headers=wh, timeout=10)
            if r.status_code in (200, 204):
                deleted += 1
                log(f"[FS-Invalidate] Silindi: {sig.get('home_team')} vs {sig.get('away_team')} [{sc}] — yükseliş eşiğin altına düştü")
        except Exception as e:
            log(f"[FS-Invalidate] Hata: {e}")
    return deleted


def update_fs_current_odds(existing_fs, snapshot_lookup):
    """DB'deki tüm FS sinyallerinin current_* değerlerini güncelle."""
    now = datetime.now(timezone.utc).isoformat()
    updated = 0
    not_found = 0
    wh = _headers_write()
    code_map = {
        '1': ('odds1', 'pct1'),
        '2': ('odds2', 'pct2'),
    }
    for sig in existing_fs:
        mk = sig.get('match_key', '')
        sc = sig.get('selection_code', '')
        row = snapshot_lookup.get(mk)
        if not row:
            not_found += 1
            continue
        fields = code_map.get(sc)
        if not fields:
            continue
        try:
            mk_enc = url_quote(mk, safe='')
            sc_enc = url_quote(sc, safe='')
            patch_url = f"{SUPABASE_URL}/rest/v1/fake_sharp_signals?match_key=eq.{mk_enc}&selection_code=eq.{sc_enc}"
            data = {
                'current_odds': str(row.get(fields[0]) or ''),
                'current_pct': str(row.get(fields[1]) or ''),
                'current_volume': str(row.get('volume') or ''),
                'last_updated_at': now,
            }
            raw_date = row.get('date', '')
            existing_date = sig.get('match_date', '')
            if raw_date and ':' in raw_date and len(existing_date) <= 10:
                data['match_date'] = _betwatch_to_iso_datetime(raw_date)
            r = requests.patch(patch_url, headers=wh, json=data, timeout=10)
            if r.status_code in (200, 204):
                updated += 1
        except Exception as e:
            log(f"[FS-Update] Hata: {e}")
    return updated, not_found


def run_fs_scan(snapshots, snapshot_lookup):
    """Fake Sharp taraması."""
    if not check_fs_table_exists():
        log("[FakeSharp] Tablo yok — migrations/create_fake_sharp_signals.sql çalıştırın")
        return
    try:
        history = fetch_history_16h()
        cooldown_set = fetch_fs_cooldown()
        signals = find_fake_sharp(snapshots, history, cooldown_set)

        existing_fs = fetch_existing_fs_signals()

        existing_keys = {
            (r.get('home_team', '').strip().lower(),
             r.get('away_team', '').strip().lower(),
             r.get('selection_code', ''))
            for r in existing_fs
        }

        new_signals = [
            s for s in signals
            if (s.get('home_team', '').strip().lower(),
                s.get('away_team', '').strip().lower(),
                s.get('selection_code', '')) not in existing_keys
        ]

        inserted = save_fake_sharp_signals(new_signals) if new_signals else 0

        fs_updated, fs_not_found = update_fs_current_odds(existing_fs, snapshot_lookup)

        # Geçersizleşen sinyalleri tespit et ve sil:
        # Güncel 10 saatlik referansa göre mevcut oran yükselişi eşiğin altına düştüyse → sil
        code_map = {'1': 'odds1', '2': 'odds2'}
        invalid_fs = []
        for sig in existing_fs:
            mk = sig.get('match_key', '')
            sc = sig.get('selection_code', '')
            o_field = code_map.get(sc)
            if not o_field:
                continue
            row = snapshot_lookup.get(mk)
            if not row:
                continue
            match_history = history.get(mk, [])
            ref_snap = _find_ref_snapshot(match_history, hours=10)
            if not ref_snap:
                continue
            try:
                odds_ref = parse_odds_pct(ref_snap.get(o_field))
                odds_cur = parse_odds_pct(row.get(o_field))
                if odds_ref <= 0 or odds_cur <= 0:
                    continue
                rise_pct = (odds_cur - odds_ref) / odds_ref
                if rise_pct < FS_ODDS_RISE_PCT:
                    invalid_fs.append(sig)
            except Exception:
                continue

        fs_deleted = delete_invalid_fs_signals(invalid_fs)
        log(f"[FakeSharp] found={len(signals)} new={len(new_signals)} inserted={inserted} "
            f"updated={fs_updated} deleted_invalid={fs_deleted} (existing={len(existing_fs)} no_snapshot={fs_not_found})")
    except Exception as e:
        log(f"[FakeSharp] Tarama hatası: {e}")
        import traceback
        traceback.print_exc()


# ============================================================
# MAIN SCAN + ENGINE LOOP
# ============================================================

def run_scan():
    log("[SinyalEngine] Tarama başlıyor...")
    snapshots = fetch_latest_snapshots()
    if not snapshots:
        log("[SinyalEngine] Veri çekilemedi, tarama atlandı")
        return
    snapshot_lookup = build_snapshot_lookup(snapshots)
    run_underdog_scan(snapshots, snapshot_lookup)
    run_cm_scan(snapshots, snapshot_lookup)
    run_cm_v2_scan(snapshots, snapshot_lookup)
    run_fs_scan(snapshots, snapshot_lookup)


def run_engine():
    print("=" * 60)
    print("SMARTXFLOW SİNYAL ENGINE v1.3")
    print(f"Tarama aralığı  : {SCAN_INTERVAL // 60} dakika")
    print(f"[Underdog]      : odds>={ODDS_THRESHOLD}, pct>={PCT_THRESHOLD}%, vol>={VOLUME_THRESHOLD:,.0f}")
    print(f"[ConfirmedMoney]: pct>{CM_PCT_THRESHOLD}%, düsüş>={CM_ODDS_DROP_PCT*100:.0f}%, vol>={CM_VOLUME_THRESHOLD:,.0f}, cooldown={CM_COOLDOWN_HOURS}sa")
    print(f"[CMv2]          : pct>={CMV2_PCT_THRESHOLD}%, düşüş>={CMV2_ODDS_DROP_PCT*100:.0f}%, oran={CMV2_MIN_ODDS}-{CMV2_MAX_ODDS}, vol>={CMV2_VOLUME_THRESHOLD:,.0f}")
    print(f"[FakeSharp]     : pct>{FS_PCT_THRESHOLD}%, yükseliş>={FS_ODDS_RISE_PCT*100:.0f}%, vol>={FS_VOLUME_THRESHOLD:,.0f}, cooldown={FS_COOLDOWN_HOURS}sa")
    print(f"Supabase URL    : {SUPABASE_URL[:40]}..." if SUPABASE_URL else "Supabase URL: NOT SET")
    print("=" * 60)

    if not SUPABASE_URL or not SUPABASE_ANON_KEY:
        log("[FATAL] SUPABASE_URL veya SUPABASE_ANON_KEY ayarlanmamış!")
        sys.exit(1)

    if not check_columns_exist():
        print("\n" + "=" * 60)
        print("UYARI: underdog_signals current_* kolonları yok.")
        print(MIGRATION_SQL)
        print("=" * 60 + "\n")

    if not check_cm_table_exists():
        print("\n" + "=" * 60)
        print("UYARI: confirmed_money_signals tablosu yok.")
        print(CM_MIGRATION_SQL)
        print("Engine migration olmadan da çalışmaya devam eder.")
        print("=" * 60 + "\n")

    if not check_cm_v2_table_exists():
        print("\n" + "=" * 60)
        print("UYARI: confirmed_money_v2_signals tablosu yok.")
        print(CMV2_MIGRATION_SQL)
        print("Engine migration olmadan da çalışmaya devam eder.")
        print("=" * 60 + "\n")

    if not check_fs_table_exists():
        print("\n" + "=" * 60)
        print("UYARI: fake_sharp_signals tablosu yok.")
        print("migrations/create_fake_sharp_signals.sql çalıştırın.")
        print("Engine migration olmadan da çalışmaya devam eder.")
        print("=" * 60 + "\n")

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
