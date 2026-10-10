"""Non-blocking tracked-bettor visibility for Polymarket.

Sport classification is metadata only. It must never decide whether a tracked
bettor's qualifying canonical position is stored, counted, or returned by the
profile API. The existing >= $1,000 total BUY-entry stake rule is preserved.

This module is bound from ``services.__init__`` so legacy callers keep their
public function names while the visibility contract is upgraded in one place.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Iterable, List, Optional, Tuple


def _merge_rows(*groups: Iterable[Dict[str, Any]]) -> List[Dict[str, Any]]:
    rows: List[Dict[str, Any]] = []
    seen: set[Tuple[Any, ...]] = set()
    for group in groups:
        for row in group or []:
            key = (
                row.get("transactionHash") or row.get("transaction_hash"),
                row.get("asset"),
                row.get("conditionId") or row.get("condition_id"),
                row.get("timestamp") or row.get("traded_at"),
                row.get("side"),
                row.get("outcome"),
            )
            if key in seen:
                continue
            seen.add(key)
            rows.append(row)

    def _sort_key(row: Dict[str, Any]) -> Tuple[int, str]:
        raw_ts = row.get("timestamp")
        try:
            return int(raw_ts or 0), str(row.get("traded_at") or "")
        except (TypeError, ValueError):
            return 0, str(row.get("traded_at") or "")

    rows.sort(key=_sort_key, reverse=True)
    return rows


def _fetch_rest_pages(
    client,
    base: str,
    headers: Dict[str, str],
    table: str,
    *,
    select_fields: str,
    wallet: str,
    order: Optional[str] = None,
    page_size: int = 1000,
    max_pages: int = 250,
) -> Tuple[List[Dict[str, Any]], bool]:
    rows: List[Dict[str, Any]] = []
    try:
        for page in range(max_pages):
            params: Dict[str, Any] = {
                "select": select_fields,
                "wallet": f"eq.{wallet.lower()}",
                "limit": page_size,
                "offset": page * page_size,
            }
            if order:
                params["order"] = order
            response = client.requests.get(
                f"{base}/rest/v1/{table}",
                headers=headers,
                params=params,
                timeout=20,
            )
            if response.status_code != 200:
                return [], False
            page_rows = response.json()
            if not isinstance(page_rows, list):
                return [], False
            rows.extend(page_rows)
            if len(page_rows) < page_size:
                return rows, True
        client.logger.warning(
            "[PolyVisibility] %s pagination safety cap reached for %s (%s rows)",
            table,
            wallet[:10],
            len(rows),
        )
        return rows, False
    except Exception as exc:
        client.logger.warning(
            "[PolyVisibility] %s pagination failed for %s: %s",
            table,
            wallet[:10],
            exc,
        )
        return [], False


def bind_polymarket_visibility_patch() -> None:
    from . import polymarket_client as client

    if getattr(client, "_sxf_unfiltered_visibility_bound", False):
        return

    original_fetch_activity = client.fetch_wallet_activity
    original_fetch_redeems = client.fetch_wallet_redeems
    original_fetch_positions = client.fetch_wallet_positions
    original_compute_and_save = client.compute_and_save_wallet_stats
    original_get_wallet_profile = client.get_wallet_profile

    def _all_items_visible(
        items: List[Dict[str, Any]],
    ) -> Tuple[List[Dict[str, Any]], bool]:
        """Compatibility gate: classification never removes a bettor row."""
        return list(items or []), True

    def fetch_wallet_activity(
        wallet: str,
        since_ts: Optional[int] = None,
        max_pages: Optional[int] = None,
        classification_details: bool = False,
    ):
        result = original_fetch_activity(
            wallet,
            since_ts,
            max_pages,
            classification_details=True,
        )
        if not isinstance(result, tuple):
            result = ([], True)
        if len(result) == 2:
            rows, truncated = result
            if classification_details:
                return list(rows or []), bool(truncated), [], []
            return list(rows or []), bool(truncated)

        verified, truncated, uncertain, non_football = result
        visible = _merge_rows(verified, uncertain, non_football)
        if classification_details:
            return visible, bool(truncated), list(uncertain or []), list(non_football or [])
        return visible, bool(truncated)

    def fetch_wallet_redeems(
        wallet: str,
        since_ts: Optional[int] = None,
        max_pages: Optional[int] = None,
        classification_details: bool = False,
    ):
        result = original_fetch_redeems(
            wallet,
            since_ts,
            max_pages,
            classification_details=True,
        )
        if not isinstance(result, tuple):
            result = ([], True)
        if len(result) == 2:
            rows, truncated = result
            if classification_details:
                return list(rows or []), bool(truncated), [], []
            return list(rows or []), bool(truncated)

        verified, truncated, uncertain, non_football = result
        visible = _merge_rows(verified, uncertain, non_football)
        if classification_details:
            return visible, bool(truncated), list(uncertain or []), list(non_football or [])
        return visible, bool(truncated)

    def fetch_wallet_positions(
        wallet: str,
        classification_details: bool = False,
    ):
        result = original_fetch_positions(wallet, classification_details=True)
        if not isinstance(result, tuple):
            result = ([], False)
        if len(result) == 2:
            rows, ok = result
            if classification_details:
                return list(rows or []), bool(ok), [], []
            return list(rows or []), bool(ok)

        verified, classified_ok, uncertain, non_football = result
        visible = _merge_rows(verified, uncertain, non_football)
        # In the legacy implementation `ok=False` also meant "classification
        # uncertain". Once classification is non-blocking, that is still a
        # successful positions API read. A real API failure returns the 2-tuple
        # branch above.
        api_ok = bool(classified_ok or uncertain or non_football or verified)
        if classification_details:
            return visible, api_ok, list(uncertain or []), list(non_football or [])
        return visible, api_ok

    def _fetch_persisted_wallet_bets_for_stats(
        base: str,
        headers: Dict[str, str],
        wallet: str,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        return _fetch_rest_pages(
            client,
            base,
            headers,
            "tracked_wallet_bets",
            select_fields=(
                "bet_key,stake_usdc,avg_entry_price,result,lifecycle_status,"
                "fill_count,first_traded_at,last_traded_at,sport_classification"
            ),
            wallet=wallet,
            order="first_traded_at.asc.nullsfirst",
        )

    def _fetch_persisted_wallet_bets_for_profile(
        base: str,
        headers: Dict[str, str],
        wallet: str,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        return _fetch_rest_pages(
            client,
            base,
            headers,
            "tracked_wallet_bets",
            select_fields=(
                "bet_key,asset,condition_id,event_id,match_key,match_name,home,away,"
                "slug,kickoff_utc,title,market_type,market_label,selection,side,"
                "outcome_raw,selection_label,side_label,bet_label,lifecycle_status,"
                "result,status_label,stake_usdc,sell_proceeds_usdc,"
                "redeem_proceeds_usdc,avg_entry_price,avg_entry_decimal,pnl_usdc,"
                "pnl_kind,fill_count,buy_fill_count,sell_fill_count,first_traded_at,"
                "last_traded_at,latest_market_price,latest_market_decimal,"
                "latest_market_at,closing_price,closing_decimal,closing_observed_at,"
                "clv_probability_pp,clv_pct,sport_classification,sport_verified_at,"
                "sport_classification_source"
            ),
            wallet=wallet,
            order="last_traded_at.desc.nullslast",
        )

    def _persist_wallet_bet_rows(
        base: str,
        headers: Dict[str, str],
        wallet: str,
        lifecycle_rows: List[Dict[str, Any]],
    ) -> bool:
        """Persist every qualifying canonical bet; sport is metadata only."""
        if not lifecycle_rows:
            return True

        now = datetime.now(timezone.utc).isoformat()
        payload: List[Dict[str, Any]] = []
        for row in lifecycle_rows:
            bet_key = row.get("bet_key")
            if not bet_key:
                continue
            classification = row.get("sport_classification")
            if classification not in {
                client.FOOTBALL_CLASS_VERIFIED,
                client.FOOTBALL_CLASS_NON_FOOTBALL,
                client.FOOTBALL_CLASS_UNCERTAIN,
            }:
                classification = client.FOOTBALL_CLASS_UNCERTAIN
            payload.append({
                "wallet": wallet,
                "bet_key": bet_key,
                "asset": row.get("asset"),
                "condition_id": row.get("condition_id"),
                "event_id": row.get("event_id"),
                "match_key": row.get("match_key"),
                "match_name": row.get("match_name") or row.get("match"),
                "home": row.get("home"),
                "away": row.get("away"),
                "slug": row.get("slug"),
                "kickoff_utc": row.get("kickoff_utc"),
                "title": row.get("title"),
                "market_type": row.get("market_type"),
                "market_label": row.get("market_label"),
                "selection": row.get("selection"),
                "side": row.get("side"),
                "outcome_raw": row.get("outcome_raw"),
                "selection_label": row.get("selection_label"),
                "side_label": row.get("side_label"),
                "bet_label": row.get("bet_label"),
                "lifecycle_status": row.get("lifecycle_status"),
                "result": row.get("result"),
                "status_label": row.get("status_label"),
                "stake_usdc": row.get("stake_usdc"),
                "sell_proceeds_usdc": row.get("sell_proceeds_usdc"),
                "redeem_proceeds_usdc": row.get("redeem_proceeds_usdc"),
                "avg_entry_price": row.get("avg_entry_price"),
                "avg_entry_decimal": row.get("avg_entry_decimal"),
                "pnl_usdc": row.get("pnl_usdc"),
                "pnl_kind": row.get("pnl_kind"),
                "fill_count": int(row.get("fill_count") or 0),
                "buy_fill_count": int(row.get("buy_fill_count") or 0),
                "sell_fill_count": int(row.get("sell_fill_count") or 0),
                "first_traded_at": row.get("first_traded_at"),
                "last_traded_at": row.get("last_traded_at"),
                "sport_classification": classification,
                "sport_verified_at": row.get("sport_verified_at"),
                "sport_classification_source": (
                    row.get("sport_classification_source")
                    or "visibility_nonblocking"
                ),
                "updated_at": now,
            })

        if not payload:
            return True
        post_headers = {
            **headers,
            "Content-Type": "application/json",
            "Prefer": "resolution=merge-duplicates",
        }
        url = f"{base}/rest/v1/tracked_wallet_bets?on_conflict=wallet,bet_key"
        try:
            for offset in range(0, len(payload), 500):
                response = client.requests.post(
                    url,
                    headers=post_headers,
                    json=payload[offset:offset + 500],
                    timeout=20,
                )
                if response.status_code not in (200, 201, 204):
                    client.logger.warning(
                        "[PolyVisibility] normalized bet upsert failed for %s HTTP %s",
                        wallet[:10],
                        response.status_code,
                    )
                    return False
            return True
        except Exception as exc:
            client.logger.warning(
                "[PolyVisibility] normalized bet upsert failed for %s: %s",
                wallet[:10],
                exc,
            )
            return False

    def _full_current_positions(
        base: str,
        headers: Dict[str, str],
        wallet: str,
    ) -> Tuple[List[Dict[str, Any]], bool]:
        return _fetch_rest_pages(
            client,
            base,
            headers,
            "tracked_wallet_positions",
            select_fields=(
                "condition_id,asset,event_id,title,slug,outcome,size,avg_price,"
                "cur_price,initial_value,current_value,cash_pnl,percent_pnl,"
                "redeemable,end_date"
            ),
            wallet=wallet,
            order="current_value.desc",
        )

    def compute_and_save_wallet_stats(
        wallet: str,
        allow_verified_sport_rebase: bool = False,
    ) -> bool:
        ok = original_compute_and_save(wallet, allow_verified_sport_rebase)
        base = client._supabase_base_url()
        if not base or not wallet:
            return ok
        headers = client._supabase_headers()
        wallet_l = wallet.lower()
        bet_rows, bets_ok = _fetch_persisted_wallet_bets_for_profile(
            base, headers, wallet_l
        )
        positions, positions_ok = _full_current_positions(base, headers, wallet_l)
        if not (bets_ok and positions_ok):
            return ok

        qualifying_assets = {
            row.get("asset")
            for row in bet_rows
            if row.get("asset")
            and float(row.get("stake_usdc") or 0)
                >= client.MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC
        }
        visible_positions = [
            row for row in positions if row.get("asset") in qualifying_assets
        ]
        resolved = client._compute_resolved_stats(visible_positions, [])
        payload = {
            "open_position_count": len(resolved["open_positions"]),
            "open_exposure_usdc": round(resolved["open_exposure"], 2),
        }
        try:
            response = client.requests.patch(
                f"{base}/rest/v1/tracked_wallets",
                headers={**headers, "Content-Type": "application/json"},
                params={"wallet": f"eq.{wallet_l}"},
                json=payload,
                timeout=15,
            )
            return ok and response.status_code in (200, 204)
        except Exception:
            return ok

    def get_wallet_profile(wallet: str):
        profile = original_get_wallet_profile(wallet)
        if not profile:
            return profile

        coverage = profile.setdefault("coverage", {})
        coverage["football_only"] = False
        coverage["sport_filtering"] = "disabled"
        coverage["sport_classification_role"] = "metadata_only"

        # Repair current-open detail from the complete stored positions snapshot
        # rather than the legacy 200-row profile read.
        base = client._supabase_base_url()
        if base and wallet:
            headers = client._supabase_headers()
            positions, positions_ok = _full_current_positions(
                base, headers, wallet.lower()
            )
            if positions_ok:
                bets = profile.get("bets") or []
                qualifying_assets = {
                    row.get("asset_id") or row.get("asset")
                    for row in bets
                    if (row.get("asset_id") or row.get("asset"))
                    and float(row.get("stake_usdc") or 0)
                        >= client.MIN_TRACKED_WALLET_TRADE_AMOUNT_USDC
                }
                visible_positions = [
                    row for row in positions if row.get("asset") in qualifying_assets
                ]
                resolved = client._compute_resolved_stats(visible_positions, [])
                open_rows = [
                    client._with_wallet_bet_display_metadata(row)
                    for row in resolved["open_positions"]
                ]
                profile["open_positions"] = open_rows
                stats = profile.setdefault("stats", {})
                stats["open_position_count"] = len(open_rows)
                stats["open_exposure_usdc"] = round(resolved["open_exposure"], 2)

        summary = []
        for line in profile.get("summary") or []:
            line = str(line).replace("futbol bahsi", "bahis")
            summary.append(line)
        profile["summary"] = summary
        profile["contract_version"] = "2026-10-10.v3-unfiltered"
        return profile

    client._filter_verified_football_items = _all_items_visible
    client.fetch_wallet_activity = fetch_wallet_activity
    client.fetch_wallet_redeems = fetch_wallet_redeems
    client.fetch_wallet_positions = fetch_wallet_positions
    client._fetch_persisted_wallet_bets_for_stats = _fetch_persisted_wallet_bets_for_stats
    client._fetch_persisted_wallet_bets_for_profile = _fetch_persisted_wallet_bets_for_profile
    client._persist_wallet_bet_rows = _persist_wallet_bet_rows
    client.compute_and_save_wallet_stats = compute_and_save_wallet_stats
    client.get_wallet_profile = get_wallet_profile
    client.TRACKED_WALLET_API_CONTRACT_VERSION = "2026-10-10.v3-unfiltered"
    client._sxf_unfiltered_visibility_bound = True
