"""Batch checkpoint loader for Polymarket trade scraping.

The legacy scraper reads the latest stored trade once per condition_id. This
module keeps identical checkpoint semantics while allowing all condition_ids
for a match to be resolved by one read-only Supabase RPC call.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Iterable, Optional

import requests

RPC_NAME = "polymarket_latest_trade_checkpoints"


def _parse_timestamp(value: Any) -> Optional[int]:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return int(dt.timestamp())


def fetch_latest_trade_checkpoints(
    writer: Any,
    condition_ids: Iterable[str],
    *,
    log,
    ssl_verify=True,
) -> Dict[str, Optional[int]]:
    """Return latest traded_at unix timestamps for all requested conditions.

    If the batch RPC is unavailable, fall back to the existing per-condition
    reader so behavior remains unchanged until the DB function is deployed.
    A failed RPC is disabled for this writer instance to avoid repeated noise.
    """
    ids = list(dict.fromkeys(str(value).strip() for value in condition_ids if value))
    if not ids:
        return {}

    if getattr(writer, "_checkpoint_batch_rpc_available", None) is False:
        return {condition_id: writer.get_last_traded_at(condition_id) for condition_id in ids}

    result: Dict[str, Optional[int]] = {condition_id: None for condition_id in ids}
    try:
        response = requests.post(
            writer._rest_url("rpc/" + RPC_NAME),
            headers=writer._headers(),
            json={"condition_ids": ids},
            timeout=15,
            verify=ssl_verify,
        )
        if response.status_code == 200:
            rows = response.json()
            if not isinstance(rows, list):
                raise ValueError("RPC response is not a list")
            for row in rows:
                if not isinstance(row, dict):
                    continue
                condition_id = str(row.get("condition_id") or "").strip()
                if condition_id in result:
                    result[condition_id] = _parse_timestamp(row.get("traded_at"))
            writer._checkpoint_batch_rpc_available = True
            return result

        writer._checkpoint_batch_rpc_available = False
        log(
            f"[Checkpoint Batch] RPC HTTP {response.status_code}; "
            "legacy checkpoint fallback enabled for this process"
        )
    except Exception as exc:
        writer._checkpoint_batch_rpc_available = False
        log(f"[Checkpoint Batch] RPC unavailable ({exc}); legacy fallback enabled")

    return {condition_id: writer.get_last_traded_at(condition_id) for condition_id in ids}
