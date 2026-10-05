from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Iterable


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


def _normalize_hashes(match_id_hashes: Iterable[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in match_id_hashes:
        match_hash = str(value or "").strip().lower()
        if not MATCH_HASH_RE.fullmatch(match_hash):
            raise LearningArchiveInvalidHash("match_id_hash must be exactly 12 hexadecimal characters")
        if match_hash not in seen:
            result.append(match_hash)
            seen.add(match_hash)
    return result


def _client(client: Any | None) -> Any:
    if client is None:
        from services.supabase_client import get_supabase_client
        client = get_supabase_client()
    if not client or not getattr(client, "is_available", False):
        raise LearningArchiveSourceUnavailable("SmartXFlow database is unavailable")
    return client


def _fetch_history_table_many(
    client: Any,
    table: str,
    match_hashes: list[str],
    page_size: int = 1000,
) -> dict[str, list[dict[str, Any]]]:
    grouped = {match_hash: [] for match_hash in match_hashes}
    if not match_hashes:
        return grouped

    offset = 0
    http = client._get_http_client()
    headers = client._headers()
    order_field = "scraped_at_utc" if table == FALLBACK_HISTORY_TABLE else "scraped_at"
    filter_value = ",".join(match_hashes)
    requested = set(match_hashes)
    while True:
        url = (
            f"{client._rest_url(table)}?select=*&match_id_hash=in.({filter_value})"
            f"&order=match_id_hash.asc,{order_field}.asc&limit={page_size}&offset={offset}"
        )
        response = http.get(url, headers=headers, timeout=20)
        if response.status_code != 200:
            raise LearningArchiveSourceUnavailable(
                f"history table batch read failed: {table} ({response.status_code})"
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
            row_hash = str(safe.get("match_id_hash") or "").strip().lower()
            if row_hash not in requested:
                raise LearningArchiveSourceUnavailable(f"history row identity mismatch in table: {table}")
            grouped[row_hash].append(safe)
        if len(page) < page_size:
            break
        offset += page_size
    return grouped


def _fetch_history_table(client: Any, table: str, match_hash: str, page_size: int = 1000) -> list[dict[str, Any]]:
    return _fetch_history_table_many(client, table, [match_hash], page_size=page_size)[match_hash]


def read_learning_archive_match_histories(
    match_id_hashes: Iterable[str],
    *,
    client: Any | None = None,
) -> dict[str, LearningArchiveHistoryPayload]:
    """Read many selected-match histories with one fixture query and one query per table.

    Hashes with no surviving fixture/history are omitted from the mapping so the
    caller can select the durable archive-capture fallback without first raising
    a per-case source error. Transport/schema failures still fail closed.
    """
    hashes = _normalize_hashes(match_id_hashes)
    if not hashes:
        return {}
    client = _client(client)

    http = client._get_http_client()
    headers = client._headers()
    filter_value = ",".join(hashes)
    fixture_url = (
        f"{client._rest_url('fixtures')}"
        f"?select=match_id_hash,home_team,away_team,league,kickoff_utc,fixture_date"
        f"&match_id_hash=in.({filter_value})&limit={max(1, len(hashes) * 2)}"
    )
    response = http.get(fixture_url, headers=headers, timeout=15)
    if response.status_code != 200:
        raise LearningArchiveSourceUnavailable(f"fixture batch read failed ({response.status_code})")
    try:
        fixtures_payload = response.json()
    except Exception as exc:
        raise LearningArchiveSourceUnavailable("fixture batch read returned invalid JSON") from exc
    if not isinstance(fixtures_payload, list):
        raise LearningArchiveSourceUnavailable("fixture batch read returned invalid payload")

    fixtures: dict[str, dict[str, Any]] = {}
    requested = set(hashes)
    for fixture in fixtures_payload:
        if not isinstance(fixture, dict):
            raise LearningArchiveSourceUnavailable("fixture batch read returned invalid row")
        row_hash = str(fixture.get("match_id_hash") or "").strip().lower()
        if row_hash not in requested:
            raise LearningArchiveSourceUnavailable("fixture batch read returned unexpected match identity")
        if row_hash in fixtures:
            raise LearningArchiveSourceUnavailable(f"fixture batch read returned duplicate rows for {row_hash}")
        fixtures[row_hash] = fixture

    present_hashes = [match_hash for match_hash in hashes if match_hash in fixtures]
    histories_by_hash: dict[str, dict[str, list[dict[str, Any]]]] = {
        match_hash: {} for match_hash in present_hashes
    }
    source_tables_by_hash: dict[str, list[str]] = {match_hash: [] for match_hash in present_hashes}

    for table in REQUIRED_HISTORY_TABLES:
        grouped = _fetch_history_table_many(client, table, present_hashes)
        for match_hash in present_hashes:
            rows = grouped[match_hash]
            histories_by_hash[match_hash][table] = rows
            if rows:
                source_tables_by_hash[match_hash].append(table)

    fallback_hashes = [
        match_hash for match_hash in present_hashes if not source_tables_by_hash[match_hash]
    ]
    if fallback_hashes:
        grouped = _fetch_history_table_many(client, FALLBACK_HISTORY_TABLE, fallback_hashes)
        for match_hash in fallback_hashes:
            rows = grouped[match_hash]
            histories_by_hash[match_hash][FALLBACK_HISTORY_TABLE] = rows
            if rows:
                source_tables_by_hash[match_hash].append(FALLBACK_HISTORY_TABLE)

    result: dict[str, LearningArchiveHistoryPayload] = {}
    for match_hash in present_hashes:
        source_tables = source_tables_by_hash[match_hash]
        if not source_tables:
            continue
        fixture = fixtures[match_hash]
        result[match_hash] = LearningArchiveHistoryPayload(
            match_id_hash=match_hash,
            match={
                "match_id_hash": match_hash,
                "home": fixture.get("home_team") or "",
                "away": fixture.get("away_team") or "",
                "league": fixture.get("league") or "",
                "kickoff_utc": fixture.get("kickoff_utc") or "",
                "fixture_date": fixture.get("fixture_date") or "",
            },
            histories=histories_by_hash[match_hash],
            source_tables=tuple(source_tables),
            unavailable_optional_tables=(),
        )
    return result


def read_learning_archive_match_history(
    match_id_hash: str,
    *,
    client: Any | None = None,
) -> LearningArchiveHistoryPayload:
    match_hash = str(match_id_hash or "").strip().lower()
    payloads = read_learning_archive_match_histories([match_hash], client=client)
    payload = payloads.get(match_hash)
    if payload is None:
        raise LearningArchiveMatchNotFound(match_hash)
    return payload
