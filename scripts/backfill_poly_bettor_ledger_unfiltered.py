#!/usr/bin/env python3
"""Backfill tracked_wallet_bets from the durable raw tracked-wallet ledger.

The repair is intentionally sport-neutral: every canonical position that meets
SmartXFlow's existing >= $1,000 total BUY-entry threshold is eligible. Soccer
classification is retained only as metadata and never as a visibility gate.

Default mode is dry-run. Use ``--apply`` only in the canonical SmartXFlow
runtime after the matching source SHA is deployed.
"""
from __future__ import annotations

import argparse
from typing import Any, Dict, List, Optional, Tuple

from services import polymarket_client as pc


PAGE_SIZE = 1000
MAX_PAGES = 500


def _fetch_all(
    base: str,
    headers: Dict[str, str],
    table: str,
    wallet: str,
    select_fields: str,
    *,
    order: Optional[str] = None,
    tracked_since: Optional[str] = None,
) -> Tuple[List[Dict[str, Any]], bool]:
    rows: List[Dict[str, Any]] = []
    for page in range(MAX_PAGES):
        params: Dict[str, Any] = {
            "select": select_fields,
            "wallet": f"eq.{wallet}",
            "limit": PAGE_SIZE,
            "offset": page * PAGE_SIZE,
        }
        if order:
            params["order"] = order
        if tracked_since and table in {"tracked_wallet_activity", "tracked_wallet_redeems"}:
            params["traded_at"] = f"gte.{tracked_since}"
        try:
            response = pc.requests.get(
                f"{base}/rest/v1/{table}",
                headers=headers,
                params=params,
                timeout=30,
            )
        except Exception as exc:
            print(f"[{wallet[:10]}] {table} fetch error: {exc}")
            return rows, False
        if response.status_code != 200:
            print(f"[{wallet[:10]}] {table} HTTP {response.status_code}")
            return rows, False
        page_rows = response.json()
        if not isinstance(page_rows, list):
            return rows, False
        rows.extend(page_rows)
        if len(page_rows) < PAGE_SIZE:
            return rows, True
    print(f"[{wallet[:10]}] {table} safety cap reached ({len(rows)} rows)")
    return rows, False


def _build_wallet_lifecycle(
    wallet_row: Dict[str, Any],
) -> Tuple[List[Dict[str, Any]], Dict[str, int], bool]:
    base = pc._supabase_base_url()
    if not base:
        return [], {}, False
    headers = pc._supabase_headers()
    wallet = str(wallet_row.get("wallet") or "").lower()
    tracked_since = wallet_row.get("created_at")

    activity, activity_ok = _fetch_all(
        base,
        headers,
        "tracked_wallet_activity",
        wallet,
        (
            "wallet,transaction_hash,asset,condition_id,event_id,result,title,slug,"
            "market_type,selection,side,action,outcome_raw,amount_usdc,price,size,traded_at"
        ),
        order="traded_at.asc,id.asc",
        tracked_since=tracked_since,
    )
    redeems, redeems_ok = _fetch_all(
        base,
        headers,
        "tracked_wallet_redeems",
        wallet,
        "condition_id,asset,event_id,title,slug,amount_usdc,traded_at",
        order="traded_at.asc",
        tracked_since=tracked_since,
    )
    positions, positions_ok = _fetch_all(
        base,
        headers,
        "tracked_wallet_positions",
        wallet,
        (
            "condition_id,asset,event_id,title,slug,outcome,size,avg_price,cur_price,"
            "initial_value,current_value,cash_pnl,percent_pnl,redeemable,end_date"
        ),
        order="current_value.desc",
    )

    if not (activity_ok and redeems_ok and positions_ok):
        return [], {
            "activity": len(activity),
            "redeems": len(redeems),
            "positions": len(positions),
        }, False

    activity = pc._filter_wallet_rows_since(activity, tracked_since)
    # The only bettor-selection rule retained here is the canonical position's
    # total BUY entry stake threshold. No sport gate is applied.
    activity = pc._filter_tracked_wallet_activity_amount(activity)
    redeems = pc._filter_wallet_rows_since(redeems, tracked_since)
    redeems = pc._filter_wallet_redeems_to_activity(redeems, activity)
    positions = pc._filter_positions_since_tracking(positions, activity)

    resolved = pc._compute_resolved_stats(positions, redeems)
    lifecycle = pc._build_display_activity(
        activity,
        positions,
        resolved["resolved_won_ids"],
        resolved["resolved_lost_ids"],
        redeems,
    )
    counts = {
        "activity": len(activity),
        "redeems": len(redeems),
        "positions": len(positions),
        "canonical_bets": len(lifecycle),
        "open_positions": len(resolved["open_positions"]),
    }
    return lifecycle, counts, True


def backfill_wallet(wallet_row: Dict[str, Any], apply: bool) -> bool:
    wallet = str(wallet_row.get("wallet") or "").lower()
    nickname = wallet_row.get("nickname") or wallet[:10]
    lifecycle, counts, ok = _build_wallet_lifecycle(wallet_row)
    if not ok:
        print(f"[{nickname}] FAILED read: {counts}")
        return False

    print(
        f"[{nickname}] qualifying activity={counts['activity']} "
        f"canonical={counts['canonical_bets']} open={counts['open_positions']}"
    )
    if not apply:
        return True

    base = pc._supabase_base_url()
    headers = pc._supabase_headers()
    if not pc._persist_wallet_bet_rows(base, headers, wallet, lifecycle):
        print(f"[{nickname}] FAILED normalized upsert")
        return False

    if not pc.compute_and_save_wallet_stats(
        wallet,
        allow_verified_sport_rebase=True,
    ):
        print(f"[{nickname}] FAILED stats refresh")
        return False

    print(f"[{nickname}] OK")
    return True


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wallet",
        help="Optional exact wallet address; default is every tracked wallet.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist normalized rows and refreshed stats. Default is dry-run.",
    )
    args = parser.parse_args()

    wallets = pc.list_tracked_wallets()
    if args.wallet:
        target = args.wallet.lower()
        wallets = [
            row for row in wallets
            if str(row.get("wallet") or "").lower() == target
        ]
    if not wallets:
        print("No matching tracked wallets.")
        return 1

    failures = 0
    for wallet_row in wallets:
        if not backfill_wallet(wallet_row, args.apply):
            failures += 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(f"{mode}: wallets={len(wallets)} failures={failures}")
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
