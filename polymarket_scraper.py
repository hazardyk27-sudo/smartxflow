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
import argparse
import hashlib
import json
import os
import sys
import time
import traceback
from datetime import datetime, timezone, timedelta
from typing import Optional, List, Dict, Any

import requests

sys.path.insert(0, os.path.dirname(__file__))

from poly_trade_checkpoints import fetch_latest_trade_checkpoints
from services.polymarket_client import (
    get_today_matches,
    get_all_active_matches,
    get_event_market_specs,
    _fetch_new_trades,
    _market_selection_side,
    list_tracked_wallets,
    fetch_wallet_activity,
    fetch_wallet_redeems,
    fetch_wallet_positions,
    _parse_activity_market,
    _canonical_match_metadata,
    _fetch_clob_midpoints,
    _closing_line_metrics,
    _to_decimal_odds,
    _classify_football_items,
    FOOTBALL_CLASS_VERIFIED,
    FOOTBALL_CLASS_NON_FOOTBALL,
    FOOTBALL_CLASS_UNCERTAIN,
    compute_and_save_wallet_stats,
)

try:
    SSL_VERIFY = __import__("certifi").where()
except Exception:
    SSL_VERIFY = True

INTERVAL_MINUTES = 5
INTERVAL_SECONDS = INTERVAL_MINUTES * 60

# General market tape is high-volume and only powers recent match analytics.
POLYMARKET_TRADE_RETENTION_DAYS = 7
# Tracked bettor raw fills/redeems are an audit/reconciliation buffer. Durable
# bettor history lives in tracked_wallet_bets and is intentionally not cleaned.
TRACKED_WALLET_RAW_RETENTION_DAYS = 365

# Price snapshots only need the approach to kickoff, not months of 5-minute data.
PRICE_SNAPSHOT_LOOKAHEAD_HOURS = 48
CLOSING_SNAPSHOT_MAX_AGE_MINUTES = 30
CLOSING_FINALIZE_LOOKBACK_HOURS = 6

MAX_RETRIES = 3
RETRY_DELAYS = [3, 6, 12]


def log(msg: str):
    ts = datetime.now(timezone.utc).strftime('%H:%M:%S')
    print(f"[Poly {ts}] {msg}", flush=True)


def _sport_quarantine_item_key(item_kind: str, item: Dict[str, Any]) -> str:
    if item_kind in ("activity", "redeem"):
        identity = [
            item_kind,
            item.get("transactionHash") or item.get("transaction_hash"),
            item.get("asset"),
            item.get("conditionId") or item.get("condition_id"),
            item.get("side"),
            item.get("timestamp") or item.get("traded_at"),
        ]
    else:
        identity = [
            item_kind,
            item.get("asset"),
            item.get("conditionId") or item.get("condition_id"),
            item.get("eventId") or item.get("event_id"),
            item.get("outcome"),
        ]
    raw = json.dumps(identity, ensure_ascii=False, separators=(",", ":"), default=str)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def _source_timestamp_iso(item: Dict[str, Any]) -> Optional[str]:
    raw = item.get("timestamp")
    if raw is not None:
        try:
            return datetime.fromtimestamp(int(raw), tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OSError):
            pass
    traded_at = item.get("traded_at")
    return str(traded_at) if traded_at else None


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

    def get_last_traded_at_many(
        self,
        condition_ids: List[str],
    ) -> Dict[str, Optional[int]]:
        return fetch_latest_trade_checkpoints(
            self,
            condition_ids,
            log=log,
            ssl_verify=SSL_VERIFY,
        )

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

    def get_wallet_resume_checkpoint(self, wallet: str) -> Optional[int]:
        """Return the safest floor after raw retention has removed old rows.

        last_synced_at is preferred because it marks the previous completed
        wallet sync. On a never-synced wallet we fall back to created_at so no
        pre-tracking history is accidentally imported.
        """
        try:
            headers = self._headers()
            url = (
                f"{self._rest_url('tracked_wallets')}"
                f"?wallet=eq.{wallet}&select=created_at,last_synced_at&limit=1"
            )
            resp = requests.get(
                url,
                headers=headers,
                timeout=15,
                verify=SSL_VERIFY,
            )
            if resp.status_code != 200:
                log(
                    f"[Wallet Resume-Floor GET] HTTP "
                    f"{resp.status_code}: {resp.text[:200]}"
                )
                return None
            rows = resp.json()
            if not rows:
                return None
            row = rows[0]
            for value in (row.get("last_synced_at"), row.get("created_at")):
                if not value:
                    continue
                try:
                    dt = datetime.fromisoformat(
                        str(value).replace("Z", "+00:00")
                    )
                    return int(dt.timestamp())
                except (TypeError, ValueError):
                    continue
            return None
        except Exception as e:
            log(f"[Wallet Resume-Floor GET] Hata: {e}")
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
            # Raw rows may legitimately be empty after retention. Resume
            # from the previous successful sync instead of falling all the way
            # back to created_at and re-downloading historical pages forever.
            return self.get_wallet_resume_checkpoint(wallet)
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
            return self.get_wallet_resume_checkpoint(wallet)
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

    def upsert_sport_quarantine(
        self,
        wallet: str,
        item_kind: str,
        items: List[Dict[str, Any]],
    ) -> bool:
        if not items:
            return True
        now = datetime.now(timezone.utc)
        rows = []
        for item in items:
            clean = {
                key: value
                for key, value in item.items()
                if not str(key).startswith("_sport_")
            }
            rows.append({
                "wallet": wallet,
                "item_kind": item_kind,
                "item_key": _sport_quarantine_item_key(item_kind, item),
                "asset": item.get("asset"),
                "condition_id": item.get("conditionId") or item.get("condition_id"),
                "event_id": (
                    item.get("_sport_resolved_event_id")
                    or item.get("eventId")
                    or item.get("event_id")
                ),
                "title": item.get("title"),
                "slug": item.get("eventSlug") or item.get("slug"),
                "traded_at": _source_timestamp_iso(item),
                "classification": FOOTBALL_CLASS_UNCERTAIN,
                "reason": item.get("_sport_reason") or "classification_uncertain",
                "raw_payload": clean,
                "last_seen_at": now.isoformat(),
                "next_retry_at": (now + timedelta(minutes=15)).isoformat(),
            })
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = (
                f"{self._rest_url('tracked_wallet_sport_quarantine')}"
                "?on_conflict=wallet,item_kind,item_key"
            )
            for offset in range(0, len(rows), 500):
                response = requests.post(
                    url,
                    headers=headers,
                    json=rows[offset:offset + 500],
                    timeout=30,
                    verify=SSL_VERIFY,
                )
                if response.status_code not in (200, 201, 204):
                    if response.status_code != 404:
                        log(
                            f"[Sport Quarantine UPSERT] HTTP "
                            f"{response.status_code}: {response.text[:160]}"
                        )
                    return False
            return True
        except Exception as exc:
            log(f"[Sport Quarantine UPSERT] Hata: {exc}")
            return False

    def get_pending_sport_quarantine(
        self,
        limit: int = 500,
    ) -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                self._rest_url("tracked_wallet_sport_quarantine"),
                headers=self._headers(),
                params={
                    "select": "wallet,item_kind,item_key,raw_payload,attempt_count,reason",
                    "classification": f"eq.{FOOTBALL_CLASS_UNCERTAIN}",
                    "next_retry_at": f"lte.{datetime.now(timezone.utc).isoformat()}",
                    "order": "next_retry_at.asc",
                    "limit": limit,
                },
                timeout=20,
                verify=SSL_VERIFY,
            )
            if response.status_code != 200:
                return []
            rows = response.json()
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def update_sport_quarantine(
        self,
        wallet: str,
        item_kind: str,
        item_key: str,
        classification: str,
        reason: str,
        attempt_count: int,
    ) -> bool:
        now = datetime.now(timezone.utc)
        payload: Dict[str, Any] = {
            "classification": classification,
            "reason": reason,
            "attempt_count": attempt_count,
            "last_seen_at": now.isoformat(),
        }
        if classification == FOOTBALL_CLASS_UNCERTAIN:
            delay_minutes = min(24 * 60, 15 * (2 ** min(attempt_count, 6)))
            payload["next_retry_at"] = (
                now + timedelta(minutes=delay_minutes)
            ).isoformat()
            payload["resolved_at"] = None
        else:
            payload["next_retry_at"] = None
            payload["resolved_at"] = now.isoformat()
        try:
            response = requests.patch(
                self._rest_url("tracked_wallet_sport_quarantine"),
                headers=self._headers(),
                params={
                    "wallet": f"eq.{wallet}",
                    "item_kind": f"eq.{item_kind}",
                    "item_key": f"eq.{item_key}",
                },
                json=payload,
                timeout=20,
                verify=SSL_VERIFY,
            )
            return response.status_code in (200, 204)
        except Exception:
            return False

    def get_bets_needing_sport_classification(
        self,
        limit: int = 1000,
    ) -> List[Dict[str, Any]]:
        try:
            response = requests.get(
                self._rest_url("tracked_wallet_bets"),
                headers=self._headers(),
                params={
                    "select": "wallet,bet_key,condition_id,event_id,title,slug,sport_classification",
                    "or": "(sport_classification.is.null,sport_classification.eq.uncertain)",
                    "order": "last_traded_at.desc.nullslast",
                    "limit": limit,
                },
                timeout=20,
                verify=SSL_VERIFY,
            )
            if response.status_code != 200:
                return []
            rows = response.json()
            return rows if isinstance(rows, list) else []
        except Exception:
            return []

    def update_bet_sport_classification(
        self,
        wallet: str,
        bet_key: str,
        classification: str,
        source: str,
    ) -> bool:
        payload = {
            "sport_classification": classification,
            "sport_verified_at": datetime.now(timezone.utc).isoformat(),
            "sport_classification_source": source,
        }
        try:
            response = requests.patch(
                self._rest_url("tracked_wallet_bets"),
                headers=self._headers(),
                params={
                    "wallet": f"eq.{wallet}",
                    "bet_key": f"eq.{bet_key}",
                },
                json=payload,
                timeout=20,
                verify=SSL_VERIFY,
            )
            return response.status_code in (200, 204)
        except Exception:
            return False

    def wallet_sport_classification_complete(self, wallet: str) -> bool:
        try:
            response = requests.get(
                self._rest_url("tracked_wallet_bets"),
                headers=self._headers(),
                params={
                    "select": "bet_key",
                    "wallet": f"eq.{wallet}",
                    "or": "(sport_classification.is.null,sport_classification.eq.uncertain)",
                    "limit": 1,
                },
                timeout=15,
                verify=SSL_VERIFY,
            )
            if response.status_code != 200:
                return False
            rows = response.json()
            return isinstance(rows, list) and not rows
        except Exception:
            return False

    def delete_before(self, table: str, date_col: str, cutoff_date: str,
                       retries: int = 3, chunk_fallback: bool = True) -> int:
        """DELETE: date_col < cutoff_date olan TUM satirlari siler (orphan dahil).
        Buyuk tablolarda tek-statement DELETE Supabase/PostgREST tarafinda statement
        timeout'a takilip 500 donebiliyor. Once birkac kez (backoff ile) tek-statement
        DELETE denenir; hepsi basarisiz olursa gune-gune chunk'li silmeye dusulur (bkz.
        services/supabase_client.py::_delete_before_chunked - ayni mantik)."""
        last_status = None
        for attempt in range(retries):
            try:
                headers = self._headers()
                headers['Prefer'] = 'count=exact'
                url = f"{self._rest_url(table)}?{date_col}=lt.{cutoff_date}"
                resp = requests.delete(url, headers=headers, timeout=120, verify=SSL_VERIFY)
                if resp.status_code in (200, 204):
                    cr = resp.headers.get('content-range', '')
                    if '/' in cr:
                        t = cr.split('/')[-1]
                        if t.isdigit():
                            return int(t)
                    return 0
                if resp.status_code == 404:
                    return 0
                last_status = resp.status_code
                log(f"[Cleanup] {table} delete failed (attempt {attempt + 1}/{retries}): {resp.status_code}")
            except Exception as e:
                last_status = str(e)
                log(f"[Cleanup] {table} delete error (attempt {attempt + 1}/{retries}): {e}")
            if attempt < retries - 1:
                time.sleep(2 * (attempt + 1))

        if not chunk_fallback:
            log(f"[Cleanup] {table}: tum denemeler basarisiz ({last_status}), chunk fallback devre disi")
            return 0

        log(f"[Cleanup] {table}: tek-statement DELETE basarisiz ({last_status}), gune-gune chunk'li silmeye geciliyor...")
        return self._delete_before_chunked(table, date_col, cutoff_date)

    def _oldest_date_value(self, table: str, date_col: str):
        """Tablodaki en eski date_col degerini dondurur (chunk fallback'in nereden
        baslayacagini bilmesi icin). Tablo bos/erisilemezse None."""
        try:
            headers = self._headers()
            url = f"{self._rest_url(table)}?select={date_col}&order={date_col}.asc&limit=1"
            resp = requests.get(url, headers=headers, timeout=30, verify=SSL_VERIFY)
            if resp.status_code == 200:
                rows = resp.json()
                if rows:
                    return rows[0].get(date_col)
        except Exception as e:
            log(f"[Cleanup] {table}: en eski tarih sorgusu hatasi: {e}")
        return None

    def _delete_before_chunked(self, table: str, date_col: str, cutoff_date: str,
                                max_days: int = 3650) -> int:
        """Gune-gune chunk'li DELETE fallback. Baslangic noktasi sabit bir gun sayisi degil,
        tablodaki gercek en eski kaydin tarihidir, boylece daha eski birikinti de atlanmaz.
        Basarisiz chunk'lar ATLANDI olarak loglanir ve bir sonraki calismada otomatik tekrar
        denenir (sessizce tamamlandi sayilmaz). Toplam silinen satir sayisini dondurur."""
        try:
            cutoff_dt = datetime.strptime(cutoff_date[:10], '%Y-%m-%d').date()
        except Exception as e:
            log(f"[Cleanup] {table}: chunk fallback cutoff parse hatasi: {e}")
            return 0

        oldest_raw = self._oldest_date_value(table, date_col)
        if oldest_raw:
            try:
                oldest_dt = datetime.strptime(str(oldest_raw)[:10], '%Y-%m-%d').date()
            except Exception:
                oldest_dt = cutoff_dt - timedelta(days=max_days)
        else:
            oldest_dt = cutoff_dt - timedelta(days=max_days)

        span_days = (cutoff_dt - oldest_dt).days
        if span_days > max_days:
            log(f"[Cleanup] {table}: en eski kayit {oldest_dt} - {span_days} gunluk aralik {max_days} gun ile sinirlandirildi, kalan sonraki calismada islenecek")
            oldest_dt = cutoff_dt - timedelta(days=max_days)

        total = 0
        skipped_days = []
        day = oldest_dt
        while day < cutoff_dt:
            next_day = day + timedelta(days=1)
            day_str = day.strftime('%Y-%m-%d')
            next_str = next_day.strftime('%Y-%m-%d')
            chunk_count = None
            ok = False
            for attempt in range(2):
                try:
                    headers = self._headers()
                    headers['Prefer'] = 'count=exact'
                    url = f"{self._rest_url(table)}?{date_col}=gte.{day_str}&{date_col}=lt.{next_str}"
                    resp = requests.delete(url, headers=headers, timeout=90, verify=SSL_VERIFY)
                    if resp.status_code in (200, 204):
                        cr = resp.headers.get('content-range', '')
                        chunk_count = 0
                        if '/' in cr:
                            t = cr.split('/')[-1]
                            if t.isdigit():
                                chunk_count = int(t)
                        ok = True
                        break
                    if resp.status_code == 404:
                        chunk_count = 0
                        ok = True
                        break
                    log(f"[Cleanup] {table} chunk {day_str} delete failed (attempt {attempt + 1}/2): {resp.status_code}")
                except Exception as e:
                    log(f"[Cleanup] {table} chunk {day_str} delete error (attempt {attempt + 1}/2): {e}")
                time.sleep(2)
            if not ok:
                skipped_days.append(day_str)
                log(f"[Cleanup] {table} chunk {day_str}: ATLANDI (denemeler basarisiz) - bir sonraki calismada tekrar denenecek")
            elif chunk_count:
                total += chunk_count
                log(f"[Cleanup] {table} chunk {day_str}: {chunk_count} satir silindi")
            day = next_day

        if skipped_days:
            log(f"[Cleanup] {table}: chunk'li silme KISMEN tamamlandi - {total} satir silindi, {len(skipped_days)} gun atlandi")
        else:
            log(f"[Cleanup] {table}: chunk'li silme tamamlandi - toplam {total} satir")
        return total

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

    def get_price_snapshot_candidates(
        self,
        now: datetime,
        horizon: datetime,
    ) -> List[Dict[str, Any]]:
        """Load pre-kickoff tracked bet assets that still need market tracking."""
        try:
            rows: List[Dict[str, Any]] = []
            page_size = 1000
            for page in range(100):
                params = [
                    ("select", "asset,condition_id,event_id,kickoff_utc,first_traded_at"),
                    ("asset", "not.is.null"),
                    ("kickoff_utc", f"gte.{now.isoformat()}"),
                    ("kickoff_utc", f"lte.{horizon.isoformat()}"),
                    ("order", "kickoff_utc.asc"),
                    ("limit", str(page_size)),
                    ("offset", str(page * page_size)),
                ]
                resp = requests.get(
                    self._rest_url("tracked_wallet_bets"),
                    headers=self._headers(),
                    params=params,
                    timeout=20,
                    verify=SSL_VERIFY,
                )
                if resp.status_code != 200:
                    if resp.status_code != 404:
                        log(f"[PriceSnapshot candidates] HTTP {resp.status_code}: {resp.text[:160]}")
                    return rows
                page_rows = resp.json()
                if not isinstance(page_rows, list):
                    return rows
                rows.extend(page_rows)
                if len(page_rows) < page_size:
                    return rows
            log("[PriceSnapshot candidates] pagination safety cap reached")
            return rows
        except Exception as e:
            log(f"[PriceSnapshot candidates] Hata: {e}")
            return []

    def upsert_price_snapshots(self, rows: List[Dict[str, Any]]) -> bool:
        if not rows:
            return True
        try:
            headers = self._headers()
            headers["Prefer"] = "resolution=merge-duplicates"
            url = (
                f"{self._rest_url('polymarket_price_snapshots')}"
                "?on_conflict=asset,bucket_at"
            )
            for offset in range(0, len(rows), 500):
                resp = requests.post(
                    url,
                    headers=headers,
                    json=rows[offset:offset + 500],
                    timeout=30,
                    verify=SSL_VERIFY,
                )
                if resp.status_code not in (200, 201, 204):
                    if resp.status_code != 404:
                        log(f"[PriceSnapshot UPSERT] HTTP {resp.status_code}: {resp.text[:160]}")
                    return False
            return True
        except Exception as e:
            log(f"[PriceSnapshot UPSERT] Hata: {e}")
            return False

    def update_latest_market_price(
        self,
        asset: str,
        price: float,
        observed_at: str,
    ) -> bool:
        try:
            payload = {
                "latest_market_price": round(price, 6),
                "latest_market_decimal": _to_decimal_odds(price),
                "latest_market_at": observed_at,
            }
            url = (
                f"{self._rest_url('tracked_wallet_bets')}"
                f"?asset=eq.{asset}"
            )
            resp = requests.patch(
                url,
                headers=self._headers(),
                json=payload,
                timeout=20,
                verify=SSL_VERIFY,
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False

    def get_pending_closing_bets(
        self,
        now: datetime,
    ) -> List[Dict[str, Any]]:
        """Bets whose kickoff just passed and closing line is still missing."""
        floor = now - timedelta(hours=CLOSING_FINALIZE_LOOKBACK_HOURS)
        try:
            rows: List[Dict[str, Any]] = []
            page_size = 1000
            for page in range(100):
                params = [
                    ("select", "wallet,bet_key,asset,kickoff_utc,first_traded_at,last_traded_at,avg_entry_price"),
                    ("asset", "not.is.null"),
                    ("closing_price", "is.null"),
                    ("kickoff_utc", f"gte.{floor.isoformat()}"),
                    ("kickoff_utc", f"lte.{now.isoformat()}"),
                    ("limit", str(page_size)),
                    ("offset", str(page * page_size)),
                ]
                resp = requests.get(
                    self._rest_url("tracked_wallet_bets"),
                    headers=self._headers(),
                    params=params,
                    timeout=20,
                    verify=SSL_VERIFY,
                )
                if resp.status_code != 200:
                    return rows
                page_rows = resp.json()
                if not isinstance(page_rows, list):
                    return rows
                rows.extend(page_rows)
                if len(page_rows) < page_size:
                    return rows
            log("[PriceSnapshot closing] pagination safety cap reached")
            return rows
        except Exception:
            return []

    def get_last_pre_kickoff_snapshot(
        self,
        asset: str,
        kickoff: datetime,
    ) -> Optional[Dict[str, Any]]:
        """Return only a recent snapshot; stale prices are never called close."""
        earliest = kickoff - timedelta(minutes=CLOSING_SNAPSHOT_MAX_AGE_MINUTES)
        try:
            params = [
                ("select", "market_price,decimal_odds,observed_at,source"),
                ("asset", f"eq.{asset}"),
                ("observed_at", f"gte.{earliest.isoformat()}"),
                ("observed_at", f"lt.{kickoff.isoformat()}"),
                ("order", "observed_at.desc"),
                ("limit", "1"),
            ]
            resp = requests.get(
                self._rest_url("polymarket_price_snapshots"),
                headers=self._headers(),
                params=params,
                timeout=15,
                verify=SSL_VERIFY,
            )
            if resp.status_code != 200:
                return None
            rows = resp.json()
            return rows[0] if isinstance(rows, list) and rows else None
        except Exception:
            return None

    def finalize_bet_closing_line(
        self,
        wallet: str,
        bet_key: str,
        closing_price: float,
        observed_at: str,
        metrics: Dict[str, Optional[float]],
    ) -> bool:
        try:
            payload = {
                "closing_price": round(closing_price, 6),
                "closing_decimal": metrics.get("closing_decimal"),
                "closing_observed_at": observed_at,
                "clv_probability_pp": metrics.get("clv_probability_pp"),
                "clv_pct": metrics.get("clv_pct"),
            }
            params = [
                ("wallet", f"eq.{wallet}"),
                ("bet_key", f"eq.{bet_key}"),
                ("closing_price", "is.null"),
            ]
            resp = requests.patch(
                self._rest_url("tracked_wallet_bets"),
                headers=self._headers(),
                params=params,
                json=payload,
                timeout=20,
                verify=SSL_VERIFY,
            )
            return resp.status_code in (200, 204)
        except Exception:
            return False


def _parse_kickoff(kickoff_utc: Optional[str]):
    if not kickoff_utc:
        return None
    try:
        return datetime.fromisoformat(kickoff_utc.replace("Z", "+00:00"))
    except Exception:
        return None


def _price_snapshot_cadence_minutes(hours_to_kickoff: float) -> int:
    if hours_to_kickoff > 6:
        return 60
    if hours_to_kickoff > 1:
        return 15
    return 5


def _price_snapshot_bucket(now: datetime, cadence_minutes: int) -> datetime:
    seconds = max(int(cadence_minutes), 1) * 60
    epoch = int(now.timestamp())
    return datetime.fromtimestamp(
        (epoch // seconds) * seconds,
        tz=timezone.utc,
    )


def _is_prematch_bet(candidate: Dict[str, Any], kickoff: datetime) -> bool:
    entered = _parse_kickoff(candidate.get("first_traded_at"))
    return entered is not None and entered < kickoff


def _is_clv_eligible_lifecycle(
    bet: Dict[str, Any],
    kickoff: datetime,
) -> bool:
    """Only compare a pure pre-kickoff lifecycle with the closing line."""
    if not _is_prematch_bet(bet, kickoff):
        return False
    last = _parse_kickoff(bet.get("last_traded_at"))
    return last is not None and last < kickoff


def run_tracked_price_snapshots(
    writer: PolymarketSupabaseWriter,
    now: Optional[datetime] = None,
) -> int:
    """Capture shared market midpoint history and finalize closing lines."""
    now = now or datetime.now(timezone.utc)
    horizon = now + timedelta(hours=PRICE_SNAPSHOT_LOOKAHEAD_HOURS)
    candidates = writer.get_price_snapshot_candidates(now, horizon)

    # One token has one market price even if several tracked wallets own it.
    by_asset: Dict[str, Dict[str, Any]] = {}
    for candidate in candidates:
        asset = str(candidate.get("asset") or "").strip()
        kickoff = _parse_kickoff(candidate.get("kickoff_utc"))
        if not asset or kickoff is None or not _is_prematch_bet(candidate, kickoff):
            continue
        existing = by_asset.get(asset)
        if existing is None:
            by_asset[asset] = candidate

    prices, complete = _fetch_clob_midpoints(list(by_asset.keys()))
    if not complete:
        log("[PriceSnapshot] CLOB midpoint batch kismi/eksik dondu")

    observed_at = now.isoformat()
    snapshot_rows: List[Dict[str, Any]] = []
    for asset, candidate in by_asset.items():
        price = prices.get(asset)
        if price is None:
            continue
        kickoff = _parse_kickoff(candidate.get("kickoff_utc"))
        if kickoff is None or now >= kickoff:
            continue
        hours_to_kickoff = max((kickoff - now).total_seconds() / 3600.0, 0.0)
        cadence = _price_snapshot_cadence_minutes(hours_to_kickoff)
        bucket = _price_snapshot_bucket(now, cadence)
        snapshot_rows.append({
            "asset": asset,
            "bucket_at": bucket.isoformat(),
            "observed_at": observed_at,
            "condition_id": candidate.get("condition_id"),
            "event_id": candidate.get("event_id"),
            "kickoff_utc": kickoff.isoformat(),
            "market_price": round(price, 6),
            "decimal_odds": _to_decimal_odds(price),
            "source": "clob_midpoint",
            "cadence_minutes": cadence,
            "is_pre_kickoff": True,
            "hours_to_kickoff": round(hours_to_kickoff, 4),
        })

    if snapshot_rows and writer.upsert_price_snapshots(snapshot_rows):
        for row in snapshot_rows:
            writer.update_latest_market_price(
                row["asset"],
                float(row["market_price"]),
                row["observed_at"],
            )

    # Closing price is the LAST observed pre-kickoff midpoint, and only if it
    # was captured within the freshness tolerance. Never use post-kickoff 0/1.
    pending = writer.get_pending_closing_bets(now)
    snapshot_cache: Dict[tuple, Optional[Dict[str, Any]]] = {}
    finalized = 0
    for bet in pending:
        asset = str(bet.get("asset") or "").strip()
        kickoff = _parse_kickoff(bet.get("kickoff_utc"))
        if (
            not asset
            or kickoff is None
            or not _is_clv_eligible_lifecycle(bet, kickoff)
        ):
            continue
        cache_key = (asset, kickoff.isoformat())
        if cache_key not in snapshot_cache:
            snapshot_cache[cache_key] = writer.get_last_pre_kickoff_snapshot(
                asset,
                kickoff,
            )
        snapshot = snapshot_cache[cache_key]
        if not snapshot:
            continue
        try:
            close_price = float(snapshot.get("market_price"))
        except (TypeError, ValueError):
            continue
        metrics = _closing_line_metrics(
            bet.get("avg_entry_price"),
            close_price,
        )
        if metrics.get("clv_probability_pp") is None:
            continue
        if writer.finalize_bet_closing_line(
            str(bet.get("wallet") or ""),
            str(bet.get("bet_key") or ""),
            close_price,
            str(snapshot.get("observed_at") or ""),
            metrics,
        ):
            finalized += 1

    if snapshot_rows or finalized:
        log(
            f"[PriceSnapshot] {len(snapshot_rows)} snapshot, "
            f"{finalized} closing line finalize"
        )
    return len(snapshot_rows)


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

    checkpoint_by_condition = writer.get_last_traded_at_many(
        [condition_id for _market_type, condition_id, _market in specs]
    )

    total_new = 0
    for market_type, condition_id, market in specs:
        raw_label = market.get("groupItemTitle") or market.get("question") or ""
        since_ts = checkpoint_by_condition.get(condition_id)
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


def _activity_item_to_row(
    wallet: str,
    item: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    try:
        ts = int(item.get("timestamp") or 0)
    except (TypeError, ValueError):
        return None
    tx_hash = item.get("transactionHash")
    asset = item.get("asset")
    if ts <= 0 or not tx_hash or not asset:
        return None

    market_type, _home, _away, selection, side = _parse_activity_market(item)
    match_meta = _canonical_match_metadata(item)
    try:
        price = float(item.get("price") or 0)
    except (TypeError, ValueError):
        price = 0.0
    try:
        size = float(item.get("size") or 0)
    except (TypeError, ValueError):
        size = 0.0
    try:
        amount_usdc = (
            float(item.get("usdcSize"))
            if item.get("usdcSize") is not None
            else size * price
        )
    except (TypeError, ValueError):
        amount_usdc = size * price

    return {
        "wallet": wallet,
        "transaction_hash": tx_hash,
        "asset": asset,
        "condition_id": item.get("conditionId"),
        "event_id": (
            item.get("_sport_resolved_event_id")
            or match_meta.get("event_id")
        ),
        "title": item.get("title"),
        "slug": (
            match_meta.get("event_slug")
            or item.get("eventSlug")
            or item.get("slug")
        ),
        "market_type": market_type,
        "selection": selection,
        "side": side if side is not None else "",
        "action": (item.get("side") or "").strip().upper() or None,
        "outcome_raw": item.get("outcome"),
        "amount_usdc": round(amount_usdc, 4),
        "price": price,
        "size": size,
        "traded_at": datetime.fromtimestamp(
            ts,
            tz=timezone.utc,
        ).isoformat(),
    }


def _redeem_item_to_row(
    wallet: str,
    item: Dict[str, Any],
) -> Optional[Dict[str, Any]]:
    try:
        ts = int(item.get("timestamp") or 0)
    except (TypeError, ValueError):
        return None
    tx_hash = item.get("transactionHash")
    condition_id = item.get("conditionId")
    if ts <= 0 or not tx_hash or not condition_id:
        return None
    try:
        amount_usdc = float(item.get("usdcSize") or 0)
    except (TypeError, ValueError):
        amount_usdc = 0.0
    match_meta = _canonical_match_metadata(item)
    return {
        "wallet": wallet,
        "transaction_hash": tx_hash,
        "condition_id": condition_id,
        "asset": item.get("asset"),
        "title": item.get("title"),
        "slug": (
            match_meta.get("event_slug")
            or item.get("eventSlug")
            or item.get("slug")
        ),
        "event_id": (
            item.get("_sport_resolved_event_id")
            or match_meta.get("event_id")
        ),
        "amount_usdc": round(amount_usdc, 4),
        "traded_at": datetime.fromtimestamp(
            ts,
            tz=timezone.utc,
        ).isoformat(),
    }


def _position_item_to_row(
    wallet: str,
    item: Dict[str, Any],
) -> Dict[str, Any]:
    match_meta = _canonical_match_metadata(item)
    return {
        "wallet": wallet,
        "condition_id": item.get("conditionId"),
        "asset": item.get("asset"),
        "title": item.get("title"),
        "slug": (
            match_meta.get("event_slug")
            or item.get("eventSlug")
            or item.get("slug")
        ),
        "event_id": (
            item.get("_sport_resolved_event_id")
            or match_meta.get("event_id")
            or item.get("eventId")
        ),
        "outcome": item.get("outcome"),
        "size": item.get("size"),
        "avg_price": item.get("avgPrice"),
        "cur_price": item.get("curPrice"),
        "initial_value": item.get("initialValue"),
        "current_value": item.get("currentValue"),
        "cash_pnl": item.get("cashPnl"),
        "percent_pnl": item.get("percentPnl"),
        "redeemable": item.get("redeemable"),
        "end_date": item.get("endDate"),
    }


def process_tracked_wallet(writer: PolymarketSupabaseWriter, wallet_row: Dict[str, Any]) -> int:
    """Sync one tracked wallet through the three-state Football Gate V2."""
    wallet = (wallet_row.get("wallet") or "").lower()
    if not wallet:
        return 0
    nickname = wallet_row.get("nickname") or wallet[:10]

    since_ts = writer.get_wallet_activity_checkpoint(wallet)
    (
        football_items,
        truncated,
        uncertain_items,
        nonfootball_items,
    ) = fetch_wallet_activity(
        wallet,
        since_ts,
        classification_details=True,
    )
    if truncated:
        log(f"  [Wallet {wallet[:10]}...] activity fetch truncated, skipping batch")
    else:
        if uncertain_items:
            writer.upsert_sport_quarantine(
                wallet,
                "activity",
                uncertain_items,
            )
            log(
                f"  [Wallet {nickname}] {len(uncertain_items)} activity "
                "karantinaya alindi"
            )
        if nonfootball_items:
            log(
                f"  [Wallet {nickname}] {len(nonfootball_items)} kesin "
                "futbol-disi activity elendi"
            )

        rows = [
            row
            for item in reversed(football_items)
            if (row := _activity_item_to_row(wallet, item)) is not None
        ]
        if rows and writer.upsert_wallet_activity(rows):
            log(f"  [Wallet {nickname}] +{len(rows)} yeni futbol islemi")

    redeem_since_ts = writer.get_wallet_redeem_checkpoint(wallet)
    (
        football_redeems,
        redeem_truncated,
        uncertain_redeems,
        nonfootball_redeems,
    ) = fetch_wallet_redeems(
        wallet,
        redeem_since_ts,
        classification_details=True,
    )
    if redeem_truncated:
        log(f"  [Wallet {wallet[:10]}...] redeem fetch truncated, skipping batch")
    else:
        if uncertain_redeems:
            writer.upsert_sport_quarantine(
                wallet,
                "redeem",
                uncertain_redeems,
            )
        if nonfootball_redeems:
            log(
                f"  [Wallet {nickname}] {len(nonfootball_redeems)} kesin "
                "futbol-disi redeem elendi"
            )
        redeem_rows = [
            row
            for item in reversed(football_redeems)
            if (row := _redeem_item_to_row(wallet, item)) is not None
        ]
        if redeem_rows and writer.upsert_wallet_redeems(redeem_rows):
            log(f"  [Wallet {nickname}] +{len(redeem_rows)} yeni futbol redeem")

    (
        positions,
        positions_ok,
        uncertain_positions,
        nonfootball_positions,
    ) = fetch_wallet_positions(
        wallet,
        classification_details=True,
    )
    if uncertain_positions:
        writer.upsert_sport_quarantine(
            wallet,
            "position",
            uncertain_positions,
        )
    if nonfootball_positions:
        log(
            f"  [Wallet {nickname}] {len(nonfootball_positions)} kesin "
            "futbol-disi pozisyon elendi"
        )

    position_rows: List[Dict[str, Any]] = []
    if not positions_ok:
        log(
            f"  [Wallet {nickname}] pozisyon siniflandirmasi/API eksik; "
            "mevcut verified snapshot korunuyor"
        )
    else:
        position_rows = [
            _position_item_to_row(wallet, item)
            for item in positions
        ]
        writer.replace_wallet_positions(wallet, position_rows)

    try:
        compute_and_save_wallet_stats(wallet)
    except Exception as exc:
        log(f"  [Wallet {nickname}] stats kaydetme hatasi: {exc}")

    return len(position_rows) if positions_ok else len(football_items)


def backfill_tracked_wallet(writer: PolymarketSupabaseWriter, wallet_row: Dict[str, Any]) -> int:
    """Fetch the COMPLETE Polymarket history for one tracked wallet (no checkpoint
    filter) and upsert everything into the DB. Safe to run multiple times — the
    upsert uses on_conflict keys so existing rows are updated in-place rather
    than duplicated. Positions are NOT backfilled (they reflect current state
    only); redeems ARE backfilled so win-rate stays correct.

    Kullanim (Hetzner'de):
        cd /opt/smartxflow
        set -a && source .env && set +a
        python3 polymarket_scraper.py --backfill
    """
    wallet = (wallet_row.get("wallet") or "").lower()
    if not wallet:
        return 0
    nickname = wallet_row.get("nickname") or wallet[:10]

    log(f"  [Backfill] {nickname} — tam gecmis cekiliyor (since_ts=None)...")

    # ── Activity (BUY/SELL fills) ────────────────────────────────────────────
    new_items, truncated = fetch_wallet_activity(wallet, since_ts=None)
    if truncated:
        log(f"  [Backfill] {nickname} — activity page cap'e ulasti, kismi veri")
    activity_rows = []
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
        match_meta = _canonical_match_metadata(item)
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
        activity_rows.append({
            "wallet": wallet,
            "transaction_hash": tx_hash,
            "asset": asset,
            "condition_id": item.get("conditionId"),
            "event_id": match_meta.get("event_id"),
            "title": item.get("title"),
            "slug": match_meta.get("event_slug") or item.get("eventSlug") or item.get("slug"),
            "market_type": market_type,
            "selection": selection,
            "side": side if side is not None else "",
            "action": (item.get("side") or "").strip().upper() or None,
            "outcome_raw": item.get("outcome"),
            "amount_usdc": round(amount_usdc, 4),
            "price": price,
            "size": size,
            "traded_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        })

    if activity_rows:
        if writer.upsert_wallet_activity(activity_rows):
            log(f"  [Backfill] {nickname} — {len(activity_rows)} activity upsert edildi")
        else:
            log(f"  [Backfill] {nickname} — activity upsert HATASI")
    else:
        log(f"  [Backfill] {nickname} — hic activity bulunamadi")

    # ── Redeems ─────────────────────────────────────────────────────────────
    redeem_items, redeem_truncated = fetch_wallet_redeems(wallet, since_ts=None)
    if redeem_truncated:
        log(f"  [Backfill] {nickname} — redeem page cap'e ulasti, kismi veri")
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
        match_meta = _canonical_match_metadata(item)
        redeem_rows.append({
            "wallet": wallet,
            "transaction_hash": tx_hash,
            "condition_id": condition_id,
            "asset": item.get("asset"),
            "title": item.get("title"),
            "slug": match_meta.get("event_slug") or item.get("eventSlug") or item.get("slug"),
            "event_id": match_meta.get("event_id"),
            "amount_usdc": round(amount_usdc, 4),
            "traded_at": datetime.fromtimestamp(ts, tz=timezone.utc).isoformat(),
        })

    if redeem_rows:
        if writer.upsert_wallet_redeems(redeem_rows):
            log(f"  [Backfill] {nickname} — {len(redeem_rows)} redeem upsert edildi")
        else:
            log(f"  [Backfill] {nickname} — redeem upsert HATASI")
    else:
        log(f"  [Backfill] {nickname} — hic redeem bulunamadi")

    # ── Stats recompute ──────────────────────────────────────────────────────
    try:
        compute_and_save_wallet_stats(wallet)
        log(f"  [Backfill] {nickname} — stats guncellendi")
    except Exception as e:
        log(f"  [Backfill] {nickname} — stats hatasi: {e}")

    return len(activity_rows)


def retry_sport_quarantine(writer: PolymarketSupabaseWriter) -> int:
    pending = writer.get_pending_sport_quarantine()
    if not pending:
        return 0

    source_items: List[Dict[str, Any]] = []
    meta_by_ref: Dict[str, Dict[str, Any]] = {}
    for row in pending:
        raw = row.get("raw_payload")
        if not isinstance(raw, dict):
            continue
        ref = row.get("item_key")
        item = dict(raw)
        item["_quarantine_ref"] = ref
        source_items.append(item)
        meta_by_ref[str(ref)] = row

    classified = _classify_football_items(source_items)
    affected_wallets: set = set()
    resolved_count = 0

    for classification, key in (
        (FOOTBALL_CLASS_VERIFIED, "verified_football"),
        (FOOTBALL_CLASS_NON_FOOTBALL, "verified_non_football"),
        (FOOTBALL_CLASS_UNCERTAIN, "uncertain"),
    ):
        for item in classified[key]:
            ref = str(item.get("_quarantine_ref") or "")
            meta = meta_by_ref.get(ref)
            if not meta:
                continue
            wallet = str(meta.get("wallet") or "").lower()
            item_kind = str(meta.get("item_kind") or "")
            attempts = int(meta.get("attempt_count") or 0) + 1
            final_classification = classification
            reason = item.get("_sport_reason") or final_classification

            if final_classification == FOOTBALL_CLASS_VERIFIED:
                stored = False
                if item_kind == "activity":
                    row = _activity_item_to_row(wallet, item)
                    stored = bool(row and writer.upsert_wallet_activity([row]))
                elif item_kind == "redeem":
                    row = _redeem_item_to_row(wallet, item)
                    stored = bool(row and writer.upsert_wallet_redeems([row]))
                elif item_kind == "position":
                    # Positions are snapshots; never resurrect an old position.
                    # The next live full-position sync will include it now that
                    # its registry identity is verified.
                    stored = True
                if not stored:
                    final_classification = FOOTBALL_CLASS_UNCERTAIN
                    reason = "verified_but_storage_retry_needed"
                else:
                    affected_wallets.add(wallet)
                    resolved_count += 1
            elif final_classification == FOOTBALL_CLASS_NON_FOOTBALL:
                resolved_count += 1

            writer.update_sport_quarantine(
                wallet,
                item_kind,
                ref,
                final_classification,
                reason,
                attempts,
            )

    for wallet in affected_wallets:
        try:
            compute_and_save_wallet_stats(wallet)
        except Exception:
            pass

    if resolved_count:
        log(f"[Sport Quarantine] {resolved_count} kayit kesin siniflandirildi")
    return resolved_count


def run_persisted_bet_sport_audit(
    writer: PolymarketSupabaseWriter,
) -> int:
    rows = writer.get_bets_needing_sport_classification()
    if not rows:
        return 0

    items: List[Dict[str, Any]] = []
    meta_by_ref: Dict[str, Dict[str, Any]] = {}
    for row in rows:
        ref = f"{row.get('wallet')}|{row.get('bet_key')}"
        item = {
            "condition_id": row.get("condition_id"),
            "event_id": row.get("event_id"),
            "title": row.get("title"),
            "slug": row.get("slug"),
            "_audit_ref": ref,
        }
        items.append(item)
        meta_by_ref[ref] = row

    classified = _classify_football_items(items)
    touched_wallets: set = set()
    changed = 0
    for classification, key in (
        (FOOTBALL_CLASS_VERIFIED, "verified_football"),
        (FOOTBALL_CLASS_NON_FOOTBALL, "verified_non_football"),
        (FOOTBALL_CLASS_UNCERTAIN, "uncertain"),
    ):
        for item in classified[key]:
            ref = str(item.get("_audit_ref") or "")
            meta = meta_by_ref.get(ref)
            if not meta:
                continue
            wallet = str(meta.get("wallet") or "").lower()
            bet_key = str(meta.get("bet_key") or "")
            if not wallet or not bet_key:
                continue
            if writer.update_bet_sport_classification(
                wallet,
                bet_key,
                classification,
                item.get("_sport_reason") or "gamma-soccer-v2",
            ):
                changed += 1
                touched_wallets.add(wallet)

    # Rebase totals downward only after every durable bet for that wallet has a
    # final classification. One uncertain row keeps the old larger snapshot.
    for wallet in touched_wallets:
        if not writer.wallet_sport_classification_complete(wallet):
            continue
        try:
            compute_and_save_wallet_stats(
                wallet,
                allow_verified_sport_rebase=True,
            )
        except Exception as exc:
            log(f"[Sport Audit] {wallet[:10]} stats rebase hatasi: {exc}")

    if changed:
        log(f"[Sport Audit] {changed} persistent bahis siniflandirildi")
    return changed


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


def run_backfill(writer: PolymarketSupabaseWriter):
    """Tum tracked cuzdan icin tam gecmis backfill calistirir.
    Normal 5 dk dongusunden bagimsizdir; sadece --backfill argumaninyla tetiklenir."""
    wallets = list_tracked_wallets()
    if not wallets:
        log("[Backfill] Hic tracked cuzdan bulunamadi.")
        return
    log(f"[Backfill] {len(wallets)} cuzdan icin tam gecmis backfill basliyor...")
    for wallet_row in wallets:
        try:
            count = backfill_tracked_wallet(writer, wallet_row)
            log(f"[Backfill] {wallet_row.get('nickname')} tamamlandi: {count} activity")
        except Exception as e:
            log(f"[Backfill Hata] {wallet_row.get('wallet')}: {e}")
            traceback.print_exc()
            continue
    log("[Backfill] Tum cuzdanlar tamamlandi.")


def cleanup_old_poly_data(writer: PolymarketSupabaseWriter) -> int:
    """Apply tiered retention without touching durable bettor history.

    - polymarket_trades: short recent-match tape.
    - tracked_wallet_activity/redeems: long raw audit/reconciliation buffer.
    - tracked_wallet_bets: NEVER cleaned here; it is the durable all-history
      canonical bettor ledger introduced by PART 9.
    - tracked_wallet_positions: current snapshot, replaced every sync.
    """
    now = datetime.now(timezone.utc)
    market_cutoff = (
        now - timedelta(days=POLYMARKET_TRADE_RETENTION_DAYS)
    ).strftime('%Y-%m-%dT00:00:00')
    wallet_cutoff = (
        now - timedelta(days=TRACKED_WALLET_RAW_RETENTION_DAYS)
    ).strftime('%Y-%m-%dT00:00:00')

    policies = (
        ("polymarket_trades", market_cutoff, POLYMARKET_TRADE_RETENTION_DAYS),
        ("tracked_wallet_activity", wallet_cutoff, TRACKED_WALLET_RAW_RETENTION_DAYS),
        ("tracked_wallet_redeems", wallet_cutoff, TRACKED_WALLET_RAW_RETENTION_DAYS),
    )
    log(
        "[Cleanup] Poly retention: "
        f"market tape={POLYMARKET_TRADE_RETENTION_DAYS}g, "
        f"tracked raw={TRACKED_WALLET_RAW_RETENTION_DAYS}g, "
        "tracked_wallet_bets=suresiz"
    )

    total_deleted = 0
    for table, cutoff_iso, days in policies:
        try:
            count = writer.delete_before(table, "traded_at", cutoff_iso)
            if count:
                log(
                    f"  [Cleanup] {table}: {count} satir silindi "
                    f"(D-{days} oncesi)"
                )
                total_deleted += count
        except Exception as e:
            log(f"  [Cleanup] {table}: Hata - {e}")

    if total_deleted:
        log(f"[Cleanup] Poly cleanup tamamlandi - {total_deleted} satir silindi")
    return total_deleted


def run_scrape(writer: PolymarketSupabaseWriter) -> int:
    # Merge DB-stored matches with live Gamma API so newly listed matches
    # (e.g. Spain vs. Belgium appearing hours before kickoff) are discovered
    # every cycle without waiting for a manual DB seed.
    db_matches = get_today_matches(hours_ahead=None)
    live_matches = get_all_active_matches()
    seen_ids = {m["event_id"] for m in db_matches if m.get("event_id")}
    for lm in live_matches:
        if lm.get("event_id") not in seen_ids:
            db_matches.append(lm)
            seen_ids.add(lm["event_id"])
    matches = db_matches
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
        retry_sport_quarantine(writer)
    except Exception as e:
        log(f"[Sport Quarantine] Hata: {e}")
        traceback.print_exc()

    try:
        run_persisted_bet_sport_audit(writer)
    except Exception as e:
        log(f"[Sport Audit] Hata: {e}")
        traceback.print_exc()

    try:
        run_tracked_wallets(writer)
    except Exception as e:
        log(f"[Takip Edilen Cuzdanlar] Hata: {e}")
        traceback.print_exc()

    try:
        run_tracked_price_snapshots(writer)
    except Exception as e:
        log(f"[PriceSnapshot] Hata: {e}")
        traceback.print_exc()

    return scrape_ok


def run_loop():
    log(f"Polymarket Scraper {INTERVAL_MINUTES} dakikada bir calisacak")

    supabase_url = os.environ.get('SUPABASE_URL')
    supabase_key = os.environ.get('SUPABASE_ANON_KEY')
    cleanup_writer = PolymarketSupabaseWriter(supabase_url, supabase_key) if supabase_url and supabase_key else None
    last_cleanup_date = None

    while True:
        try:
            main()
        except Exception as e:
            log(f"[Loop] main() hatasi: {e}")
            traceback.print_exc()

        if cleanup_writer is not None:
            today = datetime.now(timezone.utc).date()
            if last_cleanup_date != today:
                try:
                    cleanup_old_poly_data(cleanup_writer)
                    last_cleanup_date = today
                except Exception as e:
                    log(f"[Loop] cleanup_old_poly_data hatasi: {e}")
                    traceback.print_exc()

        log(f"Sonraki calisma {INTERVAL_MINUTES} dakika sonra...")
        time.sleep(INTERVAL_SECONDS)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="SmartXFlow Polymarket Scraper")
    parser.add_argument(
        "--backfill",
        action="store_true",
        help=(
            "Tum tracked cuzdanlar icin tam gecmis backfill calistir. "
            "Normal donguden bagimsiz, tek seferlik. "
            "Ornek: python3 polymarket_scraper.py --backfill"
        ),
    )
    args = parser.parse_args()

    supabase_url = os.environ.get("SUPABASE_URL")
    supabase_key = os.environ.get("SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_key:
        log("HATA: SUPABASE_URL veya SUPABASE_ANON_KEY eksik!")
        sys.exit(1)

    if args.backfill:
        writer = PolymarketSupabaseWriter(supabase_url, supabase_key)
        run_backfill(writer)
    else:
        run_loop()
