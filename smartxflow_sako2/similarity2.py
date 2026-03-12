from datetime import datetime, timezone, timedelta

from smartxflow_sako2.config2 import (
    BLOCK_WEIGHTS, HARD_FILTER, LEAGUE_TIERS, DEFAULT_LEAGUE_TIER,
    VOLUME_BUCKETS, TOP_SIMILAR_COUNT,
)


def _get_league_tier(league):
    for tier, leagues in LEAGUE_TIERS.items():
        if league in leagues:
            return tier
    return DEFAULT_LEAGUE_TIER


def _get_volume_bucket(vol):
    if vol is None:
        return 1
    for bucket, (lo, hi) in VOLUME_BUCKETS.items():
        if lo <= vol < hi:
            return bucket
    return 1


def _get_1x2_market(entry):
    markets = entry.get("markets", {})
    for key in ["moneyway_1x2", "dropping_1x2"]:
        m = markets.get(key)
        if m and m.get("opening_odds"):
            return m
    return None


def _get_ou_market(entry):
    markets = entry.get("markets", {})
    for key in ["moneyway_ou25", "dropping_ou25"]:
        m = markets.get(key)
        if m and m.get("opening_odds"):
            return m
    return None


def _get_kg_market(entry):
    markets = entry.get("markets", {})
    for key in ["moneyway_btts", "dropping_btts"]:
        m = markets.get(key)
        if m and m.get("opening_odds"):
            return m
    return None


def _clamp(v, lo=0.0, hi=1.0):
    return max(lo, min(hi, v))


def _odds_diff_score(a, b, max_diff=0.20):
    if a is None or b is None:
        return 0.0
    return max(0.0, 1.0 - (abs(a - b) / max_diff) ** 2)


def _drift_pct(opening, closing):
    if opening is None or closing is None or opening == 0:
        return 0.0
    return (closing - opening) / opening


def _drift_diff_score(drift_a, drift_b, max_diff=0.10):
    if (drift_a > 0.005 and drift_b < -0.005) or (drift_a < -0.005 and drift_b > 0.005):
        return _clamp((1.0 - (abs(drift_a - drift_b) / max_diff) ** 2) * 0.2)
    a_flat = abs(drift_a) < 0.005
    b_flat = abs(drift_b) < 0.005
    if a_flat != b_flat:
        moving = abs(drift_b) if a_flat else abs(drift_a)
        if moving > 0.015:
            return _clamp((1.0 - (abs(drift_a - drift_b) / max_diff) ** 2) * 0.5)
    return _clamp(1.0 - (abs(drift_a - drift_b) / max_diff) ** 2)


def _amount_ratio_score(q_val, c_val):
    if q_val is None or c_val is None or q_val <= 0 or c_val <= 0:
        return 0.0
    ratio = max(q_val, c_val) / max(min(q_val, c_val), 1)
    return _clamp(1.0 - (ratio - 1.0) / 4.0)


def _compute_odds_block(q_market, c_market, sel_keys):
    if not q_market or not c_market:
        return None

    q_open = q_market.get("opening_odds") or {}
    q_close = q_market.get("closing_odds") or {}
    c_open = c_market.get("opening_odds") or {}
    c_close = c_market.get("closing_odds") or {}

    open_scores = []
    close_scores = []
    drift_scores = []

    for key in sel_keys:
        qo = q_open.get(key)
        co = c_open.get(key)
        qc = q_close.get(key)
        cc = c_close.get(key)

        if qo is not None and co is not None:
            open_scores.append(_odds_diff_score(qo, co))
        if qc is not None and cc is not None:
            close_scores.append(_odds_diff_score(qc, cc))

        q_drift = _drift_pct(qo, qc)
        c_drift = _drift_pct(co, cc)
        drift_scores.append(_drift_diff_score(q_drift, c_drift))

    if not open_scores and not close_scores:
        return None

    avg_open = sum(open_scores) / len(open_scores) if open_scores else 0.0
    avg_close = sum(close_scores) / len(close_scores) if close_scores else 0.0
    avg_drift = sum(drift_scores) / len(drift_scores) if drift_scores else 0.0

    odds_only = round((avg_open * 0.45 + avg_close * 0.55), 4)
    total = round((avg_open * 0.20 + avg_close * 0.25 + avg_drift * 0.55), 4)
    return {
        "score": total,
        "odds_only": odds_only,
        "drift_only": round(avg_drift, 4),
        "opening": round(avg_open, 4),
        "closing": round(avg_close, 4),
        "drift": round(avg_drift, 4),
    }


def _get_1x2_role_mapping(market):
    odds = market.get("closing_odds") or market.get("opening_odds") or {}
    home_odds = odds.get("home")
    away_odds = odds.get("away")
    if home_odds is not None and away_odds is not None:
        if home_odds <= away_odds:
            return {"favorite": "home", "draw": "draw", "underdog": "away"}
        else:
            return {"favorite": "away", "draw": "draw", "underdog": "home"}
    return {"favorite": "home", "draw": "draw", "underdog": "away"}


def _normalize_1x2_by_role(values, role_map):
    if not values:
        return {}
    return {
        "favorite": values.get(role_map["favorite"]),
        "draw": values.get(role_map["draw"]),
        "underdog": values.get(role_map["underdog"]),
    }


def _normalize_1x2_nv_by_role(nv_list, role_map):
    if not nv_list or len(nv_list) != 3:
        return None
    key_order = ["home", "draw", "away"]
    idx = {k: i for i, k in enumerate(key_order)}
    return [
        nv_list[idx[role_map["favorite"]]],
        nv_list[idx[role_map["draw"]]],
        nv_list[idx[role_map["underdog"]]],
    ]


def _compute_money_distribution(q_entry, c_entry):
    scores = []

    q_1x2 = _get_1x2_market(q_entry)
    c_1x2 = _get_1x2_market(c_entry)
    if q_1x2 and c_1x2:
        q_role = _get_1x2_role_mapping(q_1x2)
        c_role = _get_1x2_role_mapping(c_1x2)

        q_nv = q_1x2.get("closing_nv")
        c_nv = c_1x2.get("closing_nv")
        q_nv_norm = _normalize_1x2_nv_by_role(q_nv, q_role)
        c_nv_norm = _normalize_1x2_nv_by_role(c_nv, c_role)
        if q_nv_norm and c_nv_norm:
            nv_scores = []
            for i in range(3):
                nv_scores.append(_clamp(1.0 - abs(q_nv_norm[i] - c_nv_norm[i]) / 0.15))
            scores.append(sum(nv_scores) / len(nv_scores))

        q_amounts = q_1x2.get("closing_amounts") or {}
        c_amounts = c_1x2.get("closing_amounts") or {}
        if q_amounts and c_amounts:
            q_norm = _normalize_1x2_by_role(q_amounts, q_role)
            c_norm = _normalize_1x2_by_role(c_amounts, c_role)
            q_total = sum(v for v in q_norm.values() if v is not None) or 1
            c_total = sum(v for v in c_norm.values() if v is not None) or 1
            pct_scores = []
            abs_scores = []
            for role_key in ["favorite", "draw", "underdog"]:
                q_pct = (q_norm.get(role_key) or 0) / q_total
                c_pct = (c_norm.get(role_key) or 0) / c_total
                pct_scores.append(_clamp(1.0 - abs(q_pct - c_pct) / 0.20))
                abs_scores.append(_amount_ratio_score(q_norm.get(role_key), c_norm.get(role_key)))
            if pct_scores:
                pct_avg = sum(pct_scores) / len(pct_scores)
                abs_avg = sum(abs_scores) / len(abs_scores) if abs_scores else 0.0
                scores.append(pct_avg * 0.5 + abs_avg * 0.5)

    for get_market, sel_keys in [
        (_get_ou_market, ["over", "under"]),
        (_get_kg_market, ["yes", "no"]),
    ]:
        q_m = get_market(q_entry)
        c_m = get_market(c_entry)
        if not q_m or not c_m:
            continue

        q_nv = q_m.get("closing_nv")
        c_nv = c_m.get("closing_nv")
        if q_nv and c_nv and len(q_nv) == len(c_nv):
            nv_scores = []
            for i in range(len(q_nv)):
                nv_scores.append(_clamp(1.0 - abs(q_nv[i] - c_nv[i]) / 0.15))
            scores.append(sum(nv_scores) / len(nv_scores))

        q_amounts = q_m.get("closing_amounts") or {}
        c_amounts = c_m.get("closing_amounts") or {}
        if q_amounts and c_amounts:
            q_total = sum(v for v in q_amounts.values() if v is not None) or 1
            c_total = sum(v for v in c_amounts.values() if v is not None) or 1
            pct_scores = []
            abs_scores = []
            for key in sel_keys:
                q_pct = (q_amounts.get(key) or 0) / q_total
                c_pct = (c_amounts.get(key) or 0) / c_total
                pct_scores.append(_clamp(1.0 - abs(q_pct - c_pct) / 0.20))
                abs_scores.append(_amount_ratio_score(q_amounts.get(key), c_amounts.get(key)))
            if pct_scores:
                pct_avg = sum(pct_scores) / len(pct_scores)
                abs_avg = sum(abs_scores) / len(abs_scores) if abs_scores else 0.0
                scores.append(pct_avg * 0.5 + abs_avg * 0.5)

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)


def _compute_volume_similarity(q_vol, c_vol, q_bucket, c_bucket):
    if q_vol is None or c_vol is None or q_vol == 0 or c_vol == 0:
        bucket_score = _clamp(1.0 - abs(q_bucket - c_bucket) / 3.0)
        return round(bucket_score, 4)

    ratio = max(q_vol, c_vol) / max(min(q_vol, c_vol), 1)
    ratio_score = _clamp(1.0 - (ratio - 1.0) / 4.0)

    bucket_score = _clamp(1.0 - abs(q_bucket - c_bucket) / 3.0)

    return round(ratio_score * 0.70 + bucket_score * 0.30, 4)


def _get_primary_market_getter(market_filter):
    if market_filter == "1x2":
        return _get_1x2_market, ["home", "draw", "away"]
    elif market_filter == "ou25":
        return _get_ou_market, ["over", "under"]
    elif market_filter == "kg":
        return _get_kg_market, ["yes", "no"]
    return None, None


def _compute_single_market_money(q_entry, c_entry, get_market, sel_keys, is_1x2=False):
    q_m = get_market(q_entry)
    c_m = get_market(c_entry)
    if not q_m or not c_m:
        return 0.0

    scores = []

    if is_1x2:
        q_role = _get_1x2_role_mapping(q_m)
        c_role = _get_1x2_role_mapping(c_m)

        q_nv = q_m.get("closing_nv")
        c_nv = c_m.get("closing_nv")
        q_nv_norm = _normalize_1x2_nv_by_role(q_nv, q_role)
        c_nv_norm = _normalize_1x2_nv_by_role(c_nv, c_role)
        if q_nv_norm and c_nv_norm:
            nv_scores = []
            for i in range(3):
                nv_scores.append(_clamp(1.0 - abs(q_nv_norm[i] - c_nv_norm[i]) / 0.15))
            scores.append(sum(nv_scores) / len(nv_scores))

        q_amounts = q_m.get("closing_amounts") or {}
        c_amounts = c_m.get("closing_amounts") or {}
        if q_amounts and c_amounts:
            q_norm = _normalize_1x2_by_role(q_amounts, q_role)
            c_norm = _normalize_1x2_by_role(c_amounts, c_role)
            q_total = sum(v for v in q_norm.values() if v is not None) or 1
            c_total = sum(v for v in c_norm.values() if v is not None) or 1
            pct_scores = []
            abs_scores = []
            for role_key in ["favorite", "draw", "underdog"]:
                q_pct = (q_norm.get(role_key) or 0) / q_total
                c_pct = (c_norm.get(role_key) or 0) / c_total
                pct_scores.append(_clamp(1.0 - abs(q_pct - c_pct) / 0.20))
                abs_scores.append(_amount_ratio_score(q_norm.get(role_key), c_norm.get(role_key)))
            if pct_scores:
                pct_avg = sum(pct_scores) / len(pct_scores)
                abs_avg = sum(abs_scores) / len(abs_scores) if abs_scores else 0.0
                scores.append(pct_avg * 0.5 + abs_avg * 0.5)
    else:
        q_nv = q_m.get("closing_nv")
        c_nv = c_m.get("closing_nv")
        if q_nv and c_nv and len(q_nv) == len(c_nv):
            nv_scores = []
            for i in range(len(q_nv)):
                nv_scores.append(_clamp(1.0 - abs(q_nv[i] - c_nv[i]) / 0.15))
            scores.append(sum(nv_scores) / len(nv_scores))

        q_amounts = q_m.get("closing_amounts") or {}
        c_amounts = c_m.get("closing_amounts") or {}
        if q_amounts and c_amounts:
            q_total = sum(v for v in q_amounts.values() if v is not None) or 1
            c_total = sum(v for v in c_amounts.values() if v is not None) or 1
            pct_scores = []
            abs_scores = []
            for key in sel_keys:
                q_pct = (q_amounts.get(key) or 0) / q_total
                c_pct = (c_amounts.get(key) or 0) / c_total
                pct_scores.append(_clamp(1.0 - abs(q_pct - c_pct) / 0.20))
                abs_scores.append(_amount_ratio_score(q_amounts.get(key), c_amounts.get(key)))
            if pct_scores:
                pct_avg = sum(pct_scores) / len(pct_scores)
                abs_avg = sum(abs_scores) / len(abs_scores) if abs_scores else 0.0
                scores.append(pct_avg * 0.5 + abs_avg * 0.5)

    if not scores:
        return 0.0
    return round(sum(scores) / len(scores), 4)


def passes_hard_filter(query, candidate, market_filter=None):
    hf = HARD_FILTER

    if market_filter and market_filter != "all":
        getter, sel_keys = _get_primary_market_getter(market_filter)
        if getter:
            q_m = getter(query)
            c_m = getter(candidate)
            if not q_m or not c_m:
                return False
            q_open = q_m.get("opening_odds") or {}
            c_open = c_m.get("opening_odds") or {}
            if not q_open or not c_open:
                return False
            for key in sel_keys:
                qv = q_open.get(key)
                cv = c_open.get(key)
                if qv is not None and cv is not None:
                    if abs(qv - cv) > hf["odds_1x2_max_diff"]:
                        return False
    else:
        q_m = _get_1x2_market(query)
        c_m = _get_1x2_market(candidate)
        if not q_m or not c_m:
            return False
        q_open = q_m.get("opening_odds") or {}
        c_open = c_m.get("opening_odds") or {}
        if not q_open or not c_open:
            return False
        for key in ["home", "draw", "away"]:
            qv = q_open.get(key)
            cv = c_open.get(key)
            if qv is not None and cv is not None:
                if abs(qv - cv) > hf["odds_1x2_max_diff"]:
                    return False

    q_vol = query.get("total_volume") or 0
    c_vol = candidate.get("total_volume") or 0
    if q_vol > 0 and c_vol > 0:
        ratio = max(q_vol, c_vol) / max(min(q_vol, c_vol), 1)
        if ratio > hf["volume_ratio_max"]:
            return False
    elif c_vol == 0:
        return False

    q_tier = query.get("league_tier") or _get_league_tier(query.get("league", ""))
    c_tier = candidate.get("league_tier") or _get_league_tier(candidate.get("league", ""))
    if abs(q_tier - c_tier) > hf["league_tier_max_diff"]:
        return False

    c_dq = candidate.get("data_quality_score", 0)
    if c_dq is not None and c_dq < hf["min_data_quality"]:
        return False

    return True


def compute_similarity(query, candidate, market_filter=None):
    block_scores = {}

    if market_filter and market_filter != "all":
        getter, sel_keys = _get_primary_market_getter(market_filter)
        if getter:
            q_m = getter(query)
            c_m = getter(candidate)
            odds_result = _compute_odds_block(q_m, c_m, sel_keys)
            block_map = {"1x2": "odds_1x2", "ou25": "odds_ou", "kg": "odds_kg"}
            block_name = block_map.get(market_filter, "odds_" + market_filter)
            drift_block_name = block_name + "_drift"
            if odds_result is not None:
                block_scores[block_name] = odds_result["odds_only"]
                block_scores[block_name + "_detail"] = odds_result
                block_scores[drift_block_name] = odds_result["drift_only"]
            else:
                block_scores[block_name] = 0.0
                block_scores[drift_block_name] = 0.0

            is_1x2 = (market_filter == "1x2")
            money_score = _compute_single_market_money(query, candidate, getter, sel_keys, is_1x2=is_1x2)
            block_scores["money_distribution"] = money_score

            q_vol = query.get("total_volume") or 0
            c_vol = candidate.get("total_volume") or 0
            q_bucket = query.get("volume_bucket") or _get_volume_bucket(q_vol)
            c_bucket = candidate.get("volume_bucket") or _get_volume_bucket(c_vol)
            vol_sim = _compute_volume_similarity(q_vol, c_vol, q_bucket, c_bucket)
            block_scores["total_volume"] = vol_sim

            total = (block_scores[block_name] * 0.30 +
                     block_scores[drift_block_name] * 0.30 +
                     block_scores["money_distribution"] * 0.30 +
                     block_scores["total_volume"] * 0.10)

            return {
                "total_score": round(_clamp(total), 4),
                "block_scores": block_scores,
            }

    bw = BLOCK_WEIGHTS

    q_1x2 = _get_1x2_market(query)
    c_1x2 = _get_1x2_market(candidate)
    odds_1x2_result = _compute_odds_block(q_1x2, c_1x2, ["home", "draw", "away"])
    if odds_1x2_result is not None:
        block_scores["odds_1x2"] = odds_1x2_result["score"]
        block_scores["odds_1x2_detail"] = odds_1x2_result
    else:
        block_scores["odds_1x2"] = 0.0

    q_ou = _get_ou_market(query)
    c_ou = _get_ou_market(candidate)
    odds_ou_result = _compute_odds_block(q_ou, c_ou, ["over", "under"])
    if odds_ou_result is not None:
        block_scores["odds_ou"] = odds_ou_result["score"]
        block_scores["odds_ou_detail"] = odds_ou_result
    else:
        block_scores["odds_ou"] = 0.0

    q_kg = _get_kg_market(query)
    c_kg = _get_kg_market(candidate)
    odds_kg_result = _compute_odds_block(q_kg, c_kg, ["yes", "no"])
    if odds_kg_result is None:
        for key in ["moneyway_btts", "dropping_btts"]:
            qm = query.get("markets", {}).get(key)
            cm = candidate.get("markets", {}).get(key)
            if qm and cm and qm.get("opening_odds") and cm.get("opening_odds"):
                odds_kg_result = _compute_odds_block(qm, cm, ["oddsyes", "oddsno"])
                break
    if odds_kg_result is not None:
        block_scores["odds_kg"] = odds_kg_result["score"]
        block_scores["odds_kg_detail"] = odds_kg_result
    else:
        block_scores["odds_kg"] = 0.0

    money_dist = _compute_money_distribution(query, candidate)
    block_scores["money_distribution"] = money_dist

    q_vol = query.get("total_volume") or 0
    c_vol = candidate.get("total_volume") or 0
    q_bucket = query.get("volume_bucket") or _get_volume_bucket(q_vol)
    c_bucket = candidate.get("volume_bucket") or _get_volume_bucket(c_vol)
    vol_sim = _compute_volume_similarity(q_vol, c_vol, q_bucket, c_bucket)
    block_scores["total_volume"] = vol_sim

    total = 0.0
    weight_sum = 0.0
    for block_name, score in block_scores.items():
        if block_name.endswith("_detail"):
            continue
        w = bw.get(block_name, 0)
        total += score * w
        weight_sum += w

    if weight_sum > 0:
        total /= weight_sum

    return {
        "total_score": round(_clamp(total), 4),
        "block_scores": block_scores,
    }


def _is_finished(candidate):
    kickoff = candidate.get("kickoff")
    if not kickoff:
        return False
    try:
        if isinstance(kickoff, str):
            kickoff = kickoff.replace("Z", "+00:00")
            from smartxflow_similarity.utils import parse_datetime
            kickoff = parse_datetime(kickoff)
        if kickoff is None:
            return False
        now = datetime.now(timezone.utc)
        return (now - kickoff) > timedelta(hours=3)
    except Exception:
        return False


def find_similar_matches(query_entry, store_entries, top_n=None, market_filter=None):
    if top_n is None:
        top_n = TOP_SIMILAR_COUNT

    query_hash = query_entry.get("match_id_hash", "")
    results = []

    for candidate in store_entries:
        if candidate.get("match_id_hash") == query_hash:
            continue
        if not _is_finished(candidate):
            continue
        if not passes_hard_filter(query_entry, candidate, market_filter=market_filter):
            continue
        sim = compute_similarity(query_entry, candidate, market_filter=market_filter)
        if sim["total_score"] > 0:
            results.append({
                "candidate": candidate,
                "similarity": sim,
            })

    results.sort(key=lambda x: x["similarity"]["total_score"], reverse=True)
    return results[:top_n]
