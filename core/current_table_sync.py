from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple

import requests

from core.fixture_identity_shadow import flush_staged_betwatch_identity_shadow
from core.fixture_uid_dual_write import PREMATCH_CURRENT_TABLES
from core.fixture_uid_provider_gate import attach_provider_verified_fixture_uids

CURRENT_PAGE_SIZE = 1000
DELETE_BATCH_SIZE = 200
_KEY_FIELDS = ("league", "home", "away", "date")


def _emit(logger, message: str) -> None:
    if logger:
        logger(message)


def _record_error(writer, message: str) -> None:
    errors = getattr(writer, "last_write_errors", None)
    if isinstance(errors, list) and message not in errors:
        errors.append(message)


def _normalize_date(value: Any) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return raw
    if parsed.tzinfo is None:
        return parsed.replace(microsecond=0).isoformat(timespec="seconds")
    return (
        parsed.astimezone(timezone.utc)
        .replace(microsecond=0)
        .isoformat(timespec="seconds")
    )


def _row_key(row: Dict[str, Any]) -> Tuple[str, str, str, str]:
    return (
        str(row.get("league") or "").strip(),
        str(row.get("home") or "").strip(),
        str(row.get("away") or "").strip(),
        _normalize_date(row.get("date")),
    )


def _read_current_index(writer, table: str, logger=None) -> Optional[Dict[Tuple[str, str, str, str], int]]:
    """Read the complete current-table key -> id index with explicit pagination.

    Returning None means the current set could not be proven, so callers must not
    prune anything. This is deliberately fail-closed.
    """
    index: Dict[Tuple[str, str, str, str], int] = {}
    offset = 0

    while True:
        url = (
            f"{writer._rest_url(table)}"
            f"?select=id,league,home,away,date"
            f"&order=id.asc&limit={CURRENT_PAGE_SIZE}&offset={offset}"
        )
        try:
            response = requests.get(url, headers=writer._headers(), timeout=30)
        except requests.RequestException as exc:
            message = f"{table}: current index okunamadı ({exc})"
            _record_error(writer, message)
            _emit(logger, f"[Current Sync] HATA — {message}")
            return None

        if response.status_code != 200:
            message = f"{table}: current index HTTP {response.status_code}"
            _record_error(writer, message)
            _emit(logger, f"[Current Sync] HATA — {message}")
            return None

        try:
            batch = response.json()
        except Exception as exc:
            message = f"{table}: current index JSON okunamadı ({exc})"
            _record_error(writer, message)
            _emit(logger, f"[Current Sync] HATA — {message}")
            return None

        if not isinstance(batch, list):
            message = f"{table}: current index beklenmeyen response"
            _record_error(writer, message)
            _emit(logger, f"[Current Sync] HATA — {message}")
            return None

        for row in batch:
            row_id = row.get("id")
            if row_id is None:
                message = f"{table}: current satır id alanı eksik; prune iptal"
                _record_error(writer, message)
                _emit(logger, f"[Current Sync] HATA — {message}")
                return None
            index[_row_key(row)] = int(row_id)

        if len(batch) < CURRENT_PAGE_SIZE:
            return index
        offset += CURRENT_PAGE_SIZE


def _delete_stale_ids(writer, table: str, stale_ids: Iterable[int], logger=None) -> bool:
    ids = [int(value) for value in stale_ids]
    if not ids:
        return True

    deleted = 0
    for start in range(0, len(ids), DELETE_BATCH_SIZE):
        chunk = ids[start:start + DELETE_BATCH_SIZE]
        id_filter = ",".join(str(value) for value in chunk)
        url = f"{writer._rest_url(table)}?id=in.({id_filter})"
        try:
            response = requests.delete(url, headers=writer._headers(), timeout=45)
        except requests.RequestException as exc:
            message = f"{table}: stale prune bağlantı hatası ({exc})"
            _record_error(writer, message)
            _emit(logger, f"[Current Sync] HATA — {message}")
            return False

        if response.status_code not in (200, 204):
            message = f"{table}: stale prune HTTP {response.status_code}"
            _record_error(writer, message)
            _emit(logger, f"[Current Sync] HATA — {message}")
            return False
        deleted += len(chunk)

    _emit(logger, f"[Current Sync] {table}: {deleted} stale current satır silindi")
    return True


def _upsert_current_rows(writer, table: str, rows: List[Dict[str, Any]]) -> bool:
    """Use the modern writer API when available, with legacy compatibility."""
    upsert_rows = getattr(writer, "upsert_rows", None)
    if callable(upsert_rows):
        return bool(
            upsert_rows(
                table,
                rows,
                on_conflict="league,home,away,date",
            )
        )

    replace_table = getattr(writer, "replace_table", None)
    if callable(replace_table):
        return bool(replace_table(table, rows))

    return False


def _table_supports_fixture_uid(writer, table: str) -> bool:
    cache = getattr(writer, "_fixture_uid_column_support", None)
    if not isinstance(cache, dict):
        cache = {}
        try:
            writer._fixture_uid_column_support = cache
        except Exception:
            pass
    if table in cache:
        return bool(cache[table])
    try:
        response = requests.get(
            writer._rest_url(table),
            headers=writer._headers(),
            params={"select": "fixture_uid", "limit": 0},
            timeout=10,
        )
        supported = response.status_code == 200
    except Exception:
        supported = False
    cache[table] = supported
    return supported


def _attach_fixture_uid_dual_write(writer, table: str, rows: List[Dict[str, Any]], logger=None) -> None:
    """Best-effort provider-gated UID enrichment; legacy writes stay authoritative."""
    if table not in PREMATCH_CURRENT_TABLES or not rows:
        return
    if not _table_supports_fixture_uid(writer, table):
        _emit(logger, f"[FixtureUID] WARN — {table}: fixture_uid_column_unavailable; legacy write devam ediyor")
        return
    try:
        stats = attach_provider_verified_fixture_uids(
            writer,
            rows,
            request_get=requests.get,
        )
        store = getattr(writer, "last_fixture_uid_dual_write_stats", None)
        if not isinstance(store, dict):
            store = {}
            try:
                writer.last_fixture_uid_dual_write_stats = store
            except Exception:
                pass
        store[table] = stats

        if stats.get("error"):
            _emit(
                logger,
                f"[FixtureUID] WARN — {table}: {stats['error']}; legacy write devam ediyor",
            )
            return
        if stats.get("conflicting_existing_uid"):
            _emit(
                logger,
                f"[FixtureUID] WARN — {table}: conflicting_existing_uid="
                f"{stats['conflicting_existing_uid']}; mevcut UID korunuyor",
            )
        if stats.get("identity_mismatch_rows"):
            _emit(
                logger,
                f"[FixtureUID] WARN — {table}: identity_mismatch_rows="
                f"{stats['identity_mismatch_rows']}; UID yazılmadı",
            )
        _emit(
            logger,
            f"[FixtureUID] {table}: tagged={stats['tagged_rows']} "
            f"unresolved={stats['unresolved_rows']} "
            f"provider_context={stats['provider_context_hashes']}",
        )
    except Exception as exc:  # pragma: no cover - final non-authoritative safety net
        _emit(logger, f"[FixtureUID] WARN — {table}: dual-write atlandı: {str(exc)[:200]}")


def _flush_identity_shadow(writer, logger=None) -> None:
    """Consume at most one staged provider batch without affecting current sync."""
    try:
        stats = flush_staged_betwatch_identity_shadow(writer, logger=logger)
        if stats.get("attempted"):
            writer.last_identity_shadow_stats = stats
    except Exception as exc:  # pragma: no cover - final non-authoritative safety net
        _emit(logger, f"[IdentityShadow] WARN — flush atlandı: {str(exc)[:200]}")


def sync_current_table(writer, table: str, rows: List[Dict[str, Any]], logger=None) -> bool:
    """Make a current table exactly represent the latest successful feed set.

    Safety order is intentional:
      1. Flush the staged Identity V2 shadow batch after the scraper's unchanged
         legacy fixture write. The shadow remains observational and fail-soft.
      2. Best-effort add ``fixture_uid`` only when provider registry + exact
         physical fixture metadata agree. The original row objects are enriched
         so the later history append receives the same UID.
      3. Read the full pre-write current index.
      4. UPSERT the new feed set using the unchanged legacy logical key.
      5. Only after a successful UPSERT, delete ids whose logical key is absent
         from the incoming set.

    History/archive tables are never directly written here. An empty incoming set
    is a valid current state and therefore clears the current table, but only after
    a successful index read. If the index cannot be read, new rows may still be
    upserted, while pruning is skipped and the run is marked degraded.
    """
    # In the Betwatch scraper, legacy fixtures are written before the first current
    # table. Flushing here gives the provider-gated dual-write the registry proof it
    # needs while keeping shadow failures fully outside legacy correctness.
    _flush_identity_shadow(writer, logger=logger)
    _attach_fixture_uid_dual_write(writer, table, rows, logger=logger)

    clean_rows: List[Dict[str, Any]] = []
    for row in rows:
        clean = dict(row)
        clean.pop("id", None)
        clean_rows.append(clean)

    existing_index = _read_current_index(writer, table, logger=logger)

    upsert_ok = _upsert_current_rows(writer, table, clean_rows)
    if not upsert_ok:
        message = f"{table}: current UPSERT başarısız; prune iptal"
        _record_error(writer, message)
        _emit(logger, f"[Current Sync] HATA — {message}")
        return False

    if existing_index is None:
        _emit(
            logger,
            f"[Current Sync] {table}: yeni set yazıldı fakat eski set doğrulanamadı; prune atlandı",
        )
        return False

    incoming_keys = {_row_key(row) for row in clean_rows}
    stale_ids = [
        row_id
        for key, row_id in existing_index.items()
        if key not in incoming_keys
    ]

    if not _delete_stale_ids(writer, table, stale_ids, logger=logger):
        return False

    _emit(
        logger,
        f"[Current Sync] {table}: current={len(clean_rows)}, stale={len(stale_ids)}",
    )
    return True
