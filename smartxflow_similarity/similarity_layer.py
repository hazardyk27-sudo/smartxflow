import math

from smartxflow_similarity.config import (
    HARD_FILTER, SIMILARITY_BLOCK_WEIGHTS,
    MARKET_SHAPE_SUB_WEIGHTS, FLOW_SHAPE_SUB_WEIGHTS,
    PRICE_REACTION_SUB_WEIGHTS, CROSS_MARKET_DRAW_SUB_WEIGHTS,
    CONTEXT_SUB_WEIGHTS, PHASE_WEIGHTS, PHASE_NAMES,
    MARKET_WEIGHTS_DEFAULT, MARKET_WEIGHTS_DRAW_REGIME,
    TOP_SIMILAR_COUNT,
)
from smartxflow_similarity.utils import safe_div, clamp, normalize_0_1


def passes_hard_filter(query_entry, candidate_entry):
    hf = HARD_FILTER

    q_1x2 = _get_primary_1x2(query_entry)
    c_1x2 = _get_primary_1x2(candidate_entry)
    if q_1x2 and c_1x2:
        for key in q_1x2:
            q_val = q_1x2.get(key)
            c_val = c_1x2.get(key)
            if q_val is not None and c_val is not None:
                if abs(q_val - c_val) > hf["odds_band_tolerance"]:
                    return False

    q_tier = query_entry.get("league_tier", 4)
    c_tier = candidate_entry.get("league_tier", 4)
    if abs(q_tier - c_tier) > hf["league_tier_max_diff"]:
        return False

    q_vb = query_entry.get("volume_bucket", 1)
    c_vb = candidate_entry.get("volume_bucket", 1)
    if abs(q_vb - c_vb) > hf["volume_bucket_max_diff"]:
        return False

    c_dq = candidate_entry.get("data_quality_score", 0)
    if c_dq < hf["min_data_quality"]:
        return False

    q_dur = query_entry.get("market_duration_hours", 0)
    c_dur = candidate_entry.get("market_duration_hours", 0)
    if abs(q_dur - c_dur) > hf["market_duration_max_diff"]:
        return False

    return True


def _get_primary_1x2(entry):
    markets = entry.get("markets", {})
    for key in ["moneyway_1x2", "dropping_1x2"]:
        m = markets.get(key)
        if m and m.get("opening_odds"):
            return m["opening_odds"]
    return None


def _cosine_similarity(vec_a, vec_b):
    if not vec_a or not vec_b:
        return 0.0
    dot = sum(a * b for a, b in zip(vec_a, vec_b))
    mag_a = math.sqrt(sum(a * a for a in vec_a))
    mag_b = math.sqrt(sum(b * b for b in vec_b))
    if mag_a == 0 or mag_b == 0:
        return 0.0
    return dot / (mag_a * mag_b)


def _abs_diff_score(val_a, val_b, max_diff=1.0):
    if val_a is None or val_b is None:
        return 0.0
    diff = abs(val_a - val_b)
    return clamp(1.0 - diff / max_diff)


def _list_diff_score(list_a, list_b, max_diff=0.5):
    if not list_a or not list_b:
        return 0.0
    n = min(len(list_a), len(list_b))
    total = 0.0
    for i in range(n):
        a = list_a[i] if list_a[i] is not None else 0
        b = list_b[i] if list_b[i] is not None else 0
        total += _abs_diff_score(a, b, max_diff)
    return total / n


def _get_market_keys(entry):
    markets = entry.get("markets", {})
    keys = []
    for k in ["moneyway_1x2", "dropping_1x2"]:
        if k in markets and markets[k]:
            keys.append(("1x2", k))
            break
    for k in ["moneyway_ou25", "dropping_ou25"]:
        if k in markets and markets[k]:
            keys.append(("ou25", k))
            break
    for k in ["moneyway_btts", "dropping_btts"]:
        if k in markets and markets[k]:
            keys.append(("btts", k))
            break
    return keys


def compute_market_shape_score(q_market, c_market):
    sw = MARKET_SHAPE_SUB_WEIGHTS
    score = 0.0

    opening_score = _list_diff_score(
        list((q_market.get("opening_nv") or {}).values()) if isinstance(q_market.get("opening_nv"), dict) else (q_market.get("opening_nv") or []),
        list((c_market.get("opening_nv") or {}).values()) if isinstance(c_market.get("opening_nv"), dict) else (c_market.get("opening_nv") or []),
        max_diff=0.3,
    )
    score += opening_score * sw["opening_odds_profile"]

    closing_score = _list_diff_score(
        list((q_market.get("closing_nv") or {}).values()) if isinstance(q_market.get("closing_nv"), dict) else (q_market.get("closing_nv") or []),
        list((c_market.get("closing_nv") or {}).values()) if isinstance(c_market.get("closing_nv"), dict) else (c_market.get("closing_nv") or []),
        max_diff=0.3,
    )
    score += closing_score * sw["closing_odds_profile"]

    q_nv_drifts = _extract_nv_drifts(q_market)
    c_nv_drifts = _extract_nv_drifts(c_market)
    nv_drift_score = _list_diff_score(q_nv_drifts, c_nv_drifts, max_diff=0.15)
    score += nv_drift_score * sw["nv_drift_pattern"]

    q_fav = _favorite_shape(q_market)
    c_fav = _favorite_shape(c_market)
    fav_score = _abs_diff_score(q_fav, c_fav, max_diff=0.3)
    score += fav_score * sw["favorite_shape"]

    q_bal = _balance_index(q_market)
    c_bal = _balance_index(c_market)
    bal_score = _abs_diff_score(q_bal, c_bal, max_diff=0.5)
    score += bal_score * sw["balance_index"]

    return score


def _extract_nv_drifts(market):
    drifts = []
    opening = market.get("opening_nv")
    closing = market.get("closing_nv")
    if opening and closing:
        for i in range(min(len(opening), len(closing))):
            o = opening[i] if isinstance(opening, list) else list(opening.values())[i] if isinstance(opening, dict) else None
            c = closing[i] if isinstance(closing, list) else list(closing.values())[i] if isinstance(closing, dict) else None
            if o is not None and c is not None:
                drifts.append(c - o)
    return drifts


def _favorite_shape(market):
    nv = market.get("closing_nv")
    if not nv:
        return 0.5
    vals = list(nv.values()) if isinstance(nv, dict) else list(nv)
    if not vals:
        return 0.5
    return max(vals)


def _balance_index(market):
    nv = market.get("closing_nv")
    if not nv:
        return 0.5
    vals = list(nv.values()) if isinstance(nv, dict) else list(nv)
    if len(vals) < 2:
        return 0.5
    return 1.0 - (max(vals) - min(vals))


def compute_flow_shape_score(q_market, c_market, q_entry, c_entry):
    sw = FLOW_SHAPE_SUB_WEIGHTS
    score = 0.0

    q_vol = q_entry.get("total_volume") or 0
    c_vol = c_entry.get("total_volume") or 0
    max_vol = max(q_vol, c_vol, 1)
    vol_score = _abs_diff_score(q_vol / max_vol, c_vol / max_vol, max_diff=0.5)
    score += vol_score * sw["total_volume_normalized"]

    q_ts = (q_market.get("timing_signature") or {})
    c_ts = (c_market.get("timing_signature") or {})
    dom_match = 1.0 if q_ts.get("dominant_timing") == c_ts.get("dominant_timing") else 0.3
    score += dom_match * sw["dom_pattern"]

    q_liq = _phase_liquidity_vector(q_market)
    c_liq = _phase_liquidity_vector(c_market)
    liq_score = _cosine_similarity(q_liq, c_liq)
    score += max(liq_score, 0) * sw["phase_liquidity"]

    q_late = q_ts.get("late_pressure_ratio", 0.33)
    c_late = c_ts.get("late_pressure_ratio", 0.33)
    late_score = _abs_diff_score(q_late, c_late, max_diff=0.4)
    score += late_score * sw["late_money_ratio"]

    q_early = q_ts.get("early_pressure_ratio", 0.33)
    c_early = c_ts.get("early_pressure_ratio", 0.33)
    night_score = _abs_diff_score(q_early, c_early, max_diff=0.4)
    score += night_score * sw["night_money_ratio"]

    return score


def _phase_liquidity_vector(market):
    vec = []
    pf = market.get("phase_features") or {}
    for phase in PHASE_NAMES:
        p = pf.get(phase, {})
        count = p.get("snapshot_count", 0)
        vec.append(float(count))
    return vec


def compute_price_reaction_score(q_market, c_market):
    sw = PRICE_REACTION_SUB_WEIGHTS
    score = 0.0

    q_drifts = _weighted_phase_drifts(q_market)
    c_drifts = _weighted_phase_drifts(c_market)
    drift_score = _cosine_similarity(q_drifts, c_drifts)
    score += max(drift_score, 0) * sw["phase_odds_drift"]

    q_pre = q_market.get("overall_price_response_efficiency") or {}
    c_pre = c_market.get("overall_price_response_efficiency") or {}
    pre_vals_q = list(q_pre.values())
    pre_vals_c = list(c_pre.values())
    pre_score = _list_diff_score(pre_vals_q, pre_vals_c, max_diff=50.0)
    score += pre_score * sw["response_efficiency"]

    q_freeze = _reaction_profile(q_market, "FREEZE")
    c_freeze = _reaction_profile(c_market, "FREEZE")
    freeze_score = _abs_diff_score(q_freeze, c_freeze, max_diff=0.5)
    score += freeze_score * sw["freeze_profile"]

    q_rlm = _reaction_profile(q_market, "TRUE_RLM")
    c_rlm = _reaction_profile(c_market, "TRUE_RLM")
    rlm_score = _abs_diff_score(q_rlm, c_rlm, max_diff=0.3)
    score += rlm_score * sw["rlm_profile"]

    q_closing = _closing_behavior(q_market)
    c_closing = _closing_behavior(c_market)
    close_score = _list_diff_score(q_closing, c_closing, max_diff=0.2)
    score += close_score * sw["closing_behavior"]

    return score


def _weighted_phase_drifts(market):
    vec = []
    pf = market.get("phase_features") or {}
    for phase in PHASE_NAMES:
        p = pf.get(phase, {})
        drift = p.get("odds_0_drift", 0) or 0
        w = PHASE_WEIGHTS.get(phase, 0.05)
        vec.append(drift * w)
    return vec


def _reaction_profile(market, reaction_type):
    reactions = market.get("phase_reactions") or {}
    total = 0
    count = 0
    for phase, sel_reactions in reactions.items():
        for sel, r in sel_reactions.items():
            count += 1
            if r == reaction_type:
                total += 1
    return safe_div(total, count)


def _closing_behavior(market):
    pf = market.get("phase_features") or {}
    p1 = pf.get("P1_0to1h", {})
    vals = []
    for i in range(4):
        d = p1.get(f"odds_{i}_drift")
        if d is not None:
            vals.append(d)
    return vals if vals else [0.0]


def compute_cross_market_draw_score(q_entry, c_entry):
    sw = CROSS_MARKET_DRAW_SUB_WEIGHTS
    score = 0.0

    q_cm = q_entry.get("cross_market") or {}
    c_cm = c_entry.get("cross_market") or {}

    ou_score = _abs_diff_score(
        q_cm.get("directional_harmony_score", 0),
        c_cm.get("directional_harmony_score", 0),
        max_diff=1.0,
    )
    score += ou_score * sw["ou_support"]

    btts_q = 1.0 if q_cm.get("low_event_pattern") else 0.0
    btts_c = 1.0 if c_cm.get("low_event_pattern") else 0.0
    btts_score = _abs_diff_score(btts_q, btts_c, max_diff=1.0)
    score += btts_score * sw["btts_support"]

    q_dr = q_entry.get("draw_regime") or {}
    c_dr = c_entry.get("draw_regime") or {}
    dr_score = _abs_diff_score(
        q_dr.get("draw_regime_score", 0),
        c_dr.get("draw_regime_score", 0),
        max_diff=0.5,
    )
    score += dr_score * sw["draw_regime"]

    harmony_score = _abs_diff_score(
        q_cm.get("cross_market_harmony", 0),
        c_cm.get("cross_market_harmony", 0),
        max_diff=1.0,
    )
    score += harmony_score * sw["harmony_score"]

    return score


def compute_context_score(q_entry, c_entry):
    sw = CONTEXT_SUB_WEIGHTS
    score = 0.0

    q_ctx = q_entry.get("context") or {}
    c_ctx = c_entry.get("context") or {}

    tier_score = _abs_diff_score(
        q_entry.get("league_tier", 4),
        c_entry.get("league_tier", 4),
        max_diff=4.0,
    )
    score += tier_score * sw["league_tier"]

    vb_score = _abs_diff_score(
        q_entry.get("volume_bucket", 1),
        c_entry.get("volume_bucket", 1),
        max_diff=5.0,
    )
    score += vb_score * sw["volume_bucket"]

    dq_score = _abs_diff_score(
        q_entry.get("data_quality_score", 0.5),
        c_entry.get("data_quality_score", 0.5),
        max_diff=1.0,
    )
    score += dq_score * sw["data_quality"]

    dur_score = _abs_diff_score(
        q_entry.get("market_duration_hours", 12),
        c_entry.get("market_duration_hours", 12),
        max_diff=48.0,
    )
    score += dur_score * sw["market_duration"]

    return score


def compute_similarity(query_entry, candidate_entry):
    bw = SIMILARITY_BLOCK_WEIGHTS

    q_is_draw = (query_entry.get("draw_regime") or {}).get("is_draw_regime", False)
    market_weights = MARKET_WEIGHTS_DRAW_REGIME if q_is_draw else MARKET_WEIGHTS_DEFAULT

    q_markets = _get_market_keys(query_entry)
    c_markets = _get_market_keys(candidate_entry)

    common_market_types = set()
    q_market_map = {}
    c_market_map = {}
    for mtype, mkey in q_markets:
        q_market_map[mtype] = query_entry.get("markets", {}).get(mkey, {})
    for mtype, mkey in c_markets:
        c_market_map[mtype] = candidate_entry.get("markets", {}).get(mkey, {})
    for mtype in q_market_map:
        if mtype in c_market_map:
            common_market_types.add(mtype)

    if not common_market_types:
        return {"total_score": 0.0, "block_scores": {}, "common_markets": []}

    market_shape_total = 0.0
    flow_shape_total = 0.0
    price_reaction_total = 0.0
    weight_sum = 0.0

    block_details = {}

    for mtype in common_market_types:
        w = market_weights.get(mtype, 0.25)
        qm = q_market_map[mtype]
        cm = c_market_map[mtype]

        ms = compute_market_shape_score(qm, cm)
        fs = compute_flow_shape_score(qm, cm, query_entry, candidate_entry)
        pr = compute_price_reaction_score(qm, cm)

        market_shape_total += ms * w
        flow_shape_total += fs * w
        price_reaction_total += pr * w
        weight_sum += w

        block_details[mtype] = {
            "market_shape": round(ms, 4),
            "flow_shape": round(fs, 4),
            "price_reaction": round(pr, 4),
        }

    if weight_sum > 0:
        market_shape_total /= weight_sum
        flow_shape_total /= weight_sum
        price_reaction_total /= weight_sum

    cross_market_draw_score = compute_cross_market_draw_score(query_entry, candidate_entry)
    context_score = compute_context_score(query_entry, candidate_entry)

    block_scores = {
        "market_shape": round(market_shape_total, 4),
        "flow_shape": round(flow_shape_total, 4),
        "price_reaction": round(price_reaction_total, 4),
        "cross_market_draw": round(cross_market_draw_score, 4),
        "context": round(context_score, 4),
    }

    total = 0.0
    for block_name, block_score in block_scores.items():
        total += block_score * bw.get(block_name, 0)

    phase_coverage_q = query_entry.get("phase_coverage_score", 1.0) or 1.0
    phase_coverage_c = candidate_entry.get("phase_coverage_score", 1.0) or 1.0
    coverage_factor = min(phase_coverage_q, phase_coverage_c)
    total *= (0.7 + 0.3 * coverage_factor)

    return {
        "total_score": round(clamp(total), 4),
        "block_scores": block_scores,
        "block_details": block_details,
        "common_markets": sorted(common_market_types),
        "coverage_factor": round(coverage_factor, 4),
    }


def find_similar_matches(query_entry, store_entries, top_n=None):
    if top_n is None:
        top_n = TOP_SIMILAR_COUNT

    query_hash = query_entry.get("match_id_hash", "")
    results = []

    for candidate in store_entries:
        if candidate.get("match_id_hash") == query_hash:
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
