"""Server-only, bounded PRO feed adapter for the five pre-existing SXF engines.

This reads actual legacy signal rows without changing any motor rules or
calling the old public analyst APIs. It requires an unambiguous canonical
fixture match: exact team/league names, Istanbul match date, and (where
available) real kickoff UTC. Ambiguous or orphaned identities are reported
as excluded, never silently deduced into a different fixture.

No live scores, current prices, provider outcomes or timestamps are invented.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from .feed import BaseFeedUnavailable, TR_TZ, _utc, _uid

# Provenance IDs intentionally distinct from the replacement Base engine IDs.
LEGACY_SOURCES = (
    ("LEGACY_EARLY_MONEY_LOCK", "early_money_lock_signals"),
    ("LEGACY_UNDERDOG", "underdog_signals"),
    ("LEGACY_CONFIRMED_MONEY_V1", "confirmed_money_signals"),
    ("LEGACY_CONFIRMED_MONEY_V2", "confirmed_money_v2_signals"),
    ("LEGACY_FAKE_SHARP", "fake_sharp_signals"),
)
SOURCE_FIELDS = {
    "early_money_lock_signals": "id,match_key,match_date,home_team,away_team,league,selection_code,created_at,fixture_uid,kickoff_utc",
    "underdog_signals": "id,match_key,match_date,home_team,away_team,league,selection_code,created_at,fixture_uid",
    "confirmed_money_signals": "id,match_key,match_date,home_team,away_team,league,selection_code,created_at,fixture_uid",
    "confirmed_money_v2_signals": "id,match_key,match_date,home_team,away_team,league,selection_code,created_at,fixture_uid",
    "fake_sharp_signals": "id,match_key,match_date,home_team,away_team,league,selection_code,created_at,fixture_uid",
}
PAGE_SIZE = 250
MAX_PAGES = 8
MAX_FIXTURE_PAGES = 8
HOME_CHUNK = 30


def _norm(value):
    return " ".join(str(value or "").split()).casefold()


def _safe_team(value):
    if not isinstance(value, str) or not value.strip() or len(value) > 100:
        return False
    return not any(ord(ch) < 32 for ch in value)


def _iso_day(value):
    if not isinstance(value, str) or len(value) < 10:
        return None
    try:
        first = date.fromisoformat(value[:10])
    except ValueError:
        return None
    return first if first.isoformat() == value[:10] else None


def _exact_kickoff(row):
    """Only an ISO8601 timestamp can prove an exact kickoff on legacy rows."""
    original = row.get("kickoff_utc")
    key = row.get("match_key")
    fallback = key.rsplit("|", 1)[-1] if isinstance(key, str) and "|" in key else None
    for raw in (original, fallback):
        if not isinstance(raw, str) or not re.match(r"^\d{4}-\d\d-\d\dT", raw):
            continue
        try:
            return _utc(raw)
        except BaseFeedUnavailable:
            return None
    return None


def _literal_list(values):
    # PostgREST in-list quoted syntax. Reject controls and safely escape
    # commas/parentheses/quotes in club names; never compose user SQL.
    return "in.(" + ",".join(
        '"' + x.replace("\\", "\\\\").replace('"', '\\"') + '"'
        for x in values
    ) + ")"


class LegacySignalsFeed:
    def __init__(self, private_source):
        # private_source must be the authenticated server-only BaseSignalsFeed.
        self.source = private_source

    def _page(self, table, params, *, size=PAGE_SIZE, cap=MAX_PAGES):
        data = []
        for i in range(cap):
            rows = self.source._get(table, params + [
                ("order", "id.asc" if table != "fixtures" else "fixture_uid.asc"),
                ("limit", str(size)), ("offset", str(i * size)),
            ])
            if len(rows) > size:
                raise BaseFeedUnavailable("oversized legacy source page")
            data.extend(rows)
            if len(rows) < size:
                return data
        raise BaseFeedUnavailable("legacy source pagination incomplete")

    def read(self, start: date, *, days: int = 21) -> dict:
        if not isinstance(start, date) or type(days) is not int or not 1 <= days <= 21:
            raise ValueError("invalid historical signal window")
        end = start + timedelta(days=days)
        rows = []
        counts = {}
        for engine, table in LEGACY_SOURCES:
            selected = self._page(table, [
                ("select", SOURCE_FIELDS[table]),
                ("match_date", "gte." + start.isoformat()),
                ("match_date", "lt." + end.isoformat()),
            ])
            counts[engine] = len(selected)
            for record in selected:
                rows.append((engine, table, record))
        if not rows:
            return {"items": [], "engines": [x[0] for x in LEGACY_SOURCES],
                    "source_rows": counts, "identity_excluded": 0,
                    "duplicate_events_removed": 0}
        homes = sorted({record.get("home_team") for _,_,record in rows
                        if _safe_team(record.get("home_team"))})
        fixtures = {}
        start_utc = datetime.combine(start, datetime.min.time(), TR_TZ).astimezone(timezone.utc)
        end_utc = datetime.combine(end, datetime.min.time(), TR_TZ).astimezone(timezone.utc)
        # Narrow fixture query to the actual source clubs AND selected 21-day
        # window. No unbounded public.fixtures dump and no synthetic fixture.
        for n in range(0, len(homes), HOME_CHUNK):
            chunk = homes[n:n+HOME_CHUNK]
            found = self._page("fixtures", [
                ("select", "fixture_uid,home_team,away_team,league,kickoff_utc,match_id_hash"),
                ("home_team", _literal_list(chunk)),
                ("kickoff_utc", "gte." + start_utc.isoformat()),
                ("kickoff_utc", "lt." + end_utc.isoformat()),
            ], cap=MAX_FIXTURE_PAGES)
            for fixture in found:
                uid = _uid(fixture.get("fixture_uid"))
                if uid in fixtures and fixtures[uid] != fixture:
                    raise BaseFeedUnavailable("conflicting fixture source")
                fixtures[uid] = fixture

        by_match = {}
        for fixture in fixtures.values():
            stamp = _utc(fixture.get("kickoff_utc"))
            key = (_norm(fixture.get("home_team")), _norm(fixture.get("away_team")),
                   _norm(fixture.get("league")), stamp.astimezone(TR_TZ).date())
            by_match.setdefault(key, []).append(fixture)

        accepted = {}
        excluded = 0
        duplicates = 0
        for engine, table, record in rows:
            ident = record.get("id")
            home, away, league = (record.get(k) for k in ("home_team", "away_team", "league"))
            match_date = _iso_day(record.get("match_date"))
            selected = record.get("selection_code")
            key = record.get("match_key")
            if (type(ident) is not int or ident < 1 or ident >= 1_000_000_000 or
                    not all(_safe_team(x) for x in (home, away, league)) or
                    not isinstance(key, str) or
                    not key.startswith(home+"|"+away+"|") or
                    selected not in ("1", "X", "2") or match_date is None or
                    not start <= match_date < end):
                excluded += 1
                continue
            candidates = by_match.get((_norm(home),_norm(away),_norm(league),match_date), [])
            exact = _exact_kickoff(record)
            if exact is not None:
                candidates = [x for x in candidates if _utc(x["kickoff_utc"]) == exact]
            supplied_uid = record.get("fixture_uid")
            if supplied_uid:
                candidates = [x for x in candidates if _uid(x["fixture_uid"]) == _uid(supplied_uid)]
            if len(candidates) != 1:
                excluded += 1
                continue
            fixture = candidates[0]
            uid = _uid(fixture["fixture_uid"])
            try:
                created = _utc(record["created_at"])
            except BaseFeedUnavailable:
                excluded += 1
                continue
            kickoff = _utc(fixture["kickoff_utc"])
            dedupe = (engine, uid, kickoff, selected)
            entry = {
                # Large, noncolliding, JS-safe numeric ID, distinct per engine.
                "id": 10_000_000_000 + [x[0] for x in LEGACY_SOURCES].index(engine) * 1_000_000_000 + ident,
                "uid": uid, "match_hash": str(fixture.get("match_id_hash") or "")[:20],
                "home": str(fixture.get("home_team") or "")[:100],
                "away": str(fixture.get("away_team") or "")[:100],
                "league": str(fixture.get("league") or "")[:100],
                "kickoff_utc": kickoff.isoformat(),
                "day": match_date.isoformat(),
                "engine": engine, "market": "1X2", "selection": selected,
                "kind": "LEGACY_SIGNAL", "stage_status": "LEGACY_RECORDED",
                "family": "LEGACY", "checkpoint": None,
                "source_checkpoint": None,
                "recorded_at": created.isoformat(), "observed_at": None,
                "odds": None, "strength_tag": False,
                "delivery_timing": "UNKNOWN", "origin_table": table,
                "source_record_id": ident, "identity_status": "VERIFIED_FIXTURE",
                "shadow": False, "result_state": "PENDING",
                "final_score": None, "outcome": None,
            }
            old = accepted.get(dedupe)
            if old is not None:
                duplicates += 1
            if old is None or (entry["recorded_at"], entry["source_record_id"]) > (
                old["recorded_at"], old["source_record_id"]):
                accepted[dedupe] = entry
        items = sorted(accepted.values(), key=lambda item: (item["kickoff_utc"],item["engine"],item["id"]))
        return {"items": items, "engines": [x[0] for x in LEGACY_SOURCES],
                "source_rows": counts, "identity_excluded": excluded,
                "duplicate_events_removed": duplicates}
