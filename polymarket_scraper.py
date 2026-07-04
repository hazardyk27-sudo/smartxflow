#!/usr/bin/env python3
"""
SmartXFlow Polymarket Trade Ledger Scraper
Her 5 dakikada bir Polymarket'ten CONFIRMED (eslesmis) trade'leri ceker ve
Supabase'e kalici bir ledger (polymarket_trades) olarak biriktirir.

Kritik davranis: Her calisma bir onceki calismanin KALDIGI YERDEN devam eder.
Her (event, market) icin Supabase'deki en son traded_at zaman damgasi checkpoint
olarak okunur; Polymarket Data API'den sadece o zamandan SONRAKI yeni trade'ler
cekilir (tam yeniden tarama yapilmaz). match_phase (prematch/live) trade'in
kendi zaman damgasi ile maçin kickoff zamani kiyaslanarak belirlenir.
"""
import os
import sys
import time
import traceback
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any

import requests

sys.path.insert(0, os.path.dirname(__file__))

from services.polymarket_client import (
    get_today_matches,
    get_event_market_specs,
    _fetch_new_trades,
    _market_selection_side,
)

try:
    SSL_VERIFY = __import__("certifi").where()
except Exception:
    SSL_VERIFY = True

INTERVAL_MINUTES = 5
INTERVAL_SECONDS = INTERVAL_MINUTES * 60
MAX_RETRIES = 3
RETRY_DELAYS = [3, 6, 12]


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f"[Poly {ts}] {msg}", flush=True)


class PolymarketSupabaseWriter:
    def __init__(self, url: str, key: str):
        self.url = url.rstrip('/')
        self.key = key

    def _headers(self) -> Dict[str, str]:
        return {
            "apikey": self.key,
            "Authorization": f"Bearer {self.key}",
            "Content-Type": "application/json",
        }

    def _rest_url(self, table: str) -> str:
        return f"{self.url}/rest/v1/{table}"

    def upsert_match(self, match: Dict[str, Any]) -> bool:
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url('polymarket_matches')}?on_conflict=event_id"
            resp = requests.post(url, headers=headers, json=[match], timeout=15, verify=SSL_VERIFY)
            if resp.status_code not in (200, 201, 204):
                log(f"[Match UPSERT] HTTP {resp.status_code}: {resp.text[:200]}")
                return False
            return True
        except Exception as e:
            log(f"[Match UPSERT] Hata: {e}")
            return False

    def get_last_traded_at(self, condition_id: str) -> Optional[int]:
        """Return the unix timestamp (seconds) of the most recent stored trade
        for this condition_id, or None if no trades stored yet (first fill)."""
        try:
            headers = self._headers()
            url = (
                f"{self._rest_url('polymarket_trades')}"
                f"?condition_id=eq.{condition_id}&select=traded_at&order=traded_at.desc&limit=1"
            )
            resp = requests.get(url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code != 200:
                log(f"[Checkpoint GET] HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            rows = resp.json()
            if not rows:
                return None
            traded_at_str = rows[0].get("traded_at")
            if not traded_at_str:
                return None
            dt = datetime.fromisoformat(traded_at_str.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception as e:
            log(f"[Checkpoint GET] Hata: {e}")
            return None

    def upsert_trades(self, rows: List[Dict[str, Any]]) -> bool:
        if not rows:
            return True
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url('polymarket_trades')}?on_conflict=transaction_hash,wallet,asset,side"
            for i in range(0, len(rows), 500):
                batch = rows[i:i + 500]
                resp = requests.post(url, headers=headers, json=batch, timeout=30, verify=SSL_VERIFY)
                if resp.status_code not in (200, 201, 204):
                    log(f"[Trades UPSERT] HTTP {resp.status_code}: {resp.text[:200]}")
                    return False
            return True
        except Exception as e:
            log(f"[Trades UPSERT] Hata: {e}")
            return False


def _parse_kickoff(kickoff_utc: Optional[str]):
    if not kickoff_utc:
        return None
    try:
        return datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    except Exception:
        return None


def process_match(writer: PolymarketSupabaseWriter, match: Dict[str, Any]) -> int:
    slug = match.get("slug")
    event_id = match.get("event_id")
    kickoff_dt = _parse_kickoff(match.get("kickoff_utc"))
    if not slug or not event_id:
        return 0

    event, specs = get_event_market_specs(slug)
    if not event or not specs:
        return 0

    writer.upsert_match({
        "event_id": event_id,
        "slug": slug,
        "home": match.get("home"),
        "away": match.get("away"),
        "kickoff_utc": match.get("kickoff_utc"),
        "sport": "soccer",
        "last_seen_at": datetime.now(timezone.utc).isoformat(),
    })

    total_new = 0
    for market_type, condition_id, market in specs:
        raw_label = market.get("groupItemTitle") or market.get("question") or ""
        since_ts = writer.get_last_traded_at(condition_id)
        new_trades, truncated = _fetch_new_trades(condition_id, since_ts)
        if truncated:
            log(
                f"  {match.get('home')} vs {match.get('away')} [{market_type}]: "
                f"fetch truncated before reaching checkpoint, skipping this run to avoid "
                f"a permanent gap (will retry fully next cycle)"
            )
            continue
        if not new_trades:
            continue

        rows = []
        for t in reversed(new_trades):
            try:
                ts = int(t.get("timestamp") or 0)
            except (TypeError, ValueError):
                continue
            if ts <= 0:
                continue
            traded_dt = datetime.fromtimestamp(ts, tz=timezone.utc)

            try:
                price = float(t.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            try:
                size = float(t.get("size") or 0)
            except (TypeError, ValueError):
                size = 0.0
            if t.get("usdcSize") is not None:
                try:
                    amount_usdc = float(t.get("usdcSize"))
                except (TypeError, ValueError):
                    amount_usdc = size * price
            else:
                amount_usdc = size * price

            raw_outcome = (t.get("outcome") or "").strip()
            selection, side = _market_selection_side(market_type, raw_label, raw_outcome)

            if kickoff_dt is not None:
                match_phase = "prematch" if traded_dt < kickoff_dt else "live"
            else:
                match_phase = None

            tx_hash = t.get("transactionHash")
            wallet = t.get("proxyWallet")
            if not tx_hash or not wallet:
                continue

            rows.append({
                "transaction_hash": tx_hash,
                "asset": t.get("asset"),
                "wallet": wallet,
                "pseudonym": t.get("pseudonym") or t.get("name") or "",
                "event_id": event_id,
                "condition_id": condition_id,
                "market_type": market_type,
                "selection": selection,
                "side": t.get("side") or side,
                "outcome_raw": raw_outcome,
                "amount_usdc": round(amount_usdc, 4),
                "price": price,
                "size": size,
                "traded_at": traded_dt.isoformat(),
                "match_phase": match_phase,
            })

        if rows and writer.upsert_trades(rows):
            total_new += len(rows)
            log(f"  {match.get('home')} vs {match.get('away')} [{market_type}]: +{len(rows)} yeni trade")

    return total_new


def run_scrape(writer: PolymarketSupabaseWriter) -> int:
    matches = get_today_matches(hours_ahead=None)
    log(f"{len(matches)} mac taraniyor")
    total_new = 0
    for match in matches:
        try:
            total_new += process_match(writer, match)
        except Exception as e:
            log(f"[Match Hata] {match.get('home')} vs {match.get('away')}: {e}")
            traceback.print_exc()
            continue
    log(f"Tarama tamamlandi: {total_new} yeni trade eklendi")
    return total_new


def main() -> bool:
    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_ANON_KEY')
    if not supabase_url or not supabase_key:
        log("HATA: SUPABASE_URL veya SUPABASE_ANON_KEY eksik!")
        return False

    writer = PolymarketSupabaseWriter(supabase_url, supabase_key)

    last_error = None
    for attempt in range(MAX_RETRIES):
        try:
            run_scrape(writer)
            return True
        except Exception as e:
            last_error = str(e)[:200]
            log(f"[HATA] {last_error}")
            traceback.print_exc()

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            log(f"{delay} saniye bekleniyor...")
            time.sleep(delay)

    return False


def run_loop():
    log(f"Polymarket Scraper {INTERVAL_MINUTES} dakikada bir calisacak")
    while True:
        try:
            main()
        except Exception as e:
            log(f"[Loop] main() hatasi: {e}")
            traceback.print_exc()
        log(f"Sonraki calisma {INTERVAL_MINUTES} dakika sonra...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    run_loop()
