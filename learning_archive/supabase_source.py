from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any


MATCH_HASH_RE = re.compile(r"^[0-9a-fA-F]{12}$")

REQUIRED_HISTORY_TABLES = (
    "moneyway_1x2_history",
    "moneyway_ou25_history",
    "moneyway_btts_history",
    "dropping_1x2_history",
    "dropping_ou25_history",
    "dropping_btts_history",
)
# Double Chance / Draw No Bet storage is intentionally not part of SmartXFlow.
# Do not probe, synthesize, or report those tables as missing optional sources.
OPTIONAL_HISTORY_TABLES: tuple[str, ...] = ()
FALLBACK_HISTORY_TABLE = "moneyway_snapshots"

# Explicit response allow-list. Database/internal credential fields are never serialized.
COMMON_FIELDS = {
    "match_id_hash", "home", "away", "league", "date", "scraped_at", "scraped_at_utc",
    "volume", "market", "selection", "source", "created_at",
}
TABLE_FIELDS = {
    "moneyway_1x2_history": COMMON_FIELDS | {
        "odds1", "oddsx", "odds2", "amt1", "amtx", "amt2", "pct1", "pctx", "pct2",
    },
    "moneyway_ou25_history": COMMON_FIELDS | {
        "over", "under", "line", "amtover", "amtunder", "pctover", "pctunder",
    },
    "moneyway_btts_history": COMMON_FIELDS | {
        "yes", "no", "oddsyes", "oddsno", "amtyes", "amtno", "pctyes", "pctno",
    },
    "dropping_1x2_history": COMMON_FIELDS | {
        "opening1", "openingx", "opening2", "odds1", "odds1_prev", "oddsx", "oddsx_prev",
        "odds2", "odds2_prev", "trend1", "trendx", "trend2", "drop1", "dropx", "drop2",
        "amt1", "amtx", "amt2", "pct1", "pctx", "pct2",
    },
    "dropping_ou25_history": COMMON_FIELDS | {
        "opening_over", "opening_under", "over", "over_prev", "under", "under_prev", "line",
        "trendover", "trendunder", "drop_over", "drop_under", "pctunder", "amtunder",
        "pctover", "amtover",
    },
    "dropping_btts_history": COMMON_FIELDS | {
        "opening_yes", "opening_no", "oddsyes", "oddsyes_prev", "oddsno", "oddsno_prev",
        "trendyes", "trendno", "drop_yes", "drop_no", "pctyes", "amtyes", "pctno", "amtno",
    },
    FALLBACK_HISTORY_TABLE: COMMON_FIELDS | {"odds", "share"},
}


class LearningArchiveSourceError(RuntimeError):
    pass


class LearningArchiveInvalidHash(LearningArchiveSourceError):
    pass


class LearningArchiveMatchNotFound(LearningArchiveSourceError):
    pass


class LearningArchiveSourceUnavailable(LearningArchiveSourceError):
    pass


@dataclass(frozen=True)
class LearningArchiveHistoryPayload:
    match_id_hash: str
    match: dict[str, Any]
    histories: dict[str, list[dict[str, Any]]]
    source_tables: tuple[str, ...]
    unavailable_optional_tables: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "match_id_hash": self.match_id_hash,
            "match": self.match,
            "histories": self.histories,
            "source_tables": list(self.source_tables),
            "unavailable_optional_tables": list(self.unavailable_optional_tables),
        }


def _safe_row(table: str, row: dict[str, Any]) -> dict[str, Any]:
    allowed = TABLE_FIELDS[table]
    return {key: row.get(key) for key in allowed if key in row}


def _fetch_history_table(client: Any, table: str, match_hash: str, page_size: int = 1000) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    offset = 0
    http = client._get_http_client()
    headers = client._headers()
    order_field = "scraped_at_utc" if table == FALLBACK_HISTORY_TABLE else "scraped_at"
    while True:
        url = (
            f"{client._rest_url(table)}?select=*&match_id_hash=eq.{match_hash}"
            f"&order={order_field}.asc&limit={page_size}&offset={offset}"
        )
        response = http.get(url, headers=headers, timeout=20)
        if response.status_code != 200:
            raise LearningArchiveSourceUnavailable(
                f"history table read failed: {table} ({response.status_code})"
            )
        try:
            page = response.json()
        except Exception as exc:
            raise LearningArchiveSourceUnavailable(f"invalid JSON from history table: {table}") from exc
        if not isinstance(page, list):
            raise LearningArchiveSourceUnavailable(f"invalid history payload from table: {table}")
        for row in page:
            if not isinstance(row, dict):
                raise LearningArchiveSourceUnavailable(f"invalid history row from table: {table}")
            safe = _safe_row(table, row)
            safe_hash = str(safe.get("match_id_hash") or "").lower()
            if safe_hash and safe_hash != match_hash:
                raise LearningArchiveSourceUnavailable(f"history row identity mismatch in table: {table}")
            rows.append(safe)
        if len(page) < page_size:
            break
        offset += page_size
    return rows


def read_learning_archive_match_history(
    match_id_hash: str,
    *,
    client: Any | None = None,
) -> LearningArchiveHistoryPayload:
    match_hash = str(match_id_hash or "").strip().lower()
    if not MATCH_HASH_RE.fullmatch(match_hash):
        raise LearningArchiveInvalidHash("match_id_hash must be exactly 12 hexadecimal characters")

    if client is None:
        from services.supabase_client import get_supabase_client
        client = get_supabase_client()
    if not client or not getattr(client, "is_available", False):
        raise LearningArchiveSourceUnavailable("SmartXFlow database is unavailable")

    http = client._get_http_client()
    headers = client._headers()
    fixture_url = (
        f"{client._rest_url('fixtures')}"
        f"?select=match_id_hash,home_team,away_team,league,kickoff_utc,fixture_date"
        f"&match_id_hash=eq.{match_hash}&limit=1"
    )
    response = http.get(fixture_url, headers=headers, timeout=15)
    if response.status_code != 200:
        raise LearningArchiveSourceUnavailable(f"fixture read failed ({response.status_code})")
    try:
        fixtures = response.json()
    except Exception as exc:
        raise LearningArchiveSourceUnavailable("fixture read returned invalid JSON") from exc
    if not isinstance(fixtures, list) or not fixtures:
        raise LearningArchiveMatchNotFound(match_hash)
    fixture = fixtures[0]
    if not isinstance(fixture, dict):
        raise LearningArchiveSourceUnavailable("fixture read returned invalid payload")

    histories: dict[str, list[dict[str, Any]]] = {}
    source_tables: list[str] = []

    for table in REQUIRED_HISTORY_TABLES:
        rows = _fetch_history_table(client, table, match_hash)
        histories[table] = rows
        if rows:
            source_tables.append(table)

    # Some SmartXFlow fixtures have full timestamped money history in moneyway_snapshots
    # even when the legacy per-market *_history tables contain no rows. Treat that table as
    # a canonical stored-history fallback so a valid Stage 3 case cannot be silently skipped
    # solely because of storage layout.
    if not source_tables:
        snapshot_rows = _fetch_history_table(client, FALLBACK_HISTORY_TABLE, match_hash)
        histories[FALLBACK_HISTORY_TABLE] = snapshot_rows
        if snapshot_rows:
            source_tables.append(FALLBACK_HISTORY_TABLE)

    if not source_tables:
        raise LearningArchiveMatchNotFound(match_hash)

    match = {
        "match_id_hash": match_hash,
        "home": fixture.get("home_team") or "",
        "away": fixture.get("away_team") or "",
        "league": fixture.get("league") or "",
        "kickoff_utc": fixture.get("kickoff_utc") or "",
        "fixture_date": fixture.get("fixture_date") or "",
    }
    return LearningArchiveHistoryPayload(
        match_id_hash=match_hash,
        match=match,
        histories=histories,
        source_tables=tuple(source_tables),
        unavailable_optional_tables=(),
    )
