from __future__ import annotations

from datetime import datetime, time, timedelta, timezone
import os
import re
from typing import Any
from zoneinfo import ZoneInfo

import httpx


class SXFSourceError(RuntimeError):
    pass


def _number(value: Any) -> float | None:
    if value is None:
        return None
    text = re.sub(r"[^0-9.\-]", "", str(value).replace(",", "").strip())
    if not text:
        return None
    try:
        return float(text)
    except ValueError:
        return None


def _iso(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return None
    return parsed


def _clock(value: str, *, allow_24: bool = False) -> tuple[int, int, bool]:
    text = str(value or "").strip()
    if allow_24 and text == "24:00":
        return 0, 0, True
    match = re.fullmatch(r"([01]\d|2[0-3]):([0-5]\d)", text)
    if not match:
        raise SXFSourceError(f"invalid clock value: {value!r}")
    return int(match.group(1)), int(match.group(2)), False


class SXFStage1Source:
    """Read-only SmartXFlow Stage 1 context builder backed by Supabase REST."""

    _HISTORY_BATCH_SIZE = 8

    _MARKETS = {
        "1X2": {
            "table": "moneyway_1x2_history",
            "select": "match_id_hash,odds1,oddsx,odds2,pct1,pctx,pct2,amt1,amtx,amt2,volume,scraped_at",
            "selections": {
                "Home": ("odds1", "pct1", "amt1"),
                "Draw": ("oddsx", "pctx", "amtx"),
                "Away": ("odds2", "pct2", "amt2"),
            },
        },
        "OU2.5": {
            "table": "moneyway_ou25_history",
            "select": "match_id_hash,under,over,pctunder,pctover,amtunder,amtover,volume,scraped_at",
            "selections": {
                "Under 2.5": ("under", "pctunder", "amtunder"),
                "Over 2.5": ("over", "pctover", "amtover"),
            },
        },
        "BTTS": {
            "table": "moneyway_btts_history",
            "select": "match_id_hash,yes,no,pctyes,pctno,amtyes,amtno,volume,scraped_at",
            "selections": {
                "BTTS Yes": ("yes", "pctyes", "amtyes"),
                "BTTS No": ("no", "pctno", "amtno"),
            },
        },
    }

    def __init__(self, url: str, key: str, *, timeout_seconds: int = 30):
        self.url = str(url or "").rstrip("/")
        self.key = str(key or "")
        if not self.url or not self.key:
            raise SXFSourceError("SUPABASE_URL and SUPABASE key are required")
        self._client = httpx.Client(timeout=httpx.Timeout(timeout_seconds, connect=8, pool=8))

    @classmethod
    def from_env(cls) -> "SXFStage1Source":
        return cls(
            os.environ.get("SUPABASE_URL", ""),
            os.environ.get("SUPABASE_ANON_KEY", "") or os.environ.get("SUPABASE_KEY", ""),
        )

    @classmethod
    def from_env_optional(cls) -> "SXFStage1Source | None":
        url = os.environ.get("SUPABASE_URL", "")
        key = os.environ.get("SUPABASE_ANON_KEY", "") or os.environ.get("SUPABASE_KEY", "")
        if not url or not key:
            return None
        return cls(url, key)

    def close(self) -> None:
        self._client.close()

    def _headers(self) -> dict[str, str]:
        return {"apikey": self.key, "Authorization": f"Bearer {self.key}"}

    def _get(self, table: str, params: dict[str, Any]) -> list[dict[str, Any]]:
        response = self._client.get(f"{self.url}/rest/v1/{table}", headers=self._headers(), params=params)
        if response.status_code != 200:
            raise SXFSourceError(f"{table} read failed: HTTP {response.status_code}: {response.text[:240]}")
        data = response.json()
        if not isinstance(data, list):
            raise SXFSourceError(f"{table} returned non-list payload")
        return data

    @staticmethod
    def _resolve_window(scope: dict[str, Any], now: datetime) -> tuple[datetime, datetime, ZoneInfo]:
        tz_name = str(scope.get("timezone") or "Europe/Istanbul")
        try:
            tz = ZoneInfo(tz_name)
        except Exception as exc:
            raise SXFSourceError(f"unsupported timezone: {tz_name}") from exc
        now_local = now.astimezone(tz)
        date_text = str(scope.get("date") or now_local.date().isoformat())
        try:
            target_date = datetime.strptime(date_text, "%Y-%m-%d").date()
        except ValueError as exc:
            raise SXFSourceError("scope.date must be YYYY-MM-DD") from exc
        window = scope.get("window_tr") or scope.get("window") or ["00:00", "24:00"]
        if not isinstance(window, list) or len(window) != 2:
            raise SXFSourceError("scope.window_tr must contain [start, end]")
        sh, sm, _ = _clock(str(window[0]))
        eh, em, end_next_day = _clock(str(window[1]), allow_24=True)
        start_local = datetime.combine(target_date, time(sh, sm), tzinfo=tz)
        end_date = target_date + timedelta(days=1) if end_next_day else target_date
        end_local = datetime.combine(end_date, time(eh, em), tzinfo=tz)
        if end_local <= start_local:
            end_local += timedelta(days=1)
        if scope.get("future_only", True) is not False and target_date == now_local.date():
            start_local = max(start_local, now_local)
        return start_local, end_local, tz

    def _fixtures_window(self, start_utc: datetime, end_utc: datetime) -> list[dict[str, Any]]:
        response = self._client.get(
            f"{self.url}/rest/v1/fixtures",
            headers=self._headers(),
            params=[
                ("select", "match_id_hash,home_team,away_team,league,kickoff_utc"),
                ("kickoff_utc", f"gte.{start_utc.isoformat().replace('+00:00', 'Z')}"),
                ("kickoff_utc", f"lt.{end_utc.isoformat().replace('+00:00', 'Z')}"),
                ("order", "kickoff_utc.asc"),
                ("limit", "1000"),
            ],
        )
        if response.status_code != 200:
            raise SXFSourceError(f"fixtures read failed: HTTP {response.status_code}: {response.text[:240]}")
        data = response.json()
        return data if isinstance(data, list) else []

    @staticmethod
    def _is_statement_timeout(exc: SXFSourceError) -> bool:
        text = str(exc).lower()
        return "statement timeout" in text or '"57014"' in text or "code': '57014" in text

    def _history_rows_batch(self, table: str, select: str, batch: list[str]) -> list[dict[str, Any]]:
        if not batch:
            return []
        rows: list[dict[str, Any]] = []
        page_size = 1000
        offset = 0
        try:
            while True:
                page = self._get(
                    table,
                    {
                        "select": select,
                        "match_id_hash": f"in.({','.join(batch)})",
                        "order": "scraped_at.asc",
                        "limit": str(page_size),
                        "offset": str(offset),
                    },
                )
                rows.extend(page)
                if len(page) < page_size:
                    return rows
                offset += page_size
                if offset >= 50000:
                    raise SXFSourceError(f"{table} pagination safety limit reached")
        except SXFSourceError as exc:
            if len(batch) > 1 and self._is_statement_timeout(exc):
                midpoint = len(batch) // 2
                left = self._history_rows_batch(table, select, batch[:midpoint])
                right = self._history_rows_batch(table, select, batch[midpoint:])
                return left + right
            raise

    def _history_rows(self, table: str, select: str, hashes: list[str]) -> list[dict[str, Any]]:
        rows: list[dict[str, Any]] = []
        for start in range(0, len(hashes), self._HISTORY_BATCH_SIZE):
            batch = hashes[start:start + self._HISTORY_BATCH_SIZE]
            rows.extend(self._history_rows_batch(table, select, batch))
        return rows

    @staticmethod
    def _point_before(points: list[tuple], target: datetime):
        candidates = [item for item in points if item[0] <= target]
        return candidates[-1] if candidates else None

    @classmethod
    def _selection_feature(cls, rows: list[dict[str, Any]], odds_key: str, pct_key: str, amt_key: str, now: datetime) -> dict[str, Any] | None:
        points: list[tuple[datetime, float, float, float, float | None]] = []
        for row in rows:
            observed = _iso(row.get("scraped_at"))
            odds = _number(row.get(odds_key))
            pct = _number(row.get(pct_key))
            amt = _number(row.get(amt_key))
            vol = _number(row.get("volume"))
            if observed is None or odds is None or pct is None or amt is None:
                continue
            points.append((observed, odds, pct, amt, vol))
        if not points:
            return None
        points.sort(key=lambda item: item[0])
        first, last = points[0], points[-1]
        checkpoints = {
            "h24": cls._point_before(points, now - timedelta(hours=24)),
            "h12": cls._point_before(points, now - timedelta(hours=12)),
            "h6": cls._point_before(points, now - timedelta(hours=6)),
            "h3": cls._point_before(points, now - timedelta(hours=3)),
            "h1": cls._point_before(points, now - timedelta(hours=1)),
            "m30": cls._point_before(points, now - timedelta(minutes=30)),
            "m15": cls._point_before(points, now - timedelta(minutes=15)),
        }
        directions: list[int] = []
        pivot = points[0][1]
        for point in points[1:]:
            odds = point[1]
            if pivot and abs(odds - pivot) / pivot >= 0.005:
                direction = 1 if odds > pivot else -1
                if not directions or direction != directions[-1]:
                    directions.append(direction)
                pivot = odds

        def packed(point):
            if point is None:
                return None
            return {"observed_at": point[0].isoformat(), "odds": point[1], "share": point[2], "amount": point[3], "volume": point[4]}

        def delta(left, right, index):
            if left is None or right is None:
                return None
            return round(right[index] - left[index], 4)

        feature = {
            "history_count": len(points),
            "first": packed(first),
            "last": packed(last),
            "odds_range": [min(p[1] for p in points), max(p[1] for p in points)],
            "reversal_segments": len(directions),
            "open_to_latest": {
                "odds_delta": delta(first, last, 1),
                "share_delta": delta(first, last, 2),
                "amount_delta": delta(first, last, 3),
            },
            "latest_age_seconds": max(0, round((now - last[0].astimezone(timezone.utc)).total_seconds())),
        }
        for name, point in checkpoints.items():
            feature[name] = packed(point)
            feature[f"{name}_to_latest"] = {
                "odds_delta": delta(point, last, 1),
                "share_delta": delta(point, last, 2),
                "amount_delta": delta(point, last, 3),
            }
        return feature

    def build_stage1_context(self, scope: dict[str, Any], *, now: datetime | None = None) -> dict[str, Any]:
        if not isinstance(scope, dict):
            raise SXFSourceError("scope must be an object")
        now = now or datetime.now(timezone.utc)
        if now.tzinfo is None:
            now = now.replace(tzinfo=timezone.utc)
        now = now.astimezone(timezone.utc)
        start_local, end_local, tz = self._resolve_window(scope, now)
        start_utc = start_local.astimezone(timezone.utc)
        end_utc = end_local.astimezone(timezone.utc)
        fixtures = self._fixtures_window(start_utc, end_utc) if start_utc < end_utc else []
        fixture_ids = [str(item.get("match_id_hash") or "").strip() for item in fixtures]
        fixture_ids = [item for item in fixture_ids if item]
        histories: dict[str, dict[str, list[dict[str, Any]]]] = {fid: {} for fid in fixture_ids}
        if fixture_ids:
            for market, config in self._MARKETS.items():
                rows = self._history_rows(config["table"], config["select"], fixture_ids)
                for row in rows:
                    fid = str(row.get("match_id_hash") or "").strip()
                    if fid in histories:
                        histories[fid].setdefault(market, []).append(row)

        trusted_fixtures: list[dict[str, Any]] = []
        price_evidence: list[dict[str, Any]] = []
        for fixture in fixtures:
            fid = str(fixture.get("match_id_hash") or "").strip()
            if not fid:
                continue
            market_features: dict[str, Any] = {}
            history_counts: dict[str, int] = {}
            for market, config in self._MARKETS.items():
                rows = histories[fid].get(market, [])
                history_counts[market] = len(rows)
                selections: dict[str, Any] = {}
                for selection, keys in config["selections"].items():
                    feature = self._selection_feature(rows, *keys, now)
                    selections[selection] = feature
                    if feature and feature.get("last"):
                        latest = feature["last"]
                        price_evidence.append(
                            {
                                "fixture_id": fid,
                                "origin": "SXF_NATIVE",
                                "source": "SXF",
                                "market": market,
                                "selection": selection,
                                "price": latest["odds"],
                                "observed_at": latest["observed_at"],
                                "status": "OBSERVED",
                            }
                        )
                market_features[market] = selections
            trusted_fixtures.append(
                {
                    "fixture_id": fid,
                    "home": fixture.get("home_team") or "",
                    "away": fixture.get("away_team") or "",
                    "league": fixture.get("league") or "",
                    "kickoff_utc": fixture.get("kickoff_utc") or "",
                    "history_counts": history_counts,
                    "markets": market_features,
                }
            )
        return {
            "source": "SXF_PRODUCTION_READ_ONLY",
            "generated_at": now.isoformat(),
            "timezone": str(tz),
            "window": {"start": start_local.isoformat(), "end": end_local.isoformat(), "future_only": scope.get("future_only", True) is not False},
            "source_fixture_ids": [item["fixture_id"] for item in trusted_fixtures],
            "fixtures": trusted_fixtures,
            "price_evidence": price_evidence,
        }
