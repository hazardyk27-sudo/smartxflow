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
    list_tracked_wallets,
    fetch_wallet_activity,
    fetch_wallet_redeems,
    fetch_wallet_positions,
    _parse_activity_market,
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

    def get_wallet_tracked_since(self, wallet: str) -> Optional[int]:
        """Return unix ts (seconds) of the moment this wallet was added to
        tracked_wallets (created_at), or None if the wallet row can't be
        found. Used as the checkpoint floor on a wallet's FIRST sync so we
        never backfill trades that happened before we started watching it
        (Task #280)."""
        try:
            headers = self._headers()
            url = f"{self._rest_url('tracked_wallets')}?wallet=eq.{wallet}&select=created_at&limit=1"
            resp = requests.get(url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code != 200:
                log(f"[Wallet Tracked-Since GET] HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            rows = resp.json()
            if not rows:
                return None
            created_at_str = rows[0].get("created_at")
            if not created_at_str:
                return None
            dt = datetime.fromisoformat(created_at_str.replace("Z", "+00:00"))
            return int(dt.timestamp())
        except Exception as e:
            log(f"[Wallet Tracked-Since GET] Hata: {e}")
            return None

    def get_wallet_activity_checkpoint(self, wallet: str) -> Optional[int]:
        """Return unix ts (seconds) of the most recent stored activity row for
        this tracked wallet. If nothing is stored yet, fall back to the
        wallet's tracking-start time so the first sync only captures trades
        made SINCE tracking began, instead of backfilling ~10k historical
        trades (Task #280)."""
        try:
            headers = self._headers()
            url = (
                f"{self._rest_url('tracked_wallet_activity')}"
                f"?wallet=eq.{wallet}&select=traded_at&order=traded_at.desc&limit=1"
            )
            resp = requests.get(url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code != 200:
                log(f"[Wallet Checkpoint GET] HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            rows = resp.json()
            if rows:
                traded_at_str = rows[0].get("traded_at")
                if traded_at_str:
                    dt = datetime.fromisoformat(traded_at_str.replace("Z", "+00:00"))
                    return int(dt.timestamp())
            return None
        except Exception as e:
            log(f"[Wallet Checkpoint GET] Hata: {e}")
            return None

    def upsert_wallet_activity(self, rows: List[Dict[str, Any]]) -> bool:
        if not rows:
            return True
        try:
            # Dedup: same conflict key (wallet,tx_hash,asset,side,action) in one
            # batch causes PostgreSQL "ON CONFLICT DO UPDATE cannot affect row
            # twice" — keep only the last occurrence of each key.
            seen: dict = {}
            for row in rows:
                key = (
                    row.get("wallet", ""),
                    row.get("transaction_hash", ""),
                    row.get("asset", ""),
                    row.get("side", ""),
                    row.get("action", ""),
                )
                seen[key] = row
            rows = list(seen.values())

            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url('tracked_wallet_activity')}?on_conflict=wallet,transaction_hash,asset,side,action"
            for i in range(0, len(rows), 500):
                batch = rows[i:i + 500]
                resp = requests.post(url, headers=headers, json=batch, timeout=30, verify=SSL_VERIFY)
                if resp.status_code not in (200, 201, 204):
                    log(f"[Wallet Activity UPSERT] HTTP {resp.status_code}: {resp.text[:200]}")
                    return False
            return True
        except Exception as e:
            log(f"[Wallet Activity UPSERT] Hata: {e}")
            return False

    def get_wallet_redeem_checkpoint(self, wallet: str) -> Optional[int]:
        """Return unix ts (seconds) of the most recent stored REDEEM row for
        this tracked wallet. If nothing is stored yet, fall back to the
        wallet's tracking-start time (same first-sync fix as
        get_wallet_activity_checkpoint - Task #280)."""
        try:
            headers = self._headers()
            url = (
                f"{self._rest_url('tracked_wallet_redeems')}"
                f"?wallet=eq.{wallet}&select=traded_at&order=traded_at.desc&limit=1"
            )
            resp = requests.get(url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code != 200:
                log(f"[Wallet Redeem Checkpoint GET] HTTP {resp.status_code}: {resp.text[:200]}")
                return None
            rows = resp.json()
            if rows:
                traded_at_str = rows[0].get("traded_at")
                if traded_at_str:
                    dt = datetime.fromisoformat(traded_at_str.replace("Z", "+00:00"))
                    return int(dt.timestamp())
            return None
        except Exception as e:
            log(f"[Wallet Redeem Checkpoint GET] Hata: {e}")
            return None

    def upsert_wallet_redeems(self, rows: List[Dict[str, Any]]) -> bool:
        if not rows:
            return True
        try:
            # Dedup by conflict key to prevent PostgreSQL batch conflict error.
            seen: dict = {}
            for row in rows:
                key = (
                    row.get("wallet", ""),
                    row.get("transaction_hash", ""),
                    row.get("condition_id", ""),
                )
                seen[key] = row
            rows = list(seen.values())

            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url('tracked_wallet_redeems')}?on_conflict=wallet,transaction_hash,condition_id"
            for i in range(0, len(rows), 500):
                batch = rows[i:i + 500]
                resp = requests.post(url, headers=headers, json=batch, timeout=30, verify=SSL_VERIFY)
                if resp.status_code not in (200, 201, 204):
                    log(f"[Wallet Redeem UPSERT] HTTP {resp.status_code}: {resp.text[:200]}")
                    return False
            return True
        except Exception as e:
            log(f"[Wallet Redeem UPSERT] Hata: {e}")
            return False

    def replace_wallet_positions(self, wallet: str, rows: List[Dict[str, Any]]) -> bool:
        """Full-sync a wallet's open positions: delete the previous snapshot and
        insert the current one, so closed/redeemed positions disappear."""
        try:
            headers = self._headers()
            del_url = f"{self._rest_url('tracked_wallet_positions')}?wallet=eq.{wallet}"
            resp = requests.delete(del_url, headers=headers, timeout=15, verify=SSL_VERIFY)
            if resp.status_code not in (200, 204):
                log(f"[Wallet Positions DELETE] HTTP {resp.status_code}: {resp.text[:200]}")
                return False
            if not rows:
                return True
            headers["Prefer"] = "resolution=merge-duplicates"
            url = f"{self._rest_url('tracked_wallet_positions')}?on_conflict=wallet,condition_id,asset"
            for i in range(0, len(rows), 500):
                batch = rows[i:i + 500]
                resp = requests.post(url, headers=headers, json=batch, timeout=30, verify=SSL_VERIFY)
                if resp.status_code not in (200, 201, 204):
                    log(f"[Wallet Positions UPSERT] HTTP {resp.status_code}: {resp.text[:200]}")
                    return False
            return True
        except Exception as e:
            log(f"[Wallet Positions SYNC] Hata: {e}")
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


def process_tracked_wallet(writer: PolymarketSupabaseWriter, wallet_row: Dict[str, Any]) -> int:
    """Fully sync one tracked wallet's football activity ledger (incremental,
    checkpoint-based like process_match) and its current open positions
    (full-replace snapshot each cycle)."""
    wallet = (wallet_row.get("wallet") or "").lower()
    if not wallet:
        return 0

    since_ts = writer.get_wallet_activity_checkpoint(wallet)
    new_items, truncated = fetch_wallet_activity(wallet, since_ts)
    if truncated:
        log(f"  [Wallet {wallet[:10]}...] fetch truncated before checkpoint, skipping this run")
    else:
        rows = []
        for item in reversed(new_items):
            try:
                ts = int(item.get("timestamp") or 0)
            except (TypeError, ValueError):
                continue
            if ts <= 0:
                continue
            tx_hash = item.get("transactionHash")
            asset = item.get("asset")
            if not tx_hash or not asset:
                continue

            market_type, home, away, selection, side = _parse_activity_market(item)
            try:
                price = float(item.get("price") or 0)
            except (TypeError, ValueError):
                price = 0.0
            try:
                size = float(item.get("size") or 0)
            except (TypeError, ValueError):
                size = 0.0
            try:
                amount_usdc = float(item.get("usdcSize")) if item.get("usdcSize") is not None else size * price
            except (TypeError, ValueError):
                amount_usdc = size * price

            # `side` = outcome-polarity label (Üst/Alt, Var/Yok, or None for
            # 1x2 where `selection` already IS the team name). `action` = raw
            # BUY/SELL from Polymarket, stored separately so it never gets
            # overwritten by the outcome label (Task #264 bug #2 - previously
            # `side or item.get("side")` clobbered the raw action for
            # non-1x2 markets, and 1x2 rows had their raw action mislabeled
            # as "side").
            rows.append({
                "wallet": wallet,
                "transaction_hash": tx_hash,
                "asset": asset,
                "condition_id": item.get("conditionId"),
                "event_id": None,
                "title": item.get("title"),
                "slug": item.get("slug"),
                "market_type": market_type,
                "selection": selection,
                # NULL is never equal to NULL for UNIQUE constraint purposes in
                # Postgres, so a nullable `side` in the conflict key would let
                # repeated scraper runs insert duplicate 1x2 rows (side is
                # always None for 1x2). Use "" as a non-null sentinel instead.
                "side": side if side is not None else "",
                "action": (item.get("side") or "").strip().upper() or None,
                "outcome_raw": item.get("outcome"),
                "amount_usdc": round(amount_usdc, 4),
                "price": price,
                "size": size,
                "traded_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            })

        if rows and writer.upsert_wallet_activity(rows):
            log(f"  [Wallet {wallet_row.get('nickname')}] +{len(rows)} yeni islem")

    # REDEEM olaylarini kalici olarak biriktir - kazanip nakde cevrilen
    # pozisyonlar /positions'tan tamamen kaybolur, bu yuzden Isabet Orani'nin
    # dogru kalmasi icin redeem anini burada kaydetmek sart (Task #264).
    redeem_since_ts = writer.get_wallet_redeem_checkpoint(wallet)
    redeem_items, redeem_truncated = fetch_wallet_redeems(wallet, redeem_since_ts)
    if redeem_truncated:
        log(f"  [Wallet {wallet[:10]}...] redeem fetch truncated before checkpoint, skipping this run")
    else:
        redeem_rows = []
        for item in reversed(redeem_items):
            try:
                ts = int(item.get("timestamp") or 0)
            except (TypeError, ValueError):
                continue
            if ts <= 0:
                continue
            tx_hash = item.get("transactionHash")
            condition_id = item.get("conditionId")
            if not tx_hash or not condition_id:
                continue
            try:
                amount_usdc = float(item.get("usdcSize") or 0)
            except (TypeError, ValueError):
                amount_usdc = 0.0
            redeem_rows.append({
                "wallet": wallet,
                "transaction_hash": tx_hash,
                "condition_id": condition_id,
                "asset": item.get("asset"),
                "title": item.get("title"),
                "slug": item.get("slug"),
                "event_id": None,
                "amount_usdc": round(amount_usdc, 4),
                "traded_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
            })

        if redeem_rows and writer.upsert_wallet_redeems(redeem_rows):
            log(f"  [Wallet {wallet_row.get('nickname')}] +{len(redeem_rows)} yeni redeem")

    positions, positions_ok = fetch_wallet_positions(wallet)
    if not positions_ok:
        log(f"  [Wallet {wallet_row.get('nickname')}] pozisyon cekme hatasi, mevcut kayitli pozisyonlar korunuyor (replace atlandi)")
        return len(new_items) if not truncated else 0

    position_rows = []
    for p in positions:
        position_rows.append({
            "wallet": wallet,
            "condition_id": p.get("conditionId"),
            "asset": p.get("asset"),
            "title": p.get("title"),
            "slug": p.get("slug"),
            "event_id": p.get("eventId"),
            "outcome": p.get("outcome"),
            "size": p.get("size"),
            "avg_price": p.get("avgPrice"),
            "cur_price": p.get("curPrice"),
            "initial_value": p.get("initialValue"),
            "current_value": p.get("currentValue"),
            "cash_pnl": p.get("cashPnl"),
            "percent_pnl": p.get("percentPnl"),
            "redeemable": p.get("redeemable"),
            "end_date": p.get("endDate"),
        })
    writer.replace_wallet_positions(wallet, position_rows)

    return len(position_rows)


def run_tracked_wallets(writer: PolymarketSupabaseWriter):
    wallets = list_tracked_wallets()
    if not wallets:
        return
    log(f"{len(wallets)} takip edilen cuzdan senkronize ediliyor")
    for wallet_row in wallets:
        try:
            process_tracked_wallet(writer, wallet_row)
        except Exception as e:
            log(f"[Tracked Wallet Hata] {wallet_row.get('wallet')}: {e}")
            traceback.print_exc()
            continue


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
    scrape_ok = False
    for attempt in range(MAX_RETRIES):
        try:
            run_scrape(writer)
            scrape_ok = True
            break
        except Exception as e:
            last_error = str(e)[:200]
            log(f"[HATA] {last_error}")
            traceback.print_exc()

        if attempt < MAX_RETRIES - 1:
            delay = RETRY_DELAYS[attempt]
            log(f"{delay} saniye bekleniyor...")
            time.sleep(delay)

    try:
        run_tracked_wallets(writer)
    except Exception as e:
        log(f"[Takip Edilen Cuzdanlar] Hata: {e}")
        traceback.print_exc()

    return scrape_ok


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
