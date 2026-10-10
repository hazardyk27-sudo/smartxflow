"""Tracked-bettor lifecycle/profile V4.

``tracked_wallet_bets`` is the durable canonical bettor history. Raw execution
rows are only revisited for assets touched since the previous successful sync.
Interactive profile reads never fall back to scanning the raw ledger.

This removes three large-wallet failure modes:
- profile latency scaling with 10k+ position/raw rows,
- open-position detail disappearing behind a partial raw fallback,
- resolved markets staying ``unknown``/``open`` because the old stats path
  sampled only the first 10k activity rows and a small positions subset.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta, timezone
from typing import Any, Dict, Iterable, List, Optional, Sequence, Tuple


PROFILE_BET_SELECT = (
    "bet_key,asset,condition_id,event_id,match_key,match_name,home,away,slug,"
    "kickoff_utc,title,market_type,market_label,selection,side,outcome_raw,"
    "selection_label,side_label,bet_label,lifecycle_status,result,status_label,"
    "stake_usdc,sell_proceeds_usdc,redeem_proceeds_usdc,avg_entry_price,"
    "avg_entry_decimal,pnl_usdc,pnl_kind,fill_count,buy_fill_count,sell_fill_count,"
    "first_traded_at,last_traded_at,latest_market_price,latest_market_decimal,"
    "latest_market_at,closing_price,closing_decimal,closing_observed_at,"
    "clv_probability_pp,clv_pct,sport_classification,sport_verified_at,"
    "sport_classification_source"
)
POSITION_SELECT = (
    "condition_id,asset,event_id,title,slug,outcome,size,avg_price,cur_price,"
    "initial_value,current_value,cash_pnl,percent_pnl,redeemable,end_date"
)
RAW_ACTIVITY_SELECT = (
    "wallet,transaction_hash,asset,condition_id,event_id,result,title,slug,"
    "market_type,selection,side,action,outcome_raw,amount_usdc,price,size,traded_at"
)
RAW_REDEEM_SELECT = (
    "wallet,transaction_hash,condition_id,asset,event_id,title,slug,amount_usdc,traded_at"
)


def _client():
    from . import polymarket_client as client
    return client


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _parse_dt(value: Any) -> Optional[datetime]:
    if not value:
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return dt if dt.tzinfo else dt.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _chunks(values: Sequence[str], size: int = 20) -> Iterable[List[str]]:
    for offset in range(0, len(values), size):
        yield list(values[offset:offset + size])


def _dedup_rows(rows: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    deduped: Dict[Tuple[Any, ...], Dict[str, Any]] = {}
    for row in rows:
        key = (
            row.get("transaction_hash") or row.get("transactionHash"),
            row.get("asset"),
            row.get("condition_id") or row.get("conditionId"),
            row.get("side"),
            row.get("action"),
            row.get("traded_at") or row.get("timestamp"),
        )
        deduped[key] = row
    return list(deduped.values())


def _fetch_pages(
    client,
    base: str,
    headers: Dict[str, str],
    table: str,
    *,
    select_fields: str,
    wallet: str,
    extra_params: Optional[Dict[str, Any]] = None,
    order: Optional[str] = None,
    page_size: int = 1000,
    max_pages: int = 500,
    timeout: int = 12,
) -> Tuple[List[Dict[str, Any]], bool]:
    rows: List[Dict[str, Any]] = []
    for page in range(max_pages):
        params: Dict[str, Any] = {
            "select": select_fields,
            "wallet": f"eq.{wallet.lower()}",
            "limit": page_size,
            "offset": page * page_size,
        }
        if extra_params:
            params.update(extra_params)
        if order:
            params["order"] = order

        response = None
        for _attempt in range(2):
            try:
                response = client.requests.get(
                    f"{base}/rest/v1/{table}",
                    headers=headers,
                    params=params,
                    timeout=timeout,
                )
            except Exception:
                response = None
            if response is not None and response.status_code == 200:
                break
        if response is None or response.status_code != 200:
            client.logger.warning(
                "[PolyLifecycleV4] %s page %s failed for %s",
                table,
                page,
                wallet[:10],
            )
            return rows, False

        page_rows = response.json()
        if not isinstance(page_rows, list):
            return rows, False
        rows.extend(page_rows)
        if len(page_rows) < page_size:
            return rows, True

    client.logger.warning(
        "[PolyLifecycleV4] %s pagination cap reached for %s (%s rows)",
        table,
        wallet[:10],
        len(rows),
    )
    return rows, False


def _fetch_wallet_row(client, base: str, headers: Dict[str, str], wallet: str):
    try:
        response = client.requests.get(
            f"{base}/rest/v1/tracked_wallets",
            headers=headers,
            params={
                "select": (
                    "wallet,nickname,notes,created_at,last_synced_at,win_rate,"
                    "resolved_won,resolved_lost,resolved_total,trade_count,"
                    "total_invested_usdc,avg_bet_size_usdc,avg_price,"
                    "avg_price_decimal,open_position_count,open_exposure_usdc"
                ),
                "wallet": f"eq.{wallet.lower()}",
                "limit": 1,
            },
            timeout=10,
        )
        if response.status_code != 200:
            return None
        rows = response.json()
        return rows[0] if isinstance(rows, list) and rows else None
    except Exception:
        return None


def _fetch_normalized_bets(client, base, headers, wallet):
    return _fetch_pages(
        client,
        base,
        headers,
        "tracked_wallet_bets",
        select_fields=PROFILE_BET_SELECT,
        wallet=wallet,
        order="last_traded_at.desc.nullslast",
    )


def _fetch_by_values(
    client,
    base: str,
    headers: Dict[str, str],
    table: str,
    wallet: str,
    select_fields: str,
    field: str,
    values: Iterable[Any],
    *,
    order: Optional[str] = None,
):
    clean = sorted({str(value) for value in values if value not in (None, "")})
    if not clean:
        return [], True
    all_rows: List[Dict[str, Any]] = []
    for chunk in _chunks(clean, 20):
        rows, ok = _fetch_pages(
            client,
            base,
            headers,
            table,
            select_fields=select_fields,
            wallet=wallet,
            extra_params={field: f"in.({','.join(chunk)})"},
            order=order,
            max_pages=100,
        )
        all_rows.extend(rows)
        if not ok:
            return _dedup_rows(all_rows), False
    return _dedup_rows(all_rows), True


def _fetch_positions_for_assets(client, base, headers, wallet, assets):
    return _fetch_by_values(
        client,
        base,
        headers,
        "tracked_wallet_positions",
        wallet,
        POSITION_SELECT,
        "asset",
        assets,
        order="current_value.desc",
    )


def _recent_floor(wallet_row: Dict[str, Any]) -> Optional[str]:
    source = wallet_row.get("last_synced_at") or wallet_row.get("created_at")
    dt = _parse_dt(source)
    if dt is None:
        return None
    return (dt - timedelta(hours=2)).astimezone(timezone.utc).isoformat()


def _refresh_touched_normalized(client, base, headers, wallet, wallet_row) -> bool:
    """Rebuild only canonical assets touched since the previous good sync."""
    since = _recent_floor(wallet_row)
    extra = {"traded_at": f"gte.{since}"} if since else {}

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_activity = pool.submit(
            _fetch_pages,
            client,
            base,
            headers,
            "tracked_wallet_activity",
            select_fields=RAW_ACTIVITY_SELECT,
            wallet=wallet,
            extra_params=extra,
            order="traded_at.asc",
            max_pages=200,
        )
        f_redeems = pool.submit(
            _fetch_pages,
            client,
            base,
            headers,
            "tracked_wallet_redeems",
            select_fields=RAW_REDEEM_SELECT,
            wallet=wallet,
            extra_params=extra,
            order="traded_at.asc",
            max_pages=200,
        )
        recent_activity, activity_ok = f_activity.result()
        recent_redeems, redeems_ok = f_redeems.result()

    if not (activity_ok and redeems_ok):
        return False

    touched = recent_activity + recent_redeems
    assets = {row.get("asset") for row in touched if row.get("asset")}
    conditions = {
        row.get("condition_id") or row.get("conditionId")
        for row in touched
        if row.get("condition_id") or row.get("conditionId")
    }
    if not assets and not conditions:
        return True

    activity_groups: List[Dict[str, Any]] = []
    redeem_groups: List[Dict[str, Any]] = []

    for field, values in (("asset", assets), ("condition_id", conditions)):
        if not values:
            continue
        rows, ok = _fetch_by_values(
            client,
            base,
            headers,
            "tracked_wallet_activity",
            wallet,
            RAW_ACTIVITY_SELECT,
            field,
            values,
            order="traded_at.asc",
        )
        if not ok:
            return False
        activity_groups.extend(rows)

        rows, ok = _fetch_by_values(
            client,
            base,
            headers,
            "tracked_wallet_redeems",
            wallet,
            RAW_REDEEM_SELECT,
            field,
            values,
            order="traded_at.asc",
        )
        if not ok:
            return False
        redeem_groups.extend(rows)

    full_activity = _dedup_rows(activity_groups)
    full_redeems = _dedup_rows(redeem_groups)
    tracked_since = wallet_row.get("created_at")
    full_activity = client._filter_wallet_rows_since(full_activity, tracked_since)
    full_activity = client._filter_tracked_wallet_activity_amount(full_activity)
    full_redeems = client._filter_wallet_rows_since(full_redeems, tracked_since)
    full_redeems = client._filter_wallet_redeems_to_activity(
        full_redeems,
        full_activity,
    )

    qualifying_assets = {row.get("asset") for row in full_activity if row.get("asset")}
    positions, positions_ok = _fetch_positions_for_assets(
        client,
        base,
        headers,
        wallet,
        qualifying_assets,
    )
    if not positions_ok:
        return False
    positions = client._filter_positions_since_tracking(positions, full_activity)

    resolved = client._compute_resolved_stats(positions, full_redeems)
    lifecycle = client._build_display_activity(
        full_activity,
        positions,
        resolved["resolved_won_ids"],
        resolved["resolved_lost_ids"],
        full_redeems,
    )
    if not lifecycle:
        return True
    return bool(client._persist_wallet_bet_rows(base, headers, wallet, lifecycle))


def _resolution_priority(row: Dict[str, Any]):
    result = str(row.get("result") or "").lower()
    status = str(row.get("lifecycle_status") or "").lower()
    kickoff = _parse_dt(row.get("kickoff_utc"))
    past = kickoff is not None and kickoff <= datetime.now(timezone.utc)
    if result == "unknown" and past:
        rank = 0
    elif status == "open" and past:
        rank = 1
    elif result == "unknown":
        rank = 2
    else:
        rank = 3
    return rank, str(row.get("kickoff_utc") or row.get("last_traded_at") or "")


def _reconcile_rows(
    client,
    base: str,
    headers: Dict[str, str],
    wallet: str,
    rows: List[Dict[str, Any]],
    *,
    max_condition_ids: Optional[int] = 60,
    apply: bool = True,
):
    candidates = [
        row for row in rows
        if str(row.get("result") or "").lower() not in {"won", "lost"}
        and row.get("condition_id")
        and row.get("asset")
    ]
    candidates.sort(key=_resolution_priority)

    condition_ids: List[str] = []
    seen = set()
    for row in candidates:
        cid = str(row.get("condition_id"))
        if cid in seen:
            continue
        seen.add(cid)
        condition_ids.append(cid)
        if max_condition_ids and len(condition_ids) >= max_condition_ids:
            break

    resolutions: Dict[str, Optional[Dict[str, bool]]] = {}
    if condition_ids:
        with ThreadPoolExecutor(max_workers=min(20, len(condition_ids))) as pool:
            futures = {
                pool.submit(client._fetch_market_resolution, cid): cid
                for cid in condition_ids
            }
            for future in as_completed(futures):
                cid = futures[future]
                try:
                    resolutions[cid] = future.result()
                except Exception:
                    resolutions[cid] = None

    selected = set(condition_ids)
    changed: List[Dict[str, Any]] = []
    for row in rows:
        cid = str(row.get("condition_id") or "")
        if cid not in selected:
            continue
        resolution = resolutions.get(cid)
        asset = str(row.get("asset") or "")
        if not resolution or asset not in resolution:
            continue
        winner = bool(resolution[asset])
        result = "won" if winner else "lost"
        if row.get("result") == result and row.get("lifecycle_status") == "resolved":
            continue
        row["result"] = result
        row["lifecycle_status"] = "resolved"
        row["status_label"] = "Kazandı" if winner else "Kaybetti"
        changed.append(row)

    persisted = True
    if apply and changed:
        persisted = bool(
            client._persist_wallet_bet_rows(base, headers, wallet, changed)
        )
    return {
        "checked_conditions": len(condition_ids),
        "resolved_rows": len(changed),
        "persisted": persisted,
        "rows": rows,
    }


def reconcile_persisted_wallet_bet_resolutions(
    wallet: str,
    *,
    max_condition_ids: Optional[int] = None,
    apply: bool = False,
):
    client = _client()
    base = client._supabase_base_url()
    if not base or not wallet:
        return {"wallet": wallet, "checked_conditions": 0, "resolved_rows": 0, "persisted": False}
    wallet = wallet.lower()
    headers = client._supabase_headers()
    rows, ok = _fetch_normalized_bets(client, base, headers, wallet)
    if not ok:
        return {"wallet": wallet, "checked_conditions": 0, "resolved_rows": 0, "persisted": False}
    result = _reconcile_rows(
        client,
        base,
        headers,
        wallet,
        rows,
        max_condition_ids=max_condition_ids,
        apply=apply,
    )
    return {
        "wallet": wallet,
        "checked_conditions": result["checked_conditions"],
        "resolved_rows": result["resolved_rows"],
        "persisted": result["persisted"],
    }


def _position_map(rows):
    return {
        str(row.get("asset")): row
        for row in rows
        if row.get("asset") not in (None, "")
    }


def _normalized_stats(client, bet_rows, position_rows, wallet_row=None):
    qualifying = [
        row for row in bet_rows
        if _as_float(row.get("stake_usdc")) >= client.MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC
    ]
    won = sum(str(row.get("result") or "").lower() == "won" for row in qualifying)
    lost = sum(str(row.get("result") or "").lower() == "lost" for row in qualifying)
    resolved_total = won + lost
    open_bets = [
        row for row in qualifying
        if str(row.get("lifecycle_status") or "").lower() == "open"
        and str(row.get("result") or "").lower() not in {"won", "lost"}
    ]
    total_invested = sum(_as_float(row.get("stake_usdc")) for row in qualifying)
    weighted_entry = sum(
        _as_float(row.get("avg_entry_price")) * _as_float(row.get("stake_usdc"))
        for row in qualifying
    )
    avg_entry = weighted_entry / total_invested if total_invested else 0.0

    positions = _position_map(position_rows)
    open_exposure = 0.0
    found_positions = 0
    for bet in open_bets:
        position = positions.get(str(bet.get("asset") or ""))
        if position is None:
            continue
        found_positions += 1
        open_exposure += _as_float(position.get("current_value"))

    previous_open_count = int((wallet_row or {}).get("open_position_count") or 0)
    previous_exposure = _as_float((wallet_row or {}).get("open_exposure_usdc"))
    if found_positions < len(open_bets) and previous_open_count == len(open_bets):
        open_exposure = previous_exposure

    realized_pnl = sum(
        _as_float(row.get("pnl_usdc"))
        for row in qualifying
        if row.get("pnl_kind") == "realized"
    )
    total_redeemed = sum(_as_float(row.get("redeem_proceeds_usdc")) for row in qualifying)

    return {
        "bet_count": len(qualifying),
        "trade_count": len(qualifying),
        "total_invested_usdc": round(total_invested, 2),
        "avg_bet_size_usdc": round(total_invested / len(qualifying), 2) if qualifying else 0.0,
        "avg_entry_probability": round(avg_entry, 6) if avg_entry else 0.0,
        "avg_entry_decimal": client._to_decimal_odds(avg_entry) if avg_entry else None,
        "avg_price": round(avg_entry, 6) if avg_entry else 0.0,
        "avg_price_decimal": client._to_decimal_odds(avg_entry) if avg_entry else None,
        "win_rate_pct": round((won / resolved_total) * 100, 1) if resolved_total else None,
        "resolved_won": won,
        "resolved_lost": lost,
        "resolved_total": resolved_total,
        "open_position_count": len(open_bets),
        "open_exposure_usdc": round(open_exposure, 2),
        "realized_pnl_usdc": round(realized_pnl, 2),
        "total_redeemed_usdc": round(total_redeemed, 2),
    }


def _open_position_rows(client, bet_rows, stored_positions):
    positions = _position_map(stored_positions)
    open_rows = []
    for bet in bet_rows:
        if str(bet.get("lifecycle_status") or "").lower() != "open":
            continue
        if str(bet.get("result") or "").lower() in {"won", "lost"}:
            continue
        asset = str(bet.get("asset") or "")
        position = dict(positions.get(asset) or {})
        for key in (
            "condition_id", "asset", "event_id", "title", "slug", "match_name",
            "market_type", "market_label", "selection", "selection_label",
            "side_label", "bet_label",
        ):
            if bet.get(key) not in (None, ""):
                position[key] = bet.get(key)
        if "avg_price" not in position:
            position["avg_price"] = bet.get("avg_entry_price")
        if "cur_price" not in position:
            position["cur_price"] = bet.get("latest_market_price")
        position["snapshot_missing"] = asset not in positions
        open_rows.append(client._with_wallet_bet_display_metadata(position))
    return open_rows


def get_wallet_profile_v4(wallet: str):
    client = _client()
    base = client._supabase_base_url()
    if not base or not wallet:
        return None
    wallet = wallet.lower()
    headers = client._supabase_headers()

    with ThreadPoolExecutor(max_workers=2) as pool:
        f_wallet = pool.submit(_fetch_wallet_row, client, base, headers, wallet)
        f_bets = pool.submit(_fetch_normalized_bets, client, base, headers, wallet)
        wallet_row = f_wallet.result()
        bet_rows, bets_ok = f_bets.result()
    if wallet_row is None:
        return None

    open_assets = {
        row.get("asset") for row in bet_rows
        if str(row.get("lifecycle_status") or "").lower() == "open" and row.get("asset")
    }
    positions, positions_ok = _fetch_positions_for_assets(
        client, base, headers, wallet, open_assets
    )
    if not positions_ok:
        positions = []

    stats = _normalized_stats(client, bet_rows, positions, wallet_row)
    display_activity = [client._persisted_wallet_bet_to_display(row) for row in bet_rows]
    canonical_bets = [client._wallet_bet_api_contract(row) for row in display_activity]
    open_positions = _open_position_rows(client, bet_rows, positions)

    expected = max(int(wallet_row.get("trade_count") or 0), len(canonical_bets))
    coverage = {
        "history_source": "tracked_wallet_bets",
        "history_complete": bool(bets_ok and len(canonical_bets) >= expected),
        "expected_bet_count": expected,
        "returned_bet_count": len(canonical_bets),
        "football_only": False,
        "sport_filtering": "disabled",
        "sport_classification_role": "metadata_only",
        "minimum_position_entry_usdc": client.MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC,
        "canonical_identity": "asset_first",
        "canonical_history_retention": client.TRACKED_WALLET_CANONICAL_RETENTION,
        "raw_activity_retention_days": client.TRACKED_WALLET_RAW_RETENTION_DAYS,
        "closing_line_source": client.TRACKED_WALLET_CLOSING_LINE_SOURCE,
    }
    quality = client._validate_wallet_profile_contract(stats, canonical_bets, coverage)

    summary = []
    if stats["bet_count"]:
        summary.append(
            f"{stats['bet_count']} canonical bahis, toplam "
            f"{stats['total_invested_usdc']:,.0f} USDC yatırım.".replace(",", ".")
        )
    else:
        summary.append("Henüz kayıtlı canonical bahsi bulunmuyor.")
    if stats["resolved_total"] and stats["win_rate_pct"] is not None:
        summary.append(
            f"Sonuçlanan {stats['resolved_total']} bahisin "
            f"%{stats['win_rate_pct']}'ini kazandı."
        )
    if stats["open_position_count"]:
        summary.append(
            f"Şu an {stats['open_position_count']} açık pozisyonu var, toplam "
            f"{stats['open_exposure_usdc']:,.0f} USDC açık değer.".replace(",", ".")
        )

    return {
        "contract_version": "2026-10-10.v4-normalized-fast",
        "wallet": wallet_row.get("wallet"),
        "nickname": wallet_row.get("nickname"),
        "notes": wallet_row.get("notes"),
        "tracked_since": wallet_row.get("created_at"),
        "last_synced_at": wallet_row.get("last_synced_at"),
        "stats_status": "ready" if wallet_row.get("last_synced_at") else "pending",
        "coverage": coverage,
        "quality": quality,
        "stats": stats,
        "summary": summary,
        "bets": canonical_bets,
        "activity": display_activity,
        "open_positions": open_positions,
    }


def _patch_wallet_stats(client, base, headers, wallet, stats) -> bool:
    payload = {
        "win_rate": stats["win_rate_pct"],
        "resolved_won": stats["resolved_won"],
        "resolved_lost": stats["resolved_lost"],
        "resolved_total": stats["resolved_total"],
        "trade_count": stats["trade_count"],
        "total_invested_usdc": stats["total_invested_usdc"],
        "avg_bet_size_usdc": stats["avg_bet_size_usdc"],
        "avg_price": stats["avg_price"],
        "avg_price_decimal": stats["avg_price_decimal"],
        "open_position_count": stats["open_position_count"],
        "open_exposure_usdc": stats["open_exposure_usdc"],
        "last_synced_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        response = client.requests.patch(
            f"{base}/rest/v1/tracked_wallets",
            headers={**headers, "Content-Type": "application/json"},
            params={"wallet": f"eq.{wallet.lower()}"},
            json=payload,
            timeout=15,
        )
        return response.status_code in (200, 204)
    except Exception:
        return False


def compute_and_save_wallet_stats_v4(
    wallet: str,
    allow_verified_sport_rebase: bool = False,
) -> bool:
    del allow_verified_sport_rebase
    client = _client()
    base = client._supabase_base_url()
    if not base or not wallet:
        return False
    wallet = wallet.lower()
    headers = client._supabase_headers()
    wallet_row = _fetch_wallet_row(client, base, headers, wallet)
    if wallet_row is None:
        return False

    # Do not advance last_synced_at when incremental normalized persistence
    # failed; the next cycle must retry from the previous successful floor.
    if not _refresh_touched_normalized(client, base, headers, wallet, wallet_row):
        return False

    bet_rows, bets_ok = _fetch_normalized_bets(client, base, headers, wallet)
    if not bets_ok:
        return False

    reconciliation = _reconcile_rows(
        client,
        base,
        headers,
        wallet,
        bet_rows,
        max_condition_ids=60,
        apply=True,
    )
    if not reconciliation["persisted"]:
        return False

    open_assets = {
        row.get("asset") for row in bet_rows
        if str(row.get("lifecycle_status") or "").lower() == "open"
        and str(row.get("result") or "").lower() not in {"won", "lost"}
        and row.get("asset")
    }
    positions, positions_ok = _fetch_positions_for_assets(
        client, base, headers, wallet, open_assets
    )
    if not positions_ok:
        positions = []

    stats = _normalized_stats(client, bet_rows, positions, wallet_row)
    return _patch_wallet_stats(client, base, headers, wallet, stats)


def bind_polymarket_lifecycle_v4_patch() -> None:
    client = _client()
    if getattr(client, "_sxf_lifecycle_v4_bound", False):
        return
    client.get_wallet_profile = get_wallet_profile_v4
    client.compute_and_save_wallet_stats = compute_and_save_wallet_stats_v4
    client.reconcile_persisted_wallet_bet_resolutions = reconcile_persisted_wallet_bet_resolutions
    client.TRACKED_WALLET_API_CONTRACT_VERSION = "2026-10-10.v4-normalized-fast"
    client._sxf_lifecycle_v4_bound = True
