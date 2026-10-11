"""Tracked-bettor profile V4.2 consistency patch.

V4.1 intentionally reads aggregate profile stats from the persisted
``tracked_wallets`` snapshot for speed, while fetching canonical open bets
separately from ``tracked_wallet_bets``. When lifecycle reconciliation closes a
bet between summary-sync cycles, the persisted snapshot can temporarily report a
stale open-position count even though the interactive open-bet list is correct.

V4.2 makes the visible open count use the same canonical open ledger that builds
``open_positions``. Other expensive aggregate stats stay on the persisted
snapshot fast path. Open exposure keeps its persisted value when stored position
snapshots are incomplete, and coverage explicitly reports that caveat.
"""
from __future__ import annotations

from typing import Any, Dict, List

from . import polymarket_profile_v41_patch as v41


def _client():
    from . import polymarket_client as client
    return client


def _as_float(value: Any) -> float:
    try:
        return float(value or 0)
    except (TypeError, ValueError):
        return 0.0


def _rebuild_summary(profile: Dict[str, Any], missing_snapshots: int) -> List[str]:
    stats = profile.get("stats") or {}
    summary: List[str] = []
    bet_count = int(stats.get("bet_count") or stats.get("trade_count") or 0)
    if bet_count:
        summary.append(
            f"{bet_count} canonical bahis, toplam "
            f"{_as_float(stats.get('total_invested_usdc')):,.0f} USDC yatırım.".replace(",", ".")
        )
    else:
        summary.append("Henüz kayıtlı canonical bahsi bulunmuyor.")

    resolved_total = int(stats.get("resolved_total") or 0)
    win_rate = stats.get("win_rate_pct")
    if resolved_total and win_rate is not None:
        summary.append(
            f"Sonuçlanan {resolved_total} bahisin %{win_rate}'ini kazandı."
        )

    open_count = int(stats.get("open_position_count") or 0)
    if open_count:
        if missing_snapshots:
            summary.append(
                f"Şu an {open_count} canonical açık bahsi var; "
                f"{missing_snapshots} pozisyon snapshot detayı eksik."
            )
        else:
            summary.append(
                f"Şu an {open_count} açık pozisyonu var, toplam "
                f"{_as_float(stats.get('open_exposure_usdc')):,.0f} USDC açık değer.".replace(",", ".")
            )
    return summary


def get_wallet_profile_v42(wallet: str):
    profile = v41.get_wallet_profile_v41(wallet)
    if not profile:
        return profile

    open_positions = list(profile.get("open_positions") or [])
    stats = dict(profile.get("stats") or {})
    coverage = dict(profile.get("coverage") or {})

    snapshot_count = int(stats.get("open_position_count") or 0)
    canonical_open_count = len(open_positions)
    missing_snapshots = sum(
        1 for row in open_positions if bool((row or {}).get("snapshot_missing"))
    )

    stats["open_position_count"] = canonical_open_count
    coverage["open_position_count_source"] = "canonical_open_ledger"
    coverage["open_position_count_snapshot"] = snapshot_count
    coverage["open_position_count_reconciled"] = snapshot_count != canonical_open_count
    coverage["open_position_snapshot_missing_count"] = missing_snapshots
    coverage["open_exposure_complete"] = missing_snapshots == 0

    # When every canonical open bet has a stored current-position snapshot,
    # recompute exposure from the same rows so count and value share one source.
    # Otherwise retain the persisted aggregate exposure but surface the partial
    # snapshot state in coverage instead of pretending it is fully current.
    if open_positions and missing_snapshots == 0:
        stats["open_exposure_usdc"] = round(
            sum(_as_float(row.get("current_value")) for row in open_positions),
            2,
        )
        coverage["open_exposure_source"] = "canonical_open_positions"
    else:
        coverage["open_exposure_source"] = "persisted_snapshot_partial"

    profile["stats"] = stats
    profile["coverage"] = coverage
    profile["summary"] = _rebuild_summary(profile, missing_snapshots)
    profile["contract_version"] = "2026-10-11.v4.2-open-count-ledger"
    return profile


def bind_polymarket_profile_v42_patch() -> None:
    client = _client()
    if getattr(client, "_sxf_profile_v42_bound", False):
        return
    client.get_wallet_profile = get_wallet_profile_v42
    client.TRACKED_WALLET_API_CONTRACT_VERSION = "2026-10-11.v4.2-open-count-ledger"
    client._sxf_profile_v42_bound = True
