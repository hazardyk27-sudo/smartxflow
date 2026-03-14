import requests
import time
import threading

_BASE = "https://api.smarkets.com/v3"
_HEADERS = {"Accept": "application/json"}
_TIMEOUT = 12

_snapshot_lock = threading.Lock()
_prev_snapshots = {}

def _get(path):
    resp = requests.get(f"{_BASE}{path}", headers=_HEADERS, timeout=_TIMEOUT)
    resp.raise_for_status()
    return resp.json()


def find_top_football_events(limit=3):
    params = {
        "type": "football_match",
        "state": "live",
        "limit": 50,
    }
    resp = requests.get(f"{_BASE}/events/", headers=_HEADERS, params=params, timeout=_TIMEOUT)
    resp.raise_for_status()
    live_events = resp.json().get("events", [])

    if len(live_events) < limit:
        params2 = {
            "type": "football_match",
            "state": "upcoming",
            "limit": 50,
            "sort": "start_datetime",
        }
        resp2 = requests.get(f"{_BASE}/events/", headers=_HEADERS, params=params2, timeout=_TIMEOUT)
        resp2.raise_for_status()
        upcoming = resp2.json().get("events", [])
        live_events.extend(upcoming)

    events_with_volume = []
    for ev in live_events:
        eid = ev["id"]
        try:
            mkts = _get(f"/events/{eid}/markets/")
            winner_market = None
            for m in mkts.get("markets", []):
                if m.get("slug") == "winner":
                    winner_market = m
                    break
            if not winner_market:
                continue
            mid = winner_market["id"]
            vol_data = _get(f"/markets/{mid}/volumes/")
            total_vol = 0
            for v in vol_data.get("volumes", []):
                total_vol = v.get("volume", 0) / 100.0
            events_with_volume.append({
                "event_id": eid,
                "name": ev.get("name", ""),
                "state": ev.get("state", ""),
                "start": ev.get("start_datetime", ""),
                "market_id": mid,
                "total_volume_gbp": total_vol,
            })
        except Exception:
            continue

    events_with_volume.sort(key=lambda x: x["total_volume_gbp"], reverse=True)
    return events_with_volume[:limit]


def get_market_data(market_id):
    contracts = _get(f"/markets/{market_id}/contracts/")
    quotes = _get(f"/markets/{market_id}/quotes/")
    vol_data = _get(f"/markets/{market_id}/volumes/")

    total_volume = 0
    for v in vol_data.get("volumes", []):
        total_volume = v.get("volume", 0) / 100.0

    contract_map = {}
    for c in contracts.get("contracts", []):
        cid = c["id"]
        ct = c.get("contract_type", {}).get("name", "")
        label = c.get("name", ct)
        if ct == "HOME":
            sort_order = 0
            sel_key = "1"
        elif ct == "DRAW":
            sort_order = 1
            sel_key = "X"
        elif ct == "AWAY":
            sort_order = 2
            sel_key = "2"
        else:
            sort_order = 3
            sel_key = ct
        contract_map[cid] = {
            "id": cid,
            "name": label,
            "type": ct,
            "sel_key": sel_key,
            "sort_order": sort_order,
        }

    selections = []
    for cid, info in contract_map.items():
        q = quotes.get(cid, {})
        bids = q.get("bids", [])
        offers = q.get("offers", [])

        best_bid_pct = bids[0]["price"] / 100.0 if bids else None
        best_offer_pct = offers[0]["price"] / 100.0 if offers else None

        best_bid_odds = round(100.0 / best_bid_pct, 2) if best_bid_pct and best_bid_pct > 0 else None
        best_offer_odds = round(100.0 / best_offer_pct, 2) if best_offer_pct and best_offer_pct > 0 else None

        total_bid_gbp = sum(b["quantity"] for b in bids) / 100.0
        total_offer_gbp = sum(o["quantity"] for o in offers) / 100.0

        if best_bid_odds and best_bid_odds > 0:
            est_back_stake = round(total_bid_gbp / best_bid_odds, 2)
        else:
            est_back_stake = 0

        spread = round(best_offer_pct - best_bid_pct, 2) if best_bid_pct and best_offer_pct else None

        selections.append({
            "id": cid,
            "name": info["name"],
            "sel_key": info["sel_key"],
            "sort_order": info["sort_order"],
            "best_bid_pct": best_bid_pct,
            "best_offer_pct": best_offer_pct,
            "best_bid_odds": best_bid_odds,
            "best_offer_odds": best_offer_odds,
            "total_bid_gbp": round(total_bid_gbp, 2),
            "total_offer_gbp": round(total_offer_gbp, 2),
            "est_back_stake": est_back_stake,
            "spread": spread,
        })

    selections.sort(key=lambda x: x["sort_order"])

    return {
        "total_volume_gbp": total_volume,
        "selections": selections,
    }


def fetch_all_data(limit=3):
    events = find_top_football_events(limit=limit)
    now = time.time()
    results = []

    with _snapshot_lock:
        for ev in events:
            mid = ev["market_id"]
            try:
                mdata = get_market_data(mid)
            except Exception as e:
                mdata = {"total_volume_gbp": ev["total_volume_gbp"], "selections": [], "error": str(e)}

            prev = _prev_snapshots.get(mid)
            delta = None
            if prev:
                prev_volume = prev.get("total_volume_gbp", 0)
                curr_volume = mdata.get("total_volume_gbp", 0)
                volume_increase = curr_volume - prev_volume
                elapsed_sec = now - prev.get("ts", now)
                elapsed_min = elapsed_sec / 60.0 if elapsed_sec > 0 else 1

                prev_sels = {s["id"]: s for s in prev.get("selections", [])}
                bid_drops = {}
                total_bid_drop = 0
                for s in mdata.get("selections", []):
                    ps = prev_sels.get(s["id"])
                    if ps:
                        drop = ps["total_bid_gbp"] - s["total_bid_gbp"]
                        if drop > 0:
                            bid_drops[s["id"]] = drop
                            total_bid_drop += drop

                per_sel_matched = {}
                if volume_increase > 0 and total_bid_drop > 0:
                    for sid, drop in bid_drops.items():
                        ratio = drop / total_bid_drop
                        per_sel_matched[sid] = round(volume_increase * ratio, 2)

                delta = {
                    "volume_increase": volume_increase,
                    "elapsed_min": round(elapsed_min, 1),
                    "flow_per_min": round(volume_increase / elapsed_min, 2) if elapsed_min > 0 else 0,
                    "total_bid_drop": round(total_bid_drop, 2),
                    "estimated_cancelled": round(max(0, total_bid_drop - volume_increase), 2),
                    "per_sel_matched": per_sel_matched,
                }

            _prev_snapshots[mid] = {
                "total_volume_gbp": mdata.get("total_volume_gbp", 0),
                "selections": mdata.get("selections", []),
                "ts": now,
            }

            results.append({
                "event_id": ev["event_id"],
                "name": ev["name"],
                "state": ev["state"],
                "start": ev["start"],
                "market_id": mid,
                "market": mdata,
                "delta": delta,
            })

    return {
        "events": results,
        "fetched_at": now,
        "has_previous": any(r["delta"] is not None for r in results),
    }
