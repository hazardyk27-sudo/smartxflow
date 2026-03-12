from smartxflow_sako2.config2 import BLOCK_LABELS, TOP_SIMILAR_COUNT
from smartxflow_sako2.similarity2 import find_similar_matches


def _safe_div(a, b):
    if b == 0:
        return 0.0
    return a / b


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
        "home": round(_safe_div(home_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
        "draw": round(_safe_div(draw_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
        "away": round(_safe_div(away_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
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
    top_similar = sorted_blocks[:3]
    top_divergent = sorted_blocks[-2:] if len(sorted_blocks) >= 2 else sorted_blocks

    c_markets = candidate.get("markets", {})
    c_1x2 = c_markets.get("moneyway_1x2") or c_markets.get("dropping_1x2") or {}
    c_ou25 = c_markets.get("moneyway_ou25") or c_markets.get("dropping_ou25") or {}
    c_btts = c_markets.get("moneyway_btts") or c_markets.get("dropping_btts") or {}

    return {
        "match_name": candidate.get("match_name", ""),
        "league": candidate.get("league", ""),
        "kickoff": candidate.get("kickoff"),
        "result": candidate.get("result"),
        "similarity_score": sim["total_score"],
        "opening_odds": c_1x2.get("opening_odds", {}),
        "closing_odds": c_1x2.get("closing_odds", {}),
        "closing_amounts": c_1x2.get("closing_amounts", {}),
        "ou25_opening": c_ou25.get("opening_odds", {}),
        "ou25_closing": c_ou25.get("closing_odds", {}),
        "ou25_closing_amounts": c_ou25.get("closing_amounts", {}),
        "btts_opening": c_btts.get("opening_odds", {}),
        "btts_closing": c_btts.get("closing_odds", {}),
        "btts_closing_amounts": c_btts.get("closing_amounts", {}),
        "total_volume": candidate.get("total_volume"),
        "top_3_similar_blocks": [
            {"block": b[0], "score": b[1], "label": BLOCK_LABELS.get(b[0], b[0])}
            for b in top_similar
        ],
        "top_2_divergent_blocks": [
            {"block": b[0], "score": b[1], "label": BLOCK_LABELS.get(b[0], b[0])}
            for b in top_divergent
        ],
        "block_scores": block_scores,
    }


def compute_overall_explainability(query_entry, explanations):
    if not explanations:
        return {
            "top_3_common_traits": [],
            "top_2_risk_traits": [],
            "main_pattern_label": "Yeterli veri yok",
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

    return {
        "top_3_common_traits": top_3_common,
        "top_2_risk_traits": top_2_risk,
        "main_pattern_label": "Oran + Hacim + Para Dağılımı Bazlı Benzerlik",
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
    overall = compute_overall_explainability(query_entry, explanations)

    query_summary = {
        "match_name": query_entry.get("match_name", ""),
        "league": query_entry.get("league", ""),
        "total_volume": query_entry.get("total_volume"),
        "kickoff_time": query_entry.get("kickoff") or query_entry.get("kickoff_time"),
    }

    markets = query_entry.get("markets", {})

    q_1x2 = markets.get("moneyway_1x2") or markets.get("dropping_1x2") or {}
    query_summary["opening_odds"] = q_1x2.get("opening_odds", {})
    query_summary["closing_odds"] = q_1x2.get("closing_odds", {})
    query_summary["closing_amounts"] = q_1x2.get("closing_amounts", {})

    q_ou25 = markets.get("moneyway_ou25") or markets.get("dropping_ou25") or {}
    query_summary["ou25_opening"] = q_ou25.get("opening_odds", {})
    query_summary["ou25_closing"] = q_ou25.get("closing_odds", {})
    query_summary["ou25_closing_amounts"] = q_ou25.get("closing_amounts", {})

    q_btts = markets.get("moneyway_btts") or markets.get("dropping_btts") or {}
    query_summary["btts_opening"] = q_btts.get("opening_odds", {})
    query_summary["btts_closing"] = q_btts.get("closing_odds", {})
    query_summary["btts_closing_amounts"] = q_btts.get("closing_amounts", {})

    return {
        "query_summary": query_summary,
        "similar_matches": explanations,
        "result_distribution": distribution,
        "overall_explainability": overall,
        "candidates_checked": len(store_entries),
        "matches_found": len(similar_matches),
    }
