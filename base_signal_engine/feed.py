"""Read-only, server-side feed for the replacement SmartXFlow Analizler panel.

Never uses legacy analysis rows. Only completed SXF Base signal events, never
opens service_role access to browsers. No odds or outcomes are inferred.
"""
from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
import re
from zoneinfo import ZoneInfo
from uuid import UUID

import requests

from .scheduler import RULESET_VERSION


TR_TZ = ZoneInfo("Europe/Istanbul")
VISIBLE_KINDS = frozenset(("EARLY_SIGNAL", "PRELIMINARY_SIGNAL", "FINAL_SIGNAL", "CORRECTED", "MARKET_DECISION", "RETENTION_CHECK"))
KNOWN_ENGINES = (
    "EARLY_MONEY_CORE", "EARLY_MONEY_T12", "1X2_CONCENTRATION_V1",
    "1X2_CONCENTRATION_V2", "HEAVY_1X2_CONCENTRATION", "SURPRISE_TEAM",
    "STABLE_OVER_2_5", "PREMIUM_OVER_2_5", "PREMIUM_OVER_MIN1_70", "BTTS_YES",
)
FIELDS = "event_id,job_id,fixture_uid,kickoff_utc,kind,engine,market,selection,family,job_checkpoint_hours,source_checkpoint_hours,recorded_at,details,ruleset_version"
PAGE_SIZE = 250
MAX_PAGES = 8
CHUNK_SIZE = 75


# Frozen v3 price bands from the pure Base evaluator.  For engines not
# constrained by that kernel, preserve the general 1.30 selection floor.
V3_PRICE_BANDS = {
    "1X2_CONCENTRATION_V1": (1.40, 2.50),
    "1X2_CONCENTRATION_V2": (1.40, 2.50),
    "HEAVY_1X2_CONCENTRATION": (1.40, 2.50),
    "SURPRISE_TEAM": (2.90, 4.49),
    "STABLE_OVER_2_5": (1.40, 1.80),
    "PREMIUM_OVER_2_5": (1.40, 1.80),
    "PREMIUM_OVER_MIN1_70": (1.70, 1.80),
    "BTTS_YES": (1.60, 1.90),
}


def _v3_price_in_range(engine: str, odds: float | None) -> bool:
    if odds is None or not 1.30 <= odds <= 1000:
        return False
    limits = V3_PRICE_BANDS.get(engine)
    return limits is None or limits[0] <= odds <= limits[1]


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
                         "fixtures", "live_fixtures", "moneyway_snapshots"):
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

    def _enrich_current_1x2(self, items, *, now=None):
        """Bounded live threshold enrichment, independent from saved checkpoints.

        This does NOT re-run V2 three-hour persistence. Never treat stale,
        partial, future or post-kickoff quotes as verified. Failed optional
        reads leave the historical signal feed intact.
        """
        now = now or datetime.now(timezone.utc)
        families = frozenset(("1X2_CONCENTRATION_V1", "1X2_CONCENTRATION_V2",
                              "HEAVY_1X2_CONCENTRATION"))
        active = {}
        for item in items:
            if item["engine"] not in families:
                continue
            kickoff = _utc(item["kickoff_utc"])
            if now >= kickoff:
                item["as_of_state"] = "AFTER_KICKOFF"
            elif kickoff > now + timedelta(hours=24):
                item["as_of_state"] = "OUTSIDE_WINDOW"
            else:
                active.setdefault(item["uid"], []).append(item)
        # A 21-day response cannot fan out into dozens of network round trips.
        # One batched, full-page-complete private read covers imminent fixtures.
        if not active or len(active) > 25:
            return
        rows = []
        try:
            for page in range(4):
                batch = self._get("moneyway_snapshots", [
                    ("select", "id,fixture_uid,market,selection,odds,volume,share,scraped_at_utc"),
                    ("fixture_uid", "in.(" + ",".join(sorted(active)) + ")"),
                    ("market", "eq.1X2"),
                    ("scraped_at_utc", "gte." + (now - timedelta(minutes=15)).isoformat()),
                    ("scraped_at_utc", "lte." + now.isoformat()),
                    ("order", "scraped_at_utc.desc,id.desc"),
                    ("limit", str(PAGE_SIZE)), ("offset", str(page * PAGE_SIZE)),
                ])
                if len(batch) > PAGE_SIZE:
                    return
                rows.extend(batch)
                if len(batch) < PAGE_SIZE:
                    break
            else:
                # Do not claim live validity when a bounded source is truncated.
                return
        except BaseFeedUnavailable:
            return
        groups = {}
        for raw in rows:
            try:
                uid = _uid(raw.get("fixture_uid"))
                if uid not in active or raw.get("market") != "1X2":
                    continue
                at = _utc(raw.get("scraped_at_utc"))
                if not now - timedelta(minutes=15) <= at <= now:
                    continue
                groups.setdefault(uid, {}).setdefault(at, []).append(raw)
            except BaseFeedUnavailable:
                continue
        for uid, related in active.items():
            for at in sorted(groups.get(uid, {}), reverse=True):
                group = groups[uid][at]
                if len(group) != 3 or {q.get("selection") for q in group} != {"1", "X", "2"}:
                    continue
                try:
                    quotes = {q["selection"]: {
                        "odds": Decimal(str(q["odds"])),
                        "share": Decimal(str(q["share"])),
                        "amount": Decimal(str(q["volume"])),
                    } for q in group}
                    if any(not all(v.is_finite() for v in q.values())
                           or q["odds"] < 1 or q["amount"] < 0
                           or not 0 <= q["share"] <= 100 for q in quotes.values()):
                        continue
                    if abs(sum((q["share"] for q in quotes.values()), Decimal(0)) - 100) > Decimal("0.5"):
                        continue
                except (ValueError, TypeError, InvalidOperation, KeyError):
                    continue
                leader = ("1" if quotes["1"]["amount"] >= quotes["2"]["amount"] else "2")
                for item in related:
                    side = item["selection"]
                    if side not in ("1", "2"):
                        continue
                    q = quotes[side]
                    v1 = (side == leader and q["amount"] >= 1000 and q["share"] >= 80
                          and Decimal("1.40") <= q["odds"] <= Decimal("2.50"))
                    heavy = v1 and q["amount"] >= 10000
                    passed = heavy if item["engine"] == "HEAVY_1X2_CONCENTRATION" else v1
                    item["as_of_state"] = "THRESHOLD_PASS" if passed else "THRESHOLD_FAIL"
                    item["as_of_scope"] = ("V1_BASE_ONLY" if item["engine"] == "1X2_CONCENTRATION_V2"
                                            else "CURRENT_THRESHOLDS")
                    item["as_of_checked_at"] = at.isoformat()
                break

    def read(self, start: date, *, days: int = 21, as_of_utc: datetime | None = None):
        if not isinstance(start, date) or type(days) is not int or not 1 <= days <= 21:
            raise ValueError("invalid bounded date window")
        if as_of_utc is not None and (
            not isinstance(as_of_utc, datetime) or as_of_utc.tzinfo is None
            or as_of_utc.utcoffset() is None
        ):
            raise ValueError("as_of_utc must be timezone-aware")
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
                ("ruleset_version", "eq." + RULESET_VERSION),
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
                ("select", "job_id,fixture_uid,kickoff_utc,state,ruleset_version"),
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
                     _utc(event.get("kickoff_utc")),
                     event.get("ruleset_version") or RULESET_VERSION))

        # Retention checkpoints are audit events, never standalone picks.
        # Validate their immutable job/fixture identity before using them as
        # enrichment on the original Early Core side and first checkpoint.
        retention = {}
        retention_states = {"RETAINED_AT_CHECKPOINT", "RETENTION_BREAK", "INSUFFICIENT_DATA"}
        read_as_of = (as_of_utc.astimezone(timezone.utc) if as_of_utc is not None
                      else datetime.now(timezone.utc))
        for event in rows:
            if event.get("kind") != "RETENTION_CHECK":
                continue
            uid = _uid(event.get("fixture_uid"))
            job_id = _uid(event.get("job_id"))
            job, fixture = jobs.get(job_id), fixtures.get(uid)
            if not job or not fixture or job.get("state") != "COMPLETED":
                continue
            kickoff = _utc(event.get("kickoff_utc"))
            if (_uid(job.get("fixture_uid")) != uid or
                    _utc(job.get("kickoff_utc")) != kickoff or
                    _utc(fixture.get("kickoff_utc")) != kickoff):
                continue
            h = event.get("job_checkpoint_hours")
            if type(h) is not int or h not in (6, 5, 4, 3):
                continue
            details = event.get("details")
            if not isinstance(details, dict):
                continue
            side, cp, state = (details.get("first_core_side"),
                               details.get("first_core_checkpoint"),
                               details.get("current_checkpoint_state"))
            if side not in ("1", "2") or type(cp) is not int or cp not in (72,60,40,24):
                continue
            if state not in retention_states or kickoff-timedelta(hours=h) > read_as_of:
                continue
            if _utc(event.get("recorded_at")) > read_as_of:
                continue
            key = (uid, kickoff, side, cp,
                   event.get("ruleset_version") or RULESET_VERSION)
            # An identical T checkpoint must never get two contradictory
            # completed retention verdicts.
            group = retention.setdefault(key, {})
            if h in group and group[h] != state:
                raise BaseFeedUnavailable("contradictory retention audit")
            group[h] = state

        items, dedupe = [], set()
        for row in rows:
            # A stale/misconfigured storage response must not cross rulesets.
            if row.get("ruleset_version") != RULESET_VERSION:
                continue
            ident = row.get("event_id")
            if type(ident) is not int or ident <= 0 or ident in dedupe:
                raise BaseFeedUnavailable("duplicate/invalid signal event")
            dedupe.add(ident)
            if row.get("kind") in ("MARKET_DECISION", "RETENTION_CHECK"):
                # Coverage and retention are audit state, not new signals.
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
                and (uid, market, kickoff,
                     row.get("ruleset_version") or RULESET_VERSION) in authoritative_t6
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
            # A persisted detection is not automatically an eligible signal.
            # Rejected, unverified and incomplete-history detections remain
            # in the append-only audit ledger, NEVER in the public signal feed.
            # This also excludes low-price T-8/T-6/Early events before motor
            # cards, same-side badges, totals or historical details are built.
            if selection_status != "ELIGIBLE":
                continue
            # Independent read-side guard: the persisted ELIGIBLE flag can
            # never bypass frozen V3 engine price limits (notably HEAVY 1.40).
            # Old-version audit events never enter the active signal feed.
            if not _v3_price_in_range(engine, odds):
                continue
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
            retained = None
            if engine == "EARLY_MONEY_CORE":
                source_h = row.get("source_checkpoint_hours")
                history = retention.get((uid, kickoff, selection, source_h,
                                         row.get("ruleset_version") or RULESET_VERSION), {})
                reached = {h for h in (6,5,4,3)
                           if kickoff-timedelta(hours=h) <= read_as_of}
                if any(state == "RETENTION_BREAK" for state in history.values()):
                    retention_status = "BROKEN"
                elif all(history.get(h) == "RETAINED_AT_CHECKPOINT" for h in (6,5,4,3)):
                    retention_status = "RETAINED"
                elif any(h not in history or history[h] == "INSUFFICIENT_DATA" for h in reached):
                    retention_status = "INCOMPLETE"
                else:
                    retention_status = "PENDING"
                retained = {
                    "status": retention_status,
                    "confirmed": sorted((h for h, state in history.items()
                                         if state == "RETAINED_AT_CHECKPOINT"), reverse=True),
                    "checked": sorted(history, reverse=True),
                    "required": [6, 5, 4, 3],
                }
            items.append({
                "retention": retained,
                "as_of_state": "NOT_RECHECKED",
                "as_of_checked_at": None,
                "id": ident,
                "ruleset_version": row.get("ruleset_version") or RULESET_VERSION,
                "ruleset_status": "CURRENT",
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
        if items:
            self._enrich_current_1x2(items, now=read_as_of)
        items.sort(key=lambda x: (x["kickoff_utc"], x["id"]))
        return {"status":"ok", "phase":"SHADOW", "timezone":"Europe/Istanbul",
                "ruleset_mode":"CURRENT",
                "ruleset_version":RULESET_VERSION,
                "start":start.isoformat(),"days":days, "engines":list(KNOWN_ENGINES),
                "items":items, "results_source_state":results_source_state, "source_complete":False,
                "message":"Shadow verileri test amaçlıdır; onaylanmış bahis önerisi değildir."}
