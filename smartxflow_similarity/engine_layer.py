from smartxflow_similarity.config import (
    SIMILARITY_BLOCK_WEIGHTS, PHASE_NAMES, TOP_SIMILAR_COUNT,
)
from smartxflow_similarity.similarity_layer import find_similar_matches
from smartxflow_similarity.utils import safe_div


BLOCK_LABELS = {
    "market_shape": "Market Shape (odds profili, NV drift, favori yapısı)",
    "flow_shape": "Flow Shape (hacim akışı, faz likiditesi, geç para)",
    "price_reaction": "Price Reaction (oran tepkisi, freeze/RLM profili)",
    "cross_market_draw": "Cross-Market & Draw (çapraz market uyumu, draw rejimi)",
    "context": "Context (lig seviyesi, hacim, veri kalitesi)",
}

PATTERN_TEMPLATES = {
    "late_money_favorite": "Son saatlerde güçlü para akışıyla desteklenen favori",
    "early_established": "Erken saatlerde yönü belirlenmiş, geç saatlerde sabit kalan maç",
    "reverse_line_movement": "Paraya rağmen ters yönde oran hareketi gösteren maç",
    "frozen_market": "Yüksek hacme rağmen oranların sabit kaldığı maç",
    "draw_regime": "Düşük gol beklentisi, beraberlik baskısı altında dengeli maç",
    "cross_pressure": "Farklı marketlerden çelişkili sinyaller alan maç",
    "balanced_neutral": "Belirgin bir yön oluşmamış, dengeli market yapısı",
    "absorbed_pressure": "Para baskısı absorbe edilmiş, piyasa direnci gösteren maç",
}


def compute_result_distribution(similar_matches):
    if not similar_matches:
        return {
            "simple": {"home": 0, "draw": 0, "away": 0, "total": 0},
            "weighted": {"home": 0, "draw": 0, "away": 0},
        }

    home_count = 0
    draw_count = 0
    away_count = 0
    total_with_result = 0

    weighted_home = 0.0
    weighted_draw = 0.0
    weighted_away = 0.0
    weight_sum = 0.0

    for match in similar_matches:
        result = match["candidate"].get("result")
        sim_score = match["similarity"]["total_score"]

        if result is None:
            continue

        result_str = str(result).strip().upper()
        total_with_result += 1

        if result_str in ("HOME", "1", "H"):
            home_count += 1
            weighted_home += sim_score
        elif result_str in ("DRAW", "X", "D"):
            draw_count += 1
            weighted_draw += sim_score
        elif result_str in ("AWAY", "2", "A"):
            away_count += 1
            weighted_away += sim_score

        weight_sum += sim_score

    simple = {
        "home": round(safe_div(home_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
        "draw": round(safe_div(draw_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
        "away": round(safe_div(away_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
        "total": total_with_result,
    }

    weighted = {"home": 0, "draw": 0, "away": 0}
    if weight_sum > 0:
        weighted = {
            "home": round(weighted_home / weight_sum * 100, 1),
            "draw": round(weighted_draw / weight_sum * 100, 1),
            "away": round(weighted_away / weight_sum * 100, 1),
        }

    return {"simple": simple, "weighted": weighted}


def explain_single_match(query_entry, match_result):
    candidate = match_result["candidate"]
    sim = match_result["similarity"]
    block_scores = sim.get("block_scores", {})

    sorted_blocks = sorted(block_scores.items(), key=lambda x: x[1], reverse=True)
    top_3_similar = sorted_blocks[:3]
    bottom_2_divergent = sorted_blocks[-2:] if len(sorted_blocks) >= 2 else sorted_blocks

    q_markets = query_entry.get("markets", {})
    c_markets = candidate.get("markets", {})

    closest_phases = []
    farthest_phases = []

    common_market = None
    for mk in ["moneyway_1x2", "dropping_1x2"]:
        if mk in q_markets and q_markets[mk] and mk in c_markets and c_markets[mk]:
            common_market = mk
            break

    if common_market:
        q_pf = (q_markets[common_market].get("phase_features") or {})
        c_pf = (c_markets[common_market].get("phase_features") or {})
        phase_diffs = []
        for phase in PHASE_NAMES:
            q_drift = (q_pf.get(phase) or {}).get("odds_0_drift", 0) or 0
            c_drift = (c_pf.get(phase) or {}).get("odds_0_drift", 0) or 0
            diff = abs(q_drift - c_drift)
            phase_diffs.append((phase, diff))

        phase_diffs.sort(key=lambda x: x[1])
        closest_phases = [p[0] for p in phase_diffs[:3]]
        farthest_phases = [p[0] for p in phase_diffs[-2:]]

    pattern_label = _determine_pattern_label(candidate)

    return {
        "match_name": candidate.get("match_name", ""),
        "league": candidate.get("league", ""),
        "result": candidate.get("result"),
        "similarity_score": sim["total_score"],
        "top_3_similar_blocks": [
            {"block": b[0], "score": b[1], "label": BLOCK_LABELS.get(b[0], b[0])}
            for b in top_3_similar
        ],
        "top_2_divergent_blocks": [
            {"block": b[0], "score": b[1], "label": BLOCK_LABELS.get(b[0], b[0])}
            for b in bottom_2_divergent
        ],
        "closest_phases": closest_phases,
        "farthest_phases": farthest_phases,
        "pattern_label": pattern_label,
        "block_scores": block_scores,
    }


def _determine_pattern_label(entry):
    markets = entry.get("markets", {})
    m1x2 = markets.get("moneyway_1x2") or markets.get("dropping_1x2") or {}

    ts = m1x2.get("timing_signature") or {}
    dom_timing = ts.get("dominant_timing", "balanced")

    has_lr = m1x2.get("has_late_reversal", False)
    has_ps = m1x2.get("has_phase_shift", False)

    dr = entry.get("draw_regime") or {}
    is_draw = dr.get("is_draw_regime", False)

    cm = entry.get("cross_market") or {}
    contradiction = cm.get("cross_market_contradiction", 0)

    reactions = m1x2.get("phase_reactions") or {}
    freeze_count = 0
    rlm_count = 0
    absorbed_count = 0
    total_reactions = 0
    for phase, sel_r in reactions.items():
        for sel, r in sel_r.items():
            total_reactions += 1
            if r == "FREEZE":
                freeze_count += 1
            elif r == "TRUE_RLM":
                rlm_count += 1
            elif r == "ABSORBED_PRESSURE":
                absorbed_count += 1

    if is_draw:
        return PATTERN_TEMPLATES["draw_regime"]
    if has_lr:
        return PATTERN_TEMPLATES["reverse_line_movement"]
    if dom_timing == "late_driven":
        return PATTERN_TEMPLATES["late_money_favorite"]
    if dom_timing == "early_driven":
        return PATTERN_TEMPLATES["early_established"]
    if total_reactions > 0 and freeze_count / max(total_reactions, 1) > 0.3:
        return PATTERN_TEMPLATES["frozen_market"]
    if total_reactions > 0 and absorbed_count / max(total_reactions, 1) > 0.3:
        return PATTERN_TEMPLATES["absorbed_pressure"]
    if total_reactions > 0 and rlm_count / max(total_reactions, 1) > 0.2:
        return PATTERN_TEMPLATES["reverse_line_movement"]
    if contradiction > 0.5:
        return PATTERN_TEMPLATES["cross_pressure"]
    return PATTERN_TEMPLATES["balanced_neutral"]


def compute_overall_explainability(query_entry, similar_matches, explanations):
    if not explanations:
        return {
            "top_3_common_traits": [],
            "top_2_risk_traits": [],
            "main_pattern_label": "Yeterli veri yok",
            "top_shared_patterns": [],
            "top_mismatch_patterns": [],
        }

    block_totals = {}
    for exp in explanations:
        for b in exp.get("top_3_similar_blocks", []):
            name = b["block"]
            block_totals[name] = block_totals.get(name, 0) + b["score"]

    sorted_blocks = sorted(block_totals.items(), key=lambda x: x[1], reverse=True)

    top_3_common = []
    for b_name, b_total in sorted_blocks[:3]:
        avg = b_total / len(explanations)
        top_3_common.append({
            "trait": BLOCK_LABELS.get(b_name, b_name),
            "avg_score": round(avg, 4),
        })

    divergent_totals = {}
    for exp in explanations:
        for b in exp.get("top_2_divergent_blocks", []):
            name = b["block"]
            divergent_totals[name] = divergent_totals.get(name, 0) + (1.0 - b["score"])

    sorted_div = sorted(divergent_totals.items(), key=lambda x: x[1], reverse=True)
    top_2_risk = []
    for b_name, b_total in sorted_div[:2]:
        avg = b_total / len(explanations)
        top_2_risk.append({
            "risk": BLOCK_LABELS.get(b_name, b_name),
            "avg_divergence": round(avg, 4),
        })

    pattern_counts = {}
    for exp in explanations:
        pl = exp.get("pattern_label", "")
        pattern_counts[pl] = pattern_counts.get(pl, 0) + 1

    sorted_patterns = sorted(pattern_counts.items(), key=lambda x: x[1], reverse=True)
    main_pattern = sorted_patterns[0][0] if sorted_patterns else "Belirgin pattern yok"
    top_shared = [{"pattern": p, "count": c} for p, c in sorted_patterns[:3]]

    q_dr = query_entry.get("draw_regime", {})
    draw_risk = q_dr.get("is_draw_regime", False)

    q_cm = query_entry.get("cross_market", {})
    market_contradiction = q_cm.get("cross_market_contradiction", 0) > 0.4

    mismatch_patterns = []
    if draw_risk:
        mismatch_patterns.append("Draw rejimi aktif — beraberlik riski yüksek")
    if market_contradiction:
        mismatch_patterns.append("Çapraz market çelişkisi — farklı marketler farklı yön gösteriyor")

    q_markets = query_entry.get("markets", {})
    for mk, mdata in q_markets.items():
        if mdata and mdata.get("has_late_reversal"):
            mismatch_patterns.append(f"{mk}: Son fazlarda yön değişimi (Late Reversal)")
            break
    for mk, mdata in q_markets.items():
        if mdata and mdata.get("has_phase_shift"):
            mismatch_patterns.append(f"{mk}: Fazlar arası rejim bozulması (Phase Shift)")
            break

    return {
        "top_3_common_traits": top_3_common,
        "top_2_risk_traits": top_2_risk,
        "main_pattern_label": main_pattern,
        "top_shared_patterns": top_shared,
        "top_mismatch_patterns": mismatch_patterns,
        "draw_risk": draw_risk,
        "market_contradiction": market_contradiction,
    }


def run_engine(query_entry, store_entries, top_n=None):
    if top_n is None:
        top_n = TOP_SIMILAR_COUNT

    similar_matches = find_similar_matches(query_entry, store_entries, top_n)

    explanations = []
    for match in similar_matches:
        exp = explain_single_match(query_entry, match)
        explanations.append(exp)

    distribution = compute_result_distribution(similar_matches)
    overall = compute_overall_explainability(query_entry, similar_matches, explanations)

    query_summary = {
        "match_name": query_entry.get("match_name", ""),
        "league": query_entry.get("league", ""),
        "total_volume": query_entry.get("total_volume"),
        "draw_regime": query_entry.get("draw_regime", {}),
        "active_market_weights": query_entry.get("active_market_weights", {}),
    }

    opening_odds = {}
    closing_odds = {}
    for mk in ["moneyway_1x2", "dropping_1x2"]:
        m = query_entry.get("markets", {}).get(mk)
        if m:
            opening_odds = m.get("opening_odds", {})
            closing_odds = m.get("closing_odds", {})
            break

    query_summary["opening_odds"] = opening_odds
    query_summary["closing_odds"] = closing_odds

    ts = {}
    for mk in ["moneyway_1x2", "dropping_1x2"]:
        m = query_entry.get("markets", {}).get(mk)
        if m and m.get("timing_signature"):
            ts = m["timing_signature"]
            break
    query_summary["timing_signature"] = ts

    return {
        "query_summary": query_summary,
        "similar_matches": explanations,
        "result_distribution": distribution,
        "overall_explainability": overall,
        "candidates_checked": len(store_entries),
        "matches_found": len(similar_matches),
    }
