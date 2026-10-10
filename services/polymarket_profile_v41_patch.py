"""Fast tracked-bettor profile reader for large durable ledgers.

The V4 lifecycle remains canonical for persistence and statistics. This reader
only changes the interactive profile shape:
- summary stats come from the already-persisted tracked_wallets snapshot,
- the initial history window is bounded to the latest 250 canonical bets,
- open canonical bets are fetched separately so they never disappear merely
  because they are older than the visible history window,
- the legacy duplicate ``activity`` array is not returned.

The complete canonical history remains durable in ``tracked_wallet_bets`` and
lifecycle reconciliation still runs against the full ledger outside the profile
request path.
"""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Dict, List, Tuple

from . import polymarket_lifecycle_v4_patch as v4


PROFILE_HISTORY_LIMIT = 250
PROFILE_HISTORY_MAX_LIMIT = 500


def _client():
    from . import polymarket_client as client
    return client


def _fetch_history_page(
    client,
    base: str,
    headers: Dict[str, str],
    wallet: str,
    *,
    limit: int = PROFILE_HISTORY_LIMIT,
    offset: int = 0,
) -> Tuple[List[Dict[str, Any]], bool]:
    limit = max(1, min(int(limit or PROFILE_HISTORY_LIMIT), PROFILE_HISTORY_MAX_LIMIT))
    offset = max(0, int(offset or 0))
    try:
        response = client.requests.get(
            f"{base}/rest/v1/tracked_wallet_bets",
            headers=headers,
            params={
                "select": v4.PROFILE_BET_SELECT,
                "wallet": f"eq.{wallet.lower()}",
                "order": "last_traded_at.desc.nullslast",
                "limit": limit,
                "offset": offset,
            },
            timeout=10,
        )
        if response.status_code != 200:
            return [], False
        rows = response.json()
        return (rows if isinstance(rows, list) else []), isinstance(rows, list)
    except Exception:
        return [], False


def _fetch_open_bets(client, base, headers, wallet):
    rows, ok = v4._fetch_pages(
        client,
        base,
        headers,
        "tracked_wallet_bets",
        select_fields=v4.PROFILE_BET_SELECT,
        wallet=wallet,
        extra_params={"lifecycle_status": "eq.open"},
        order="last_traded_at.desc.nullslast",
        page_size=500,
        max_pages=20,
        timeout=10,
    )
    if not ok:
        return rows, False
    rows = [
        row for row in rows
        if str(row.get("result") or "").lower() not in {"won", "lost"}
    ]
    return rows, True


def _stats_from_wallet_row(client, row: Dict[str, Any]) -> Dict[str, Any]:
    total = int(row.get("trade_count") or 0)
    invested = v4._as_float(row.get("total_invested_usdc"))
    avg_price = v4._as_float(row.get("avg_price"))
    avg_decimal = row.get("avg_price_decimal")
    if avg_decimal in (None, "") and avg_price:
        avg_decimal = client._to_decimal_odds(avg_price)
    return {
        "bet_count": total,
        "trade_count": total,
        "total_invested_usdc": round(invested, 2),
        "avg_bet_size_usdc": round(v4._as_float(row.get("avg_bet_size_usdc")), 2),
        "avg_entry_probability": round(avg_price, 6) if avg_price else 0.0,
        "avg_entry_decimal": avg_decimal,
        "avg_price": round(avg_price, 6) if avg_price else 0.0,
        "avg_price_decimal": avg_decimal,
        "win_rate_pct": row.get("win_rate"),
        "resolved_won": int(row.get("resolved_won") or 0),
        "resolved_lost": int(row.get("resolved_lost") or 0),
        "resolved_total": int(row.get("resolved_total") or 0),
        "open_position_count": int(row.get("open_position_count") or 0),
        "open_exposure_usdc": round(v4._as_float(row.get("open_exposure_usdc")), 2),
        # Bet-level realized P&L is still present in the returned recent window;
        # these aggregate compatibility fields intentionally avoid a full-ledger
        # scan inside an interactive GET.
        "realized_pnl_usdc": 0.0,
        "total_redeemed_usdc": 0.0,
    }


def get_wallet_profile_v41(wallet: str):
    client = _client()
    base = client._supabase_base_url()
    if not base or not wallet:
        return None
    wallet = wallet.lower()
    headers = client._supabase_headers()

    with ThreadPoolExecutor(max_workers=3) as pool:
        f_wallet = pool.submit(v4._fetch_wallet_row, client, base, headers, wallet)
        f_history = pool.submit(
            _fetch_history_page,
            client,
            base,
            headers,
            wallet,
            limit=PROFILE_HISTORY_LIMIT,
            offset=0,
        )
        f_open = pool.submit(_fetch_open_bets, client, base, headers, wallet)
        wallet_row = f_wallet.result()
        history_rows, history_ok = f_history.result()
        open_rows, open_ok = f_open.result()

    if wallet_row is None:
        return None

    open_assets = {
        row.get("asset") for row in open_rows
        if row.get("asset") not in (None, "")
    }
    positions, positions_ok = v4._fetch_positions_for_assets(
        client, base, headers, wallet, open_assets
    )
    if not positions_ok:
        positions = []

    stats = _stats_from_wallet_row(client, wallet_row)
    display_activity = [
        client._persisted_wallet_bet_to_display(row)
        for row in history_rows
    ]
    canonical_bets = [
        client._wallet_bet_api_contract(row)
        for row in display_activity
    ]
    open_positions = v4._open_position_rows(client, open_rows, positions)

    expected = int(wallet_row.get("trade_count") or 0)
    returned = len(canonical_bets)
    coverage = {
        "history_source": "tracked_wallet_bets",
        "history_complete": bool(history_ok and returned >= expected),
        "history_window": "latest",
        "history_window_limit": PROFILE_HISTORY_LIMIT,
        "history_more_available": expected > returned,
        "expected_bet_count": expected,
        "returned_bet_count": returned,
        "football_only": False,
        "sport_filtering": "disabled",
        "sport_classification_role": "metadata_only",
        "minimum_position_entry_usdc": client.MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC,
        "canonical_identity": "asset_first",
        "canonical_history_retention": client.TRACKED_WALLET_CANONICAL_RETENTION,
        "raw_activity_retention_days": client.TRACKED_WALLET_RAW_RETENTION_DAYS,
        "closing_line_source": client.TRACKED_WALLET_CLOSING_LINE_SOURCE,
        "open_history_complete": bool(open_ok),
    }
    quality = client._validate_wallet_profile_contract(stats, canonical_bets, coverage)

    summary: List[str] = []
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
        "contract_version": "2026-10-10.v4.1-bounded-profile",
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
        "open_positions": open_positions,
    }


def bind_polymarket_profile_v41_patch() -> None:
    client = _client()
    if getattr(client, "_sxf_profile_v41_bound", False):
        return
    client.get_wallet_profile = get_wallet_profile_v41
    client.TRACKED_WALLET_API_CONTRACT_VERSION = "2026-10-10.v4.1-bounded-profile"
    client._sxf_profile_v41_bound = True
