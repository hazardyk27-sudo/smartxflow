#!/usr/bin/env python3
"""Repair durable tracked-bettor lifecycle results from Polymarket CLOB.

Default mode is dry-run. ``--apply`` persists resolved ``won/lost`` states and
refreshes the wallet summary from ``tracked_wallet_bets``. Sport classification
is metadata only; no qualifying canonical bet is filtered out.
"""
from __future__ import annotations

import argparse

from services import polymarket_client as pc


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--wallet",
        help="Optional exact tracked wallet. Default: every tracked wallet.",
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persist CLOB-resolved lifecycle states. Default: dry-run.",
    )
    parser.add_argument(
        "--max-conditions",
        type=int,
        default=0,
        help="Maximum unique condition ids per wallet; 0 means no limit.",
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
    total_resolved = 0
    limit = args.max_conditions or None
    for wallet_row in wallets:
        wallet = str(wallet_row.get("wallet") or "").lower()
        nickname = wallet_row.get("nickname") or wallet[:10]
        result = pc.reconcile_persisted_wallet_bet_resolutions(
            wallet,
            max_condition_ids=limit,
            apply=args.apply,
        )
        total_resolved += int(result.get("resolved_rows") or 0)
        print(
            f"[{nickname}] checked_conditions={result.get('checked_conditions', 0)} "
            f"resolved_rows={result.get('resolved_rows', 0)} "
            f"persisted={result.get('persisted')}"
        )
        if not result.get("persisted"):
            failures += 1
            continue
        if args.apply and not pc.compute_and_save_wallet_stats(wallet):
            print(f"[{nickname}] stats refresh FAILED")
            failures += 1

    mode = "APPLY" if args.apply else "DRY-RUN"
    print(
        f"{mode}: wallets={len(wallets)} resolved_rows={total_resolved} "
        f"failures={failures}"
    )
    return 1 if failures else 0


if __name__ == "__main__":
    raise SystemExit(main())
