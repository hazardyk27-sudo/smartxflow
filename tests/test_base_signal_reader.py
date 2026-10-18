"""Prove the production Moneyway input boundary without database credentials."""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from uuid import UUID

import pytest

from base_signal_engine import Fixture, choose_base_checkpoint, evaluate_base
from base_signal_engine.reader import SnapshotReadError, SupabaseMoneywayReader

KICKOFF = datetime(2026, 10, 19, 20, 0, tzinfo=timezone.utc)
UID = "ef5c99bf-e002-451b-b401-af9174ad53f0"
HASH = "test-legacy-hash"
FX = Fixture(UID, KICKOFF)


class Response:
    status_code = 200

    def __init__(self, rows):
        self.rows = rows

    def json(self):
        return self.rows


class FakeSession:
    """Reproduce PostgREST filtering, pagination and ordering for frozen rows."""
    def __init__(self, snapshots=(), fixtures=None, failure_status=None):
        self.snapshots = list(snapshots)
        self.fixtures = fixtures if fixtures is not None else [
            {"fixture_uid": UID, "match_id_hash": HASH, "kickoff_utc": KICKOFF.isoformat()}
        ]
        self.calls = []
        self.failure_status = failure_status

    def get(self, url, params, headers, timeout):
        self.calls.append((url, dict(params)))
        if self.failure_status:
            result = Response([])
            result.status_code = self.failure_status
            return result
        p = dict(params)
        if url.endswith("/fixtures"):
            rows = [f for f in self.fixtures if f["fixture_uid"] == p["fixture_uid"][3:]]
        else:
            assert url.endswith("/moneyway_snapshots")
            start = datetime.fromisoformat(p["scraped_at_utc"].split("gte.")[1]) if p["scraped_at_utc"].startswith("gte.") else None
            # dict() collapses repeated `scraped_at_utc` filters; emulate actual multi-param HTTP here.
            for name, val in params:
                if name == "scraped_at_utc" and val.startswith("gte."):
                    start = datetime.fromisoformat(val[4:])
                if name == "scraped_at_utc" and val.startswith("lte."):
                    end = datetime.fromisoformat(val[4:])
            rows = [r for r in self.snapshots if r["fixture_uid"] == p["fixture_uid"][3:]
                    and start <= r["scraped_at_utc"] <= end]
            rows.sort(key=lambda r: (r["scraped_at_utc"], r["id"]))
        offset = int(p.get("offset", 0))
        limit = int(p.get("limit", len(rows)))
        return Response(rows[offset:offset + limit])


def at(h):
    return KICKOFF - timedelta(hours=h, minutes=4)


def market_rows(market, when, *, uid=UID, hsh=HASH, amount=3000):
    if market == "1X2":
        picks = {"1": ("1.74", amount, "85"), "X": ("3.7", "200", "10"), "2": ("5.0", "100", "5")}
    elif market == "OU25":
        picks = {"O": ("1.72", "4000", "80"), "U": ("2.2", "500", "20")}
    else:
        picks = {"Y": ("1.75", "900", "65"), "N": ("2.0", "400", "35")}
    offset = {"1X2": 1, "OU25": 10, "BTTS": 20}[market]
    return [{"id": int(when.timestamp()) * 100 + offset + j, "fixture_uid": uid, "match_id_hash": hsh,
             "scraped_at_utc": when, "market": market, "selection": side,
             "odds": odd, "volume": vol, "share": pct}
            for j, (side, (odd, vol, pct)) in enumerate(picks.items())]


def repo(rows, **kwargs):
    session = FakeSession(rows)
    return SupabaseMoneywayReader("https://example.supabase.co", "private-test-token", session=session, **kwargs), session


def test_fixture_is_authoritatively_uid_resolved():
    reader, session = repo([])
    fixture, legacy = reader.load_fixture(UID)
    assert fixture == FX and legacy == HASH
    assert session.calls[0][0].endswith("/fixtures")
    assert session.calls[0][1]["fixture_uid"] == "eq." + UID


def test_t6_all_three_markets_feed_real_kernel_and_v2_history():
    rows = []
    for h in (9, 8, 7, 6):
        rows.extend(market_rows("1X2", at(h)))
    rows += market_rows("OU25", at(6)) + market_rows("BTTS", at(6))
    reader, sess = repo(rows, page_size=5)
    result = reader.load_checkpoints(FX, hours=[6], as_of_utc=KICKOFF - timedelta(hours=5))
    assert result.fetched_rows == 16 and len(result.snapshots) == 6
    assert result.discarded_groups == 0
    ev = evaluate_base(FX, 6, result.snapshots)
    names = {s.engine for s in ev.signals}
    assert {"1X2_CONCENTRATION_V1", "1X2_CONCENTRATION_V2", "STABLE_OVER_2_5",
            "PREMIUM_OVER_2_5", "PREMIUM_OVER_MIN1_70", "BTTS_YES"} <= names
    assert ev.v2_state == "QUALIFIED"
    assert len([x for x in sess.calls if x[0].endswith("moneyway_snapshots")]) >= 4  # pages
    assert all(c[0].split("/rest/v1/")[1] in ("moneyway_snapshots", "fixtures") for c in sess.calls)


def test_malformed_incomplete_group_is_not_salvaged_from_other_timestamps():
    rows = market_rows("1X2", at(6))[:2] + market_rows("OU25", at(6))
    reader, _ = repo(rows)
    result = reader.load_checkpoints(FX, hours=[6], as_of_utc=KICKOFF)
    assert result.discarded_groups == 1 and len(result.snapshots) == 1
    ev = evaluate_base(FX, 6, result.snapshots)
    assert ev.market_states["1X2"] == "INSUFFICIENT_DATA"


def test_market_duplicate_side_rejected():
    rows = market_rows("OU25", at(6))
    rows.append(dict(rows[0], id=999000))
    reader, _ = repo(rows)
    result = reader.load_checkpoints(FX, hours=[6], as_of_utc=KICKOFF)
    assert result.discarded_groups == 1 and not result.snapshots


def test_bad_share_and_bad_price_rejected_without_partial_signal():
    rows = market_rows("OU25", at(6))
    rows[0]["share"] = "88"
    rows += market_rows("BTTS", at(6))
    rows[-1]["odds"] = "not-a-number"
    result = repo(rows)[0].load_checkpoints(FX, hours=[6], as_of_utc=KICKOFF)
    assert len(result.snapshots) == 0 and result.discarded_groups == 2


def test_t6_missing_t8_fallback_and_future_never_available():
    rows = market_rows("1X2", at(8))
    reader, _ = repo(rows)
    now = KICKOFF - timedelta(hours=7)
    res = reader.load_checkpoints(FX, hours=[8, 6], as_of_utc=now)
    assert choose_base_checkpoint(FX, "1X2", res.snapshots, now) == (8, "PRELIMINARY_T8")
    res2 = reader.load_checkpoints(FX, hours=[8, 6], as_of_utc=KICKOFF-timedelta(hours=5))
    assert choose_base_checkpoint(FX, "1X2", res2.snapshots, KICKOFF-timedelta(hours=5)) == (8, "FALLBACK_T8")


def test_t6_present_but_rule_fails_never_falls_back():
    rows = market_rows("1X2", at(8)) + market_rows("1X2", at(6), amount="500")
    reader, _ = repo(rows)
    out = reader.load_checkpoints(FX, hours=[8, 6], as_of_utc=KICKOFF-timedelta(hours=5))
    assert choose_base_checkpoint(FX, "1X2", out.snapshots, KICKOFF-timedelta(hours=5)) == (6, "AUTHORITATIVE_T6")
    assert "1X2_CONCENTRATION_V1" not in {s.engine for s in evaluate_base(FX, 6, out.snapshots).signals}


def test_pagination_cap_never_returns_truncated_history():
    rows = market_rows("1X2", at(6))
    reader, _ = repo(rows, page_size=2, max_pages_per_window=1)
    with pytest.raises(SnapshotReadError, match="pagination cap"):
        reader.load_checkpoints(FX, hours=[6], as_of_utc=KICKOFF)


def test_duplicate_row_id_across_pages_is_fatal():
    rows = market_rows("1X2", at(6))
    rows[1]["id"] = rows[0]["id"]
    reader, _ = repo(rows, page_size=2)
    with pytest.raises(SnapshotReadError, match="non-unique"):
        reader.load_checkpoints(FX, hours=[6], as_of_utc=KICKOFF)


def test_hash_drift_is_logged_and_uid_kept_authoritative():
    rows = market_rows("BTTS", at(8), hsh="provider-label-drift")
    reader, _ = repo(rows)
    out = reader.load_checkpoints(FX, hours=[8], as_of_utc=KICKOFF, expected_legacy_hash=HASH)
    assert out.hash_drift_rows == 2 and len(out.snapshots) == 1


def test_http_failures_are_fail_closed_and_never_leak_credentials():
    sess = FakeSession(failure_status=503)
    reader = SupabaseMoneywayReader("https://example.supabase.co", "TOP_SECRET", session=sess)
    with pytest.raises(SnapshotReadError) as err:
        reader.load_fixture(UID)
    assert "TOP_SECRET" not in str(err.value)


def test_invalid_uid_or_naive_now_rejected():
    reader, _ = repo([])
    with pytest.raises(ValueError):
        reader.load_fixture("not-a-uuid")
    with pytest.raises(ValueError, match="timezone"):
        reader.load_checkpoints(FX, hours=[6], as_of_utc=datetime(2026,10,18))


def test_multiple_checkpoint_windows_are_merged_only_when_overlap():
    reader, sess = repo([])
    result = reader.load_checkpoints(FX, hours=[72,60,40,24,12,8,6,5,4,3], as_of_utc=KICKOFF)
    assert len(result.queried_windows) == 9  # independent Early windows; overlapping T-8/T-6 lookbacks merge
    assert len([x for x in sess.calls if x[0].endswith("moneyway_snapshots") ]) == 9


def test_bad_fixture_identity_fails_closed():
    sess = FakeSession(fixtures=[{"fixture_uid": UID, "match_id_hash": HASH, "kickoff_utc": "2026-10-19 20:00:00"}])
    reader = SupabaseMoneywayReader("https://example.supabase.co", "test-token", session=sess)
    with pytest.raises(SnapshotReadError, match="invalid fixture"):
        reader.load_fixture(UID)