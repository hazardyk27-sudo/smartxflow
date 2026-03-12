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


def _odds_diff_score(a, b, max_diff=2.0):
    if a is None or b is None:
        return 0.0
    return _clamp(1.0 - abs(a - b) / max_diff)


def _drift_pct(opening, closing):
    if opening is None or closing is None or opening == 0:
        return 0.0
    return (closing - opening) / opening


def _drift_diff_score(drift_a, drift_b, max_diff=0.30):
    return _clamp(1.0 - abs(drift_a - drift_b) / max_diff)


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
            open_scores.append(_odds_diff_score(qo, co, max_diff=1.5))
        if qc is not None and cc is not None:
            close_scores.append(_odds_diff_score(qc, cc, max_diff=1.5))

        q_drift = _drift_pct(qo, qc)
        c_drift = _drift_pct(co, cc)
        drift_scores.append(_drift_diff_score(q_drift, c_drift, max_diff=0.25))

    if not open_scores and not close_scores:
        return None

    avg_open = sum(open_scores) / len(open_scores) if open_scores else 0.0
    avg_close = sum(close_scores) / len(close_scores) if close_scores else 0.0
    avg_drift = sum(drift_scores) / len(drift_scores) if drift_scores else 0.0

    return round((avg_open * 0.30 + avg_close * 0.30 + avg_drift * 0.40), 4)


def _compute_money_distribution(q_entry, c_entry):
    scores = []

    for get_market, sel_keys in [
        (_get_1x2_market, ["home", "draw", "away"]),
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
            for key in sel_keys:
                q_pct = (q_amounts.get(key) or 0) / q_total
                c_pct = (c_amounts.get(key) or 0) / c_total
                pct_scores.append(_clamp(1.0 - abs(q_pct - c_pct) / 0.20))
            if pct_scores:
                scores.append(sum(pct_scores) / len(pct_scores))

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


def passes_hard_filter(query, candidate):
    hf = HARD_FILTER

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


def compute_similarity(query, candidate):
    bw = BLOCK_WEIGHTS
    block_scores = {}

    q_1x2 = _get_1x2_market(query)
    c_1x2 = _get_1x2_market(candidate)
    odds_1x2 = _compute_odds_block(q_1x2, c_1x2, ["home", "draw", "away"])
    block_scores["odds_1x2"] = odds_1x2 if odds_1x2 is not None else 0.0

    q_ou = _get_ou_market(query)
    c_ou = _get_ou_market(candidate)
    odds_ou = _compute_odds_block(q_ou, c_ou, ["over", "under"])
    block_scores["odds_ou"] = odds_ou if odds_ou is not None else 0.0

    q_kg = _get_kg_market(query)
    c_kg = _get_kg_market(candidate)
    odds_kg = _compute_odds_block(q_kg, c_kg, ["yes", "no"])
    if odds_kg is None:
        for key in ["moneyway_btts", "dropping_btts"]:
            qm = query.get("markets", {}).get(key)
            cm = candidate.get("markets", {}).get(key)
            if qm and cm and qm.get("opening_odds") and cm.get("opening_odds"):
                odds_kg = _compute_odds_block(qm, cm, ["oddsyes", "oddsno"])
                break
    block_scores["odds_kg"] = odds_kg if odds_kg is not None else 0.0

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


def find_similar_matches(query_entry, store_entries, top_n=None):
    if top_n is None:
        top_n = TOP_SIMILAR_COUNT

    query_hash = query_entry.get("match_id_hash", "")
    results = []

    for candidate in store_entries:
        if candidate.get("match_id_hash") == query_hash:
            continue
        if not _is_finished(candidate):
            continue
        if not passes_hard_filter(query_entry, candidate):
            continue
        sim = compute_similarity(query_entry, candidate)
        if sim["total_score"] > 0:
            results.append({
                "candidate": candidate,
                "similarity": sim,
            })

    results.sort(key=lambda x: x["similarity"]["total_score"], reverse=True)
    return results[:top_n]
