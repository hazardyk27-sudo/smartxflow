"""Read-only, server-side feed for the replacement SmartXFlow Analizler panel.

Never uses legacy analysis rows. Only completed SXF Base signal events, never
opens service_role access to browsers. No odds or outcomes are inferred.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
import re
from zoneinfo import ZoneInfo
from uuid import UUID

import requests

TR_TZ = ZoneInfo("Europe/Istanbul")
VISIBLE_KINDS = frozenset(("EARLY_SIGNAL", "PRELIMINARY_SIGNAL", "FINAL_SIGNAL", "CORRECTED", "MARKET_DECISION"))
KNOWN_ENGINES = (
    "EARLY_MONEY_CORE", "EARLY_MONEY_T12", "1X2_CONCENTRATION_V1",
    "1X2_CONCENTRATION_V2", "HEAVY_1X2_CONCENTRATION", "SURPRISE_TEAM",
    "STABLE_OVER_2_5", "PREMIUM_OVER_2_5", "PREMIUM_OVER_MIN1_70", "BTTS_YES",
)
FIELDS = "event_id,job_id,fixture_uid,kickoff_utc,kind,engine,market,selection,family,job_checkpoint_hours,source_checkpoint_hours,recorded_at,details"
PAGE_SIZE = 250
MAX_PAGES = 8
CHUNK_SIZE = 75


class BaseFeedUnavailable(Exception):
    """Missing/oversized/untrusted private Base data: never serve partial results."""


def parse_day(value: str) -> date:
    if not isinstance(value, str) or len(value) != 10:
        raise ValueError("day must be YYYY-MM-DD")
    parsed = date.fromisoformat(value)
    if parsed.isoformat() != value:
        raise ValueError("non-canonical day")
    return parsed


def _utc(dt: str) -> datetime:
    if not isinstance(dt, str):
        raise BaseFeedUnavailable("missing timestamp")
    try:
        result = datetime.fromisoformat(dt.replace("Z", "+00:00"))
        if result.tzinfo is None:
            raise ValueError()
        return result.astimezone(timezone.utc)
    except ValueError as exc:
        raise BaseFeedUnavailable("invalid timestamp") from exc


def _uid(value):
    try:
        item = str(UUID(str(value)))
        if item != value:
            raise ValueError()
        return item
    except (ValueError, TypeError) as exc:
        raise BaseFeedUnavailable("invalid physical identity") from exc


def _chunks(items, size=CHUNK_SIZE):
    for n in range(0, len(items), size):
        yield items[n:n+size]


class BaseSignalsFeed:
    def __init__(self, base_url: str, service_key: str, *, session=None):
        if not base_url.startswith("https://") or not service_key:
            raise BaseFeedUnavailable("server-only service role not configured")
        self.base = base_url.rstrip("/") + "/rest/v1/"
        self._headers = {"apikey": service_key, "Authorization": "Bearer " + service_key}
        self._session = session if session is not None else requests.Session()

    def _get(self, table, params):
        if table not in ("sxf_base_signal_events", "sxf_base_checkpoint_jobs",
                         "fixtures", "live_fixtures"):
            raise BaseFeedUnavailable("forbidden source")
        try:
            response = self._session.get(self.base + table, params=params,
                                         headers=self._headers, timeout=12)
            if response.status_code not in (200, 206):
                raise BaseFeedUnavailable("private signal source HTTP failure")
            rows = response.json()
            if not isinstance(rows, list) or any(not isinstance(x, dict) for x in rows):
                raise BaseFeedUnavailable("invalid private response")
            return rows
        except BaseFeedUnavailable:
            raise
        except (requests.RequestException, ValueError, TypeError) as exc:
            raise BaseFeedUnavailable("private signal source unavailable") from exc


    def _finished_results(self, items, fixtures):
        """Optional read-only scoreboard enrichment.

        Historical live_fixtures rows have NULL fixture_uid, so joining only
        by fixture_uid hides all results. Hash fallback is accepted *only* if
        the original teams, league and exact kickoff also agree. No score may
        be inferred from betting selections or from in-play score snapshots.
        Ambiguous, mismatched or malformed rows have no settlement.
        """
        indexed = {}
        ambiguous = set()
        for item in items:
            fixture = fixtures[item["uid"]]
            match_hash = str(fixture.get("match_id_hash") or "").strip().lower()
            if not re.fullmatch(r"[0-9a-f]{12}", match_hash):
                continue
            prev = indexed.get(match_hash)
            if prev is not None and prev["fixture_uid"] != item["uid"]:
                ambiguous.add(match_hash)
            indexed[match_hash] = fixture

        results = {}
        source_state = "ok"
        try:
            for chunk in _chunks(sorted(indexed)):
                rows = self._get("live_fixtures", [
                    ("select", "fixture_uid,match_id_hash,home_team,away_team,league,kickoff_utc,score,status,minute,updated_at"),
                    ("match_id_hash", "in.(" + ",".join(chunk) + ")"),
                    ("limit", str(len(chunk) + 1)),
                ])
                for result in rows:
                    h = str(result.get("match_id_hash") or "").strip().lower()
                    if h not in indexed or h in results:
                        ambiguous.add(h)
                    else:
                        results[h] = result
        except BaseFeedUnavailable:
            # The Base pick ledger must remain readable when the independent
            # scoreboard provider is unhealthy. It simply cannot be settled.
            source_state = "unavailable"
            results = {}

        for item in items:
            item["result_state"] = "UNAVAILABLE" if source_state != "ok" else "PENDING"
            item["final_score"] = None
            item["outcome"] = None
            fixture = fixtures[item["uid"]]
            h = str(fixture.get("match_id_hash") or "").strip().lower()
            row = results.get(h)
            if not row or h in ambiguous:
                continue
            # Reject false hash associations, including the historical
            # fixture_uid backfill gap and any kickoff drift.
            result_uid = row.get("fixture_uid")
            if result_uid and result_uid != item["uid"]:
                continue
            def normalized(value):
                return " ".join(str(value or "").split()).casefold()
            if any(normalized(row.get(k)) != normalized(fixture.get(k)) for k in
                   ("home_team", "away_team", "league")):
                continue
            try:
                if _utc(row.get("kickoff_utc")) != _utc(fixture.get("kickoff_utc")):
                    continue
            except BaseFeedUnavailable:
                continue
            status = str(row.get("status") or "").strip().lower()
            minute = str(row.get("minute") or "").strip().upper()
            if status not in ("ft", "finished", "fulltime", "full_time") and minute != "FT":
                continue
            score = str(row.get("score") or "").strip()
            m = re.fullmatch(r"(\d{1,2})\s*-\s*(\d{1,2})", score)
            if not m:
                continue
            home, away = map(int, m.groups())
            if home > 30 or away > 30:
                continue
            item["final_score"] = f"{home}-{away}"
            item["result_state"] = "FT"
            selection, market = item["selection"], item["market"]
            win = None
            if market == "1X2" and selection in ("1", "X", "2"):
                winner = "1" if home > away else ("2" if away > home else "X")
                win = selection == winner
            elif market == "OU25" and selection in ("O", "U"):
                win = (home + away > 2) if selection == "O" else (home + away < 3)
            elif market == "BTTS" and selection in ("Y", "N"):
                both = home > 0 and away > 0
                win = both if selection == "Y" else not both
            if win is not None:
                item["outcome"] = "WIN" if win else "LOSS"
        return source_state

    def read(self, start: date, *, days: int = 21):
        if not isinstance(start, date) or type(days) is not int or not 1 <= days <= 21:
            raise ValueError("invalid bounded date window")
        today = datetime.now(TR_TZ).date()
        if start < today - timedelta(days=45) or start > today + timedelta(days=21):
            raise ValueError("date window outside allowed history")
        end = start + timedelta(days=days)
        start_utc = datetime.combine(start, datetime.min.time(), TR_TZ).astimezone(timezone.utc)
        end_utc = datetime.combine(end, datetime.min.time(), TR_TZ).astimezone(timezone.utc)
        rows = []
        for page in range(MAX_PAGES):
            batch = self._get("sxf_base_signal_events", [
                ("select", FIELDS),
                ("kickoff_utc", "gte." + start_utc.isoformat()),
                ("kickoff_utc", "lt." + end_utc.isoformat()),
                ("ruleset_version", "eq.SXF_SIGNAL_MOTOR_V2_2026_10_22"),
                ("kind", "in.(" + ",".join(sorted(VISIBLE_KINDS)) + ")"),
                ("order", "event_id.asc"),
                ("limit", str(PAGE_SIZE)),
                ("offset", str(page*PAGE_SIZE)),
            ])
            if len(batch) > PAGE_SIZE:
                raise BaseFeedUnavailable("unbounded event page")
            rows.extend(batch)
            if len(batch) < PAGE_SIZE:
                break
        else:
            # Never say a day is empty due to truncated results.
            raise BaseFeedUnavailable("signal event window exceeds safety limit")

        # Join server-side, not in the browser, and reject stale/foreign jobs.
        ids = sorted({_uid(row.get("fixture_uid")) for row in rows})
        job_ids = sorted({_uid(row.get("job_id")) for row in rows})
        fixtures, jobs = {}, {}
        for chunk in _chunks(ids):
            got = self._get("fixtures", [
                ("select", "fixture_uid,home_team,away_team,league,kickoff_utc,match_id_hash"),
                ("fixture_uid", "in.(" + ",".join(chunk) + ")"),
                ("limit", str(len(chunk) + 1)),
            ])
            for item in got:
                key = _uid(item.get("fixture_uid"))
                if key in fixtures:
                    raise BaseFeedUnavailable("duplicate fixture identity")
                fixtures[key] = item
        for chunk in _chunks(job_ids):
            got = self._get("sxf_base_checkpoint_jobs", [
                ("select", "job_id,fixture_uid,kickoff_utc,state"),
                ("job_id", "in.(" + ",".join(chunk) + ")"),
                ("limit", str(len(chunk) + 1)),
            ])
            for item in got:
                key = _uid(item.get("job_id"))
                if key in jobs:
                    raise BaseFeedUnavailable("duplicate checkpoint identity")
                jobs[key] = item

        # Signal-family independence: one skipped checkpoint must never
        # suppress a COMPLETED signal produced by another family or market.

        # T-8 signals remain in the append-only ledger after an authentic
        # T-6 market decision. Label them historical, never silently present
        # them as a fresh final recommendation.
        authoritative_t6 = set()
        for event in rows:
            if (event.get("kind") != "MARKET_DECISION" or
                    event.get("job_checkpoint_hours") != 6 or
                    event.get("source_checkpoint_hours") != 6 or
                    not isinstance(event.get("details"), dict) or
                    event["details"].get("state") != "AUTHORITATIVE_T6"):
                continue
            source_job = jobs.get(_uid(event.get("job_id")))
            if source_job and source_job.get("state") == "COMPLETED":
                authoritative_t6.add(
                    (_uid(event.get("fixture_uid")), event.get("market"),
                     _utc(event.get("kickoff_utc"))))

        items, dedupe = [], set()
        for row in rows:
            ident = row.get("event_id")
            if type(ident) is not int or ident <= 0 or ident in dedupe:
                raise BaseFeedUnavailable("duplicate/invalid signal event")
            dedupe.add(ident)
            if row.get("kind") == "MARKET_DECISION":
                # These are coverage/no-hit records, not picks, even when a
                # malformed upstream row happens to contain engine/selection.
                continue
            engine = row.get("engine")
            market = row.get("market")
            selection = row.get("selection")
            if not (isinstance(engine, str) and engine.strip() and
                    market in ("1X2", "OU25", "BTTS") and
                    isinstance(selection, str) and selection.strip() and
                    row.get("kind") in VISIBLE_KINDS):
                # A signal must never be rendered without a concrete pick.
                continue
            uid = _uid(row["fixture_uid"])
            job_id = _uid(row["job_id"])
            fixture, job = fixtures.get(uid), jobs.get(job_id)
            if not fixture or not job or job.get("state") != "COMPLETED":
                continue
            kickoff = _utc(row["kickoff_utc"])
            if (_uid(job.get("fixture_uid")) != uid or
                    _utc(job.get("kickoff_utc")) != kickoff or
                    _utc(fixture.get("kickoff_utc")) != kickoff):
                continue
            tr_day = kickoff.astimezone(TR_TZ).date().isoformat()
            if not start.isoformat() <= tr_day < end.isoformat():
                continue
            details = row.get("details")
            if not isinstance(details, dict):
                details = {}
            if row["kind"] == "CORRECTED" and details.get("decision") != "HIT":
                # A NO_HIT correction is not a fresh betting signal.
                continue
            historical_t8 = (
                row["kind"] == "PRELIMINARY_SIGNAL"
                and (uid, market, kickoff) in authoritative_t6
            )
            observed = details.get("observed_at")
            try:
                observed = _utc(observed).isoformat() if observed else None
            except BaseFeedUnavailable:
                observed = None
            odds = details.get("odds")
            try:
                odds = float(odds) if odds is not None else None
                if odds is not None and not 1.01 <= odds <= 1000:
                    odds = None
            except (ValueError, TypeError):
                odds = None
            recorded = _utc(row["recorded_at"])
            checkpoint_hours = row.get("job_checkpoint_hours")
            # A belated evaluation can preserve frozen pre-match source evidence,
            # but it is not a contemporaneous alert. Never rewrite the event.
            if row["kind"] == "CORRECTED":
                delivery_timing = "RECONCILED_LATER"
            elif type(checkpoint_hours) is int and 1 <= checkpoint_hours <= 72:
                # Scheduler waits 10m for source ingestion before the job
                # can even be claimed. Allow another bounded 10m for durable
                # DB claim/evaluation/commit; >20m is historical replay.
                grace_end = kickoff - timedelta(hours=checkpoint_hours) + timedelta(minutes=20)
                delivery_timing = ("LATE_EVALUATION" if recorded > grace_end else
                                   "CHECKPOINT_WINDOW")
            else:
                delivery_timing = "UNKNOWN"
            # An append-only event is not necessarily an eligible, timely
            # prematch signal. Preserve every historic event for audit, but
            # give the UI a trustworthy count/status independent of the raw
            # ledger's kind or the time it was replayed.
            selection_status = details.get("selection_status")
            if selection_status not in ("ELIGIBLE", "PRICE_FILTER_REJECT", "HISTORY_INCOMPLETE"):
                selection_status = "UNKNOWN"
            # Never trust an inconsistent persisted eligibility label over
            # the event's own verified recorded price.
            if odds is not None and odds < 1.30:
                selection_status = "PRICE_FILTER_REJECT"
            elif odds is None or (
                selection_status == "PRICE_FILTER_REJECT" and odds >= 1.30
            ):
                selection_status = "UNKNOWN"
            recorded_on_time = (
                delivery_timing == "CHECKPOINT_WINDOW" and recorded < kickoff
            )
            valid_on_time = (
                row["kind"] in ("PRELIMINARY_SIGNAL", "FINAL_SIGNAL", "EARLY_SIGNAL")
                and selection_status == "ELIGIBLE"
                and recorded_on_time
                and not historical_t8
            )
            if selection_status == "PRICE_FILTER_REJECT":
                review_state = "PRICE_REJECTED"
            elif selection_status == "HISTORY_INCOMPLETE":
                review_state = "HISTORY_INCOMPLETE"
            elif row["kind"] == "CORRECTED":
                review_state = "RECONCILED_HISTORY"
            elif historical_t8:
                review_state = "T8_SUPERSEDED"
            elif not recorded_on_time:
                review_state = "LATE_HISTORY"
            elif selection_status != "ELIGIBLE":
                review_state = "UNVERIFIED_STATUS"
            else:
                review_state = "VALID_PREMATCH_RECORD"
            items.append({
                "id": ident,
                "uid": uid,
                "match_hash": str(fixture.get("match_id_hash") or "")[:20],
                "home": str(fixture.get("home_team") or "")[:100],
                "away": str(fixture.get("away_team") or "")[:100],
                "league": str(fixture.get("league") or "")[:100],
                "kickoff_utc": kickoff.isoformat(),
                "day": tr_day,
                "engine": engine[:80],
                "market": market,
                "selection": selection[:32],
                "kind": row["kind"],
                "stage_status": "T8_HISTORICAL" if historical_t8 else "AS_RECORDED",
                "family": str(row.get("family") or "")[:35],
                "checkpoint": row.get("job_checkpoint_hours"),
                "source_checkpoint": row.get("source_checkpoint_hours"),
                "recorded_at": recorded.isoformat(),
                "observed_at": observed,
                "delivery_timing": delivery_timing,
                "selection_status": selection_status,
                "review_state": review_state,
                "valid_on_time": valid_on_time,
                "odds": odds,
                "strength_tag": details.get("label") == "STRENGTH_TAG",
                "shadow": True,
            })
        results_source_state = self._finished_results(items, fixtures) if items else "ok"
        items.sort(key=lambda x: (x["kickoff_utc"], x["id"]))
        return {"status":"ok", "phase":"SHADOW", "timezone":"Europe/Istanbul",
                "start":start.isoformat(),"days":days, "engines":list(KNOWN_ENGINES),
                "items":items, "results_source_state":results_source_state, "source_complete":False,
                "message":"Shadow verileri test amaçlıdır; onaylanmış bahis önerisi değildir."}
