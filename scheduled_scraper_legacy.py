#!/usr/bin/env python3
"""
SmartXFlow Scheduled Scraper
Replit Scheduled Deployment için prematch scraper runtime'i.
MEVCUT ÇALIŞAN SCRAPER'I KULLANIR.
"""
import os
import sys
import time
import requests
from datetime import datetime, timezone
from typing import Optional
import traceback

try:
    import fcntl
except ImportError:  # pragma: no cover - Replit runtime is Linux
    fcntl = None

# standalone_scraper modülünü import et (SupabaseWriter + cleanup için)
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'scraper_standalone'))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'desktop', 'scraper_standalone'))
import standalone_scraper as ss_module
from standalone_scraper import SupabaseWriter, cleanup_old_matches
from betwatch_prematch import run_scrape_betwatch as run_scrape
from core.retention_guard import retention_cleanup_disabled

print("[Source] Veri kaynağı: Betwatch API v1 (/football/prematch)")

MAX_RETRIES = 3
RETRY_DELAYS = [30, 60, 90]
PREMATCH_INTERVAL_MINUTES = 5
PREMATCH_INTERVAL_SECONDS = PREMATCH_INTERVAL_MINUTES * 60
PREMATCH_WATCHDOG_MINUTES = 12
PREMATCH_WATCHDOG_SECONDS = PREMATCH_WATCHDOG_MINUTES * 60
PREMATCH_FAILURE_RETRY_SECONDS = 60
PREMATCH_MASTER_LEASE_MINUTES = 7
SCRAPER_SOURCE = (
    os.environ.get("SMARTXFLOW_SCRAPER_SOURCE")
    or ("replit-preview" if (os.environ.get("REPL_ID") or os.environ.get("REPL_SLUG") or os.environ.get("REPL_OWNER")) else "replit")
)
SIGNAL_DEDUP_WINDOW_SECONDS = 120
EXTERNAL_MASTER_WINDOW_SECONDS = int(
    os.environ.get(
        "SMARTXFLOW_EXTERNAL_MASTER_WINDOW_SECONDS",
        str(PREMATCH_MASTER_LEASE_MINUTES * 60),
    )
)
_SIGNAL_LOCK_PATH = "/tmp/smartxflow_scraper_signal.lock"
_HEARTBEAT_TABLE_AVAILABLE = None
_HEARTBEAT_MISSING_LOGGED = False
_PREMATCH_MASTER_STATUSES = {"starting", "active", "active_degraded"}
_NON_PREMATCH_HEARTBEAT_SOURCES = {"alarm_engine", "sinyal_engine"}


def _heartbeat_table_missing(response) -> bool:
    text = getattr(response, "text", "") or ""
    return response.status_code == 404 and (
        "scraper_heartbeat" in text or "PGRST205" in text
    )


def _log_heartbeat_missing_once() -> None:
    global _HEARTBEAT_MISSING_LOGGED
    if not _HEARTBEAT_MISSING_LOGGED:
        print("[Heartbeat] scraper_heartbeat yok; scraper_signal tabanlı liveness fallback aktif")
        _HEARTBEAT_MISSING_LOGGED = True


def _is_prematch_source(source: str) -> bool:
    """Prematch election/watchdog kapsamındaki scraper source'larını ayır.

    scraper_heartbeat tablosu prematch, live ve engine heartbeat'lerini aynı yerde
    tutuyor. Prematch master seçimi yalnız prematch scraper instance'ları arasında
    yapılmalı; live scraper veya engine heartbeat'i prematch'i standby'a itemez.
    """
    value = str(source or "").strip().lower()
    if not value:
        return False
    if value in _NON_PREMATCH_HEARTBEAT_SOURCES:
        return False
    if value.endswith("-live") or "-live-" in value or value.startswith("live-"):
        return False
    return True


def _check_master_from_signals(supabase_url: str, supabase_key: str) -> tuple:
    """Heartbeat tablosu yoksa son prematch scrape_complete sinyalinden master koruması."""
    try:
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }
        url = (
            f"{supabase_url}/rest/v1/scraper_signal"
            f"?signal_type=eq.scrape_complete"
            f"&source=neq.{SCRAPER_SOURCE}"
            f"&order=created_at.desc&limit=20&select=source,created_at"
        )
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            return True, f"signal_fallback_http_{r.status_code}"
        rows = r.json()
        if not rows:
            return True, "signal_fallback_no_external_master"

        now = datetime.now(timezone.utc)
        saw_prematch = False
        for row in rows:
            source = str(row.get("source") or "")
            if not _is_prematch_source(source):
                continue
            saw_prematch = True
            raw = str(row.get("created_at") or "")
            if not raw:
                continue
            beat_time = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if beat_time.tzinfo is None:
                beat_time = beat_time.replace(tzinfo=timezone.utc)
            diff_seconds = (now - beat_time.astimezone(timezone.utc)).total_seconds()
            diff_minutes = diff_seconds / 60
            if 0 <= diff_seconds < EXTERNAL_MASTER_WINDOW_SECONDS:
                return False, f"{source or 'external'} recent scrape ({diff_minutes:.1f} min ago)"
            # Ordered newest first. The first prematch row is already stale,
            # therefore every older prematch row is stale as well.
            return True, f"signal_fallback_stale ({diff_minutes:.1f} min ago)"

        if not saw_prematch:
            return True, "signal_fallback_no_prematch_master"
        return True, "signal_fallback_missing_timestamp"
    except Exception as e:
        print(f"[Master Check] scraper_signal fallback hatası: {e}")
        return True, "signal_fallback_error"


def _is_recent_duplicate_signal(
    supabase_url: str,
    supabase_key: str,
    match_count: int,
    snapshot_count: int,
) -> bool:
    """Herhangi bir prematch scrape_complete çok yeniyse ikinci signal üretimini engelle."""
    try:
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
        }
        url = (
            f"{supabase_url}/rest/v1/scraper_signal"
            f"?signal_type=eq.scrape_complete"
            f"&order=created_at.desc&limit=20"
            f"&select=id,source,created_at,match_count,snapshot_count"
        )
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            print(f"[Signal] Duplicate kontrolü HTTP {r.status_code}; fail-open")
            return False
        rows = r.json()
        if not rows:
            return False
        now = datetime.now(timezone.utc)
        for row in rows:
            if not _is_prematch_source(row.get("source", "")):
                continue
            raw = str(row.get("created_at") or "")
            if not raw:
                continue
            created = datetime.fromisoformat(raw.replace("Z", "+00:00"))
            if created.tzinfo is None:
                created = created.replace(tzinfo=timezone.utc)
            age = (now - created.astimezone(timezone.utc)).total_seconds()
            return 0 <= age <= SIGNAL_DEDUP_WINDOW_SECONDS
        return False
    except Exception as e:
        print(f"[Signal] Duplicate kontrolü hata: {e}; fail-open")
        return False


def send_telegram(message: str, is_error: bool = False) -> bool:
    bot_token = os.environ.get('PAYMENT_BOT_TOKEN')
    chat_id = os.environ.get('PAYMENT_CHAT_ID')

    if not bot_token or not chat_id:
        print("[Telegram] Token veya Chat ID eksik")
        return False

    try:
        emoji = "🔴" if is_error else "🟢"
        url = f'https://api.telegram.org/bot{bot_token}/sendMessage'
        data = {
            'chat_id': chat_id,
            'text': f"{emoji} {message}",
            'parse_mode': 'HTML'
        }
        r = requests.post(url, data=data, timeout=10)
        return r.status_code == 200
    except Exception as e:
        print(f"[Telegram] Hata: {e}")
        return False


def send_alarm_engine_signal(supabase_url: str, supabase_key: str, match_count: int, snapshot_count: int = 0) -> bool:
    """Alarm Engine'e tekil scrape_complete sinyali gönder."""
    lock_handle = None
    try:
        if fcntl is not None:
            lock_handle = open(_SIGNAL_LOCK_PATH, "a+", encoding="utf-8")
            fcntl.flock(lock_handle.fileno(), fcntl.LOCK_EX)

        if _is_recent_duplicate_signal(
            supabase_url,
            supabase_key,
            match_count,
            snapshot_count,
        ):
            print(
                f"[Signal] Duplicate scrape_complete atlandı "
                f"({match_count} maç, {snapshot_count} snapshot)"
            )
            return True

        data = {
            "source": SCRAPER_SOURCE,
            "signal_type": "scrape_complete",
            "match_count": int(match_count),
            "snapshot_count": int(snapshot_count),
            "processed": False
        }

        url = f"{supabase_url}/rest/v1/scraper_signal"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation"
        }

        r = requests.post(url, json=data, headers=headers, timeout=10)
        print(f"[Signal] HTTP {r.status_code}: {r.text[:200]}")
        success = r.status_code in [200, 201] and len(r.text) > 10
        if success:
            print(
                f"[Signal] Alarm Engine'e sinyal gönderildi ✓ "
                f"({match_count} maç, {snapshot_count} snapshot)"
            )
        else:
            print(f"[Signal] Sinyal gönderilemedi - HTTP {r.status_code}")
        return success
    except Exception as e:
        print(f"[Signal] Hata: {e}")
        return False
    finally:
        if lock_handle is not None:
            try:
                if fcntl is not None:
                    fcntl.flock(lock_handle.fileno(), fcntl.LOCK_UN)
            finally:
                lock_handle.close()


def update_heartbeat(supabase_url: str, supabase_key: str, status: str, match_count: int = 0, error_msg: Optional[str] = None) -> bool:
    global _HEARTBEAT_TABLE_AVAILABLE
    if _HEARTBEAT_TABLE_AVAILABLE is False:
        return False
    try:
        now = datetime.now(timezone.utc).isoformat()
        data = {
            "source": SCRAPER_SOURCE,
            "last_heartbeat": now,
            "status": status,
            "match_count": match_count,
            "error_message": error_msg,
            "updated_at": now
        }

        url = f"{supabase_url}/rest/v1/scraper_heartbeat?on_conflict=source"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=representation,resolution=merge-duplicates"
        }

        r = requests.post(url, json=data, headers=headers, timeout=10)
        success = r.status_code in [200, 201]
        if success:
            _HEARTBEAT_TABLE_AVAILABLE = True
            print(f"[Heartbeat] {status} - {match_count} matches ✓")
        elif _heartbeat_table_missing(r):
            _HEARTBEAT_TABLE_AVAILABLE = False
            _log_heartbeat_missing_once()
        else:
            print(f"[Heartbeat] {status} - HTTP {r.status_code}: {r.text[:100]}")
        return success
    except Exception as e:
        print(f"[Heartbeat] Hata: {e}")
        return False


def check_master_status(supabase_url: str, supabase_key: str) -> tuple:
    global _HEARTBEAT_TABLE_AVAILABLE
    if _HEARTBEAT_TABLE_AVAILABLE is False:
        return _check_master_from_signals(supabase_url, supabase_key)
    try:
        url = f"{supabase_url}/rest/v1/scraper_heartbeat?select=*"
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }

        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code != 200:
            if _heartbeat_table_missing(r):
                _HEARTBEAT_TABLE_AVAILABLE = False
                _log_heartbeat_missing_once()
            return _check_master_from_signals(supabase_url, supabase_key)

        _HEARTBEAT_TABLE_AVAILABLE = True
        rows = r.json()
        if not rows:
            return True, "no_master"

        now = datetime.now(timezone.utc)

        for row in rows:
            source = str(row.get("source") or "")
            if source == SCRAPER_SOURCE or not _is_prematch_source(source):
                continue

            last_beat = row.get("last_heartbeat")
            if last_beat:
                from dateutil import parser
                beat_time = parser.parse(last_beat)
                if beat_time.tzinfo is None:
                    beat_time = beat_time.replace(tzinfo=timezone.utc)
                diff_minutes = (now - beat_time).total_seconds() / 60

                if (
                    0 <= diff_minutes < PREMATCH_MASTER_LEASE_MINUTES
                    and str(row.get("status") or "").lower() in _PREMATCH_MASTER_STATUSES
                ):
                    return False, f"{source} is prematch master ({diff_minutes:.1f} min ago)"

        return True, "i_am_master"
    except Exception as e:
        print(f"[Master Check] Hata: {e}; scraper_signal fallback deneniyor")
        return _check_master_from_signals(supabase_url, supabase_key)


def log_callback(message: str):
    print(f"[Scraper] {message}")


def run_with_retry(writer: SupabaseWriter) -> tuple:
    last_error = None

    for attempt in range(MAX_RETRIES):
        try:
            print(f"\n[Scrape] Deneme {attempt + 1}/{MAX_RETRIES}")
            rows = run_scrape(writer, logger_callback=log_callback)

            if rows and rows > 0:
                print(f"[Scrape] Başarılı: {rows} satır yazıldı")
                return rows, None
            else:
                last_error = "Veri çekilemedi veya boş döndü"
                print(f"[Scrape] {last_error}")

        except requests.exceptions.SSLError as e:
            last_error = f"SSL Hatası: {str(e)[:150]}"
            print(f"[Scrape] {last_error}")
        except requests.exceptions.Timeout as e:
            last_error = f"Timeout: {str(e)[:150]}"
            print(f"[Scrape] {last_error}")
        except requests.exceptions.RequestException as e:
            last_error = f"Request Hatası: {str(e)[:150]}"
            print(f"[Scrape] {last_error}")
        except Exception as e:
            last_error = f"Genel Hata: {str(e)[:150]}"
            print(f"[Scrape] {last_error}")
            traceback.print_exc()

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            print(f"[Scrape] {delay} saniye bekleniyor...")
            time.sleep(delay)

    return 0, last_error


def main():
    print("=" * 60)
    print("SmartXFlow Scheduled Scraper (Replit)")
    print(f"Time: {datetime.now(timezone.utc).isoformat()}")
    print("=" * 60)

    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_ANON_KEY')

    if not supabase_url or not supabase_key:
        error_msg = "SUPABASE_URL veya SUPABASE_ANON_KEY eksik!"
        print(f"[FATAL] {error_msg}")
        send_telegram(f"SCRAPER FATAL: {error_msg}", is_error=True)
        return False

    is_master, reason = check_master_status(supabase_url, supabase_key)
    if not is_master:
        print(f"[Master] Başka bir prematch scraper aktif: {reason}")
        print("[Master] Standby modunda, veri yazmıyorum")
        update_heartbeat(supabase_url, supabase_key, "standby", 0, reason)
        # Standby bir scrape değildir. Watchdog success zamanı yalnız gerçek
        # scrape_complete sinyaliyle ilerletilir.
        return False

    print(f"[Master] Ben prematch master oluyorum: {reason}")
    update_heartbeat(supabase_url, supabase_key, "starting", 0)

    try:
        writer = SupabaseWriter(supabase_url, supabase_key)
        print("[Supabase] Writer oluşturuldu")
    except Exception as e:
        error_msg = f"Supabase Writer hatası: {e}"
        print(f"[FATAL] {error_msg}")
        send_telegram(f"SCRAPER FATAL: {error_msg}", is_error=True)
        update_heartbeat(supabase_url, supabase_key, "error", 0, error_msg[:200])
        return False

    rows, error = run_with_retry(writer)
    stats = getattr(writer, "last_scrape_stats", {}) or {}
    match_count = int(stats.get("match_count") or 0)
    snapshot_count = int(stats.get("snapshot_count") or 0)
    if rows > 0 and match_count <= 0:
        print("[Signal] Exact match_count unavailable; row-count fallback kullanılıyor")
        match_count = int(rows)

    signal_ok = False
    if error:
        send_telegram(f"SCRAPER HATA (3 retry sonrası):\n{error}", is_error=True)
        update_heartbeat(supabase_url, supabase_key, "error", match_count, error[:200])
    else:
        history_errors = getattr(writer, "last_write_errors", [])
        if history_errors:
            degraded_msg = "History yazma kısmi hata: " + "; ".join(history_errors[:2])
            print(f"[Scrape] ACTIVE_DEGRADED: {degraded_msg}")
            update_heartbeat(
                supabase_url,
                supabase_key,
                "active_degraded",
                match_count,
                degraded_msg[:500]
            )
        else:
            update_heartbeat(supabase_url, supabase_key, "active", match_count)
        signal_ok = send_alarm_engine_signal(
            supabase_url,
            supabase_key,
            match_count,
            snapshot_count,
        )
        if not signal_ok:
            signal_error = "scrape_complete sinyali gönderilemedi"
            print(f"[Signal] ACTIVE_DEGRADED: {signal_error}")
            update_heartbeat(
                supabase_url,
                supabase_key,
                "active_degraded",
                match_count,
                signal_error,
            )

    print("=" * 60)
    print(
        f"Tamamlandı: {rows} satır | "
        f"{match_count} maç | {snapshot_count} snapshot"
    )
    if error:
        print(f"Son hata: {error}")
    print("=" * 60)

    return error is None and signal_ok


def get_last_signal_time() -> Optional[datetime]:
    """Son gerçek prematch scrape_complete zamanını döndür."""
    try:
        supabase_url = os.environ.get('SUPABASE_URL')
        supabase_key = os.environ.get('SUPABASE_ANON_KEY')
        if not supabase_url or not supabase_key:
            return None
        headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}"
        }
        url = (
            f"{supabase_url}/rest/v1/scraper_signal?signal_type=eq.scrape_complete"
            f"&order=created_at.desc&limit=20&select=source,created_at"
        )
        r = requests.get(url, headers=headers, timeout=10)
        if r.status_code == 200:
            data = r.json()
            for row in data:
                if not _is_prematch_source(row.get("source", "")):
                    continue
                ts = str(row.get('created_at') or '')
                if not ts:
                    continue
                from datetime import datetime as dt
                if ts.endswith('Z'):
                    ts = ts[:-1] + '+00:00'
                parsed = dt.fromisoformat(ts)
                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)
                return parsed.astimezone(timezone.utc)
    except Exception as e:
        print(f"[Loop] Son sinyal zamanı alınamadı: {e}")
    return None


def _seconds_until_next_scrape(
    last_successful_scrape: Optional[datetime],
    now: Optional[datetime] = None,
) -> float:
    """Son gerçek scrape_complete'e göre 5 dakikalık cadence'in kalan süresi."""
    if last_successful_scrape is None:
        return 0.0
    current = now or datetime.now(timezone.utc)
    if current.tzinfo is None:
        current = current.replace(tzinfo=timezone.utc)
    last = last_successful_scrape
    if last.tzinfo is None:
        last = last.replace(tzinfo=timezone.utc)
    elapsed = max(0.0, (current - last.astimezone(timezone.utc)).total_seconds())
    remaining = PREMATCH_INTERVAL_SECONDS - elapsed
    return max(0.0, min(float(PREMATCH_INTERVAL_SECONDS), remaining))


def _try_run_cleanup(supabase_url: str, supabase_key: str, last_cleanup_date_holder: list):
    """Günde 1 kez cleanup_old_matches'i çalıştır (D-8+ siler, son 7 gün korunur).
    last_cleanup_date_holder: [last_date or None] - mutable holder for state."""
    if retention_cleanup_disabled():
        print("[Retention Guard] Scheduled scraper cleanup skipped")
        return
    try:
        today = datetime.now(timezone.utc).date()
        if last_cleanup_date_holder[0] == today:
            return
        writer = SupabaseWriter(supabase_url, supabase_key)
        print(f"[Cleanup] Günlük cleanup başlatılıyor (D-8+ silinecek, son 7 gün korunur)")
        deleted = cleanup_old_matches(writer, logger_callback=lambda m: print(f"[Cleanup] {m}"))
        last_cleanup_date_holder[0] = today
        print(f"[Cleanup] Tamamlandı - {deleted} işlem")
    except Exception as e:
        print(f"[Cleanup] Hata: {e}")
        traceback.print_exc()


def run_loop():
    """5 dakikalık prematch cadence + 12 dk watchdog + guarded günlük cleanup."""
    cleanup_disabled = retention_cleanup_disabled()
    print(f"[Loop] Scraper {PREMATCH_INTERVAL_MINUTES} dakikada bir çalışacak")
    print(
        f"[Watchdog] {PREMATCH_WATCHDOG_MINUTES} dk gerçek scrape_complete "
        "gelmezse Telegram uyarısı gönderilecek"
    )
    if cleanup_disabled:
        print("[Retention Guard] Günlük cleanup DEVRE DIŞI; scraping devam edecek")
    else:
        print(f"[Cleanup] Günlük cleanup aktif (D-8+ silinir, son 7 gün korunur)")

    supabase_url_for_cleanup = None if cleanup_disabled else os.environ.get('SUPABASE_URL')
    supabase_key_for_cleanup = None if cleanup_disabled else os.environ.get('SUPABASE_ANON_KEY')
    last_cleanup_date_holder = [None]

    last_successful_scrape = get_last_signal_time()
    watchdog_alert_sent = False

    startup_delay = _seconds_until_next_scrape(last_successful_scrape)
    if last_successful_scrape and startup_delay > 30:
        elapsed = (
            datetime.now(timezone.utc) - last_successful_scrape.astimezone(timezone.utc)
        ).total_seconds()
        print(
            f"[Loop] Son gerçek scrape {elapsed/60:.1f} dk önce yapılmış, "
            f"{startup_delay/60:.1f} dk bekleniyor..."
        )
        time.sleep(startup_delay)
    elif last_successful_scrape:
        elapsed = (
            datetime.now(timezone.utc) - last_successful_scrape.astimezone(timezone.utc)
        ).total_seconds()
        print(f"[Loop] Son gerçek scrape {elapsed/60:.1f} dk önce, süre dolmuş - hemen çalışıyor")

    while True:
        try:
            main()
        except Exception as e:
            print(f"[Loop] main() hatası: {e}")
            traceback.print_exc()

        # main() return değeri watchdog success değildir. Başarı yalnız DB'de
        # gerçekten oluşmuş yeni prematch scrape_complete ile kanıtlanır.
        received_new_signal = False
        latest_signal = get_last_signal_time()
        if latest_signal and (
            last_successful_scrape is None or latest_signal > last_successful_scrape
        ):
            last_successful_scrape = latest_signal
            received_new_signal = True
            if watchdog_alert_sent:
                send_telegram(
                    "<b>SCRAPER TEKRAR ÇALIŞIYOR</b>\n"
                    "Yeni scrape_complete alındı, prematch veri akışı normale döndü.",
                    is_error=False,
                )
                watchdog_alert_sent = False

        if supabase_url_for_cleanup and supabase_key_for_cleanup:
            _try_run_cleanup(supabase_url_for_cleanup, supabase_key_for_cleanup, last_cleanup_date_holder)

        now = datetime.now(timezone.utc)
        if last_successful_scrape is not None:
            elapsed = (now - last_successful_scrape).total_seconds()
        else:
            elapsed = PREMATCH_WATCHDOG_SECONDS + 1

        if elapsed >= PREMATCH_WATCHDOG_SECONDS and not watchdog_alert_sent:
            elapsed_min = elapsed / 60
            send_telegram(
                f"<b>⚠️ SCRAPER UYARI</b>\n"
                f"Prematch scraper <b>{elapsed_min:.0f} dakikadır</b> gerçek scrape_complete üretmiyor!\n"
                f"Son başarılı: {last_successful_scrape.strftime('%H:%M UTC') if last_successful_scrape else 'Hiç'}",
                is_error=True
            )
            watchdog_alert_sent = True
            print(f"[Watchdog] Telegram uyarısı gönderildi ({elapsed_min:.0f} dk)")

        if received_new_signal:
            sleep_seconds = _seconds_until_next_scrape(last_successful_scrape)
            print(
                f"\n[Loop] Sonraki gerçek scrape hedefi "
                f"{PREMATCH_INTERVAL_MINUTES} dk cadence; "
                f"{sleep_seconds:.0f} sn sonra tekrar kontrol edilecek..."
            )
        else:
            # Başarısız scrape/standby durumunda 5 dakika kör bekleme. Master
            # failover ve recovery daha hızlı olsun; gerçek scrape cadence'i ise
            # yalnız scrape_complete timestamp'i ile ilerler.
            sleep_seconds = PREMATCH_FAILURE_RETRY_SECONDS
            print(
                f"\n[Loop] Yeni scrape_complete yok; "
                f"{sleep_seconds:.0f} sn sonra master/recovery tekrar kontrol edilecek..."
            )
        time.sleep(max(1.0, sleep_seconds))


if __name__ == "__main__":
    run_loop()
