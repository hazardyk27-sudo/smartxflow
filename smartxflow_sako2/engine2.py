from smartxflow_sako2.config2 import BLOCK_LABELS, TOP_SIMILAR_COUNT
from smartxflow_sako2.similarity2 import find_similar_matches


def _safe_div(a, b):
    if b == 0:
        return 0.0
    return a / b


def _parse_score(score_str):
    if not score_str or "-" not in str(score_str):
        return None, None
    parts = str(score_str).split("-")
    try:
        return int(parts[0]), int(parts[1])
    except (ValueError, IndexError):
        return None, None


def _get_favorite_side(candidate):
    markets = candidate.get("markets", {})
    m1x2 = markets.get("moneyway_1x2") or markets.get("dropping_1x2") or {}
    closing = m1x2.get("closing_odds", {})
    odds_1 = closing.get("1") or closing.get("home")
    odds_2 = closing.get("2") or closing.get("away")
    if odds_1 is None or odds_2 is None:
        return None
    try:
        odds_1 = float(odds_1)
        odds_2 = float(odds_2)
    except (ValueError, TypeError):
        return None
    if odds_1 < odds_2:
        return "HOME"
    elif odds_2 < odds_1:
        return "AWAY"
    return None


def compute_result_distribution(similar_matches):
    empty = {
        "simple": {"favori": 0, "draw": 0, "surpriz": 0, "total": 0},
        "weighted": {"favori": 0, "draw": 0, "surpriz": 0},
    }
    if not similar_matches:
        return empty

    fav_count = 0
    draw_count = 0
    sur_count = 0
    total_with_result = 0

    w_fav = 0.0
    w_draw = 0.0
    w_sur = 0.0
    weight_sum = 0.0

    for match in similar_matches:
        candidate = match["candidate"]
        result = candidate.get("result")
        sim_score = match["similarity"]["total_score"]

        if result is None:
            continue

        result_str = str(result).strip().upper()
        total_with_result += 1

        if result_str in ("DRAW", "X", "D"):
            draw_count += 1
            w_draw += sim_score
            weight_sum += sim_score
        else:
            fav_side = _get_favorite_side(candidate)
            if fav_side is None:
                total_with_result -= 1
                continue
            if result_str in ("HOME", "1", "H"):
                winner = "HOME"
            elif result_str in ("AWAY", "2", "A"):
                winner = "AWAY"
            else:
                total_with_result -= 1
                continue

            if winner == fav_side:
                fav_count += 1
                w_fav += sim_score
            else:
                sur_count += 1
                w_sur += sim_score
            weight_sum += sim_score

    simple = {
        "favori": round(_safe_div(fav_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
        "draw": round(_safe_div(draw_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
        "surpriz": round(_safe_div(sur_count, total_with_result) * 100, 1) if total_with_result > 0 else 0,
        "total": total_with_result,
    }

    weighted = {"favori": 0, "draw": 0, "surpriz": 0}
    if weight_sum > 0:
        weighted = {
            "favori": round(w_fav / weight_sum * 100, 1),
            "draw": round(w_draw / weight_sum * 100, 1),
            "surpriz": round(w_sur / weight_sum * 100, 1),
        }

    return {"simple": simple, "weighted": weighted}


def compute_ou25_distribution(similar_matches):
    empty = {
        "simple": {"over": 0, "under": 0, "total": 0},
        "weighted": {"over": 0, "under": 0},
    }
    if not similar_matches:
        return empty

    over_count = 0
    under_count = 0
    total = 0
    w_over = 0.0
    w_under = 0.0
    weight_sum = 0.0

    for match in similar_matches:
        candidate = match["candidate"]
        score = candidate.get("score")
        hg, ag = _parse_score(score)
        if hg is None:
            continue
        sim_score = match["similarity"]["total_score"]
        total += 1
        if (hg + ag) > 2:
            over_count += 1
            w_over += sim_score
        else:
            under_count += 1
            w_under += sim_score
        weight_sum += sim_score

    simple = {
        "over": round(_safe_div(over_count, total) * 100, 1) if total > 0 else 0,
        "under": round(_safe_div(under_count, total) * 100, 1) if total > 0 else 0,
        "total": total,
    }
    weighted = {"over": 0, "under": 0}
    if weight_sum > 0:
        weighted = {
            "over": round(w_over / weight_sum * 100, 1),
            "under": round(w_under / weight_sum * 100, 1),
        }
    return {"simple": simple, "weighted": weighted}


def compute_btts_distribution(similar_matches):
    empty = {
        "simple": {"yes": 0, "no": 0, "total": 0},
        "weighted": {"yes": 0, "no": 0},
    }
    if not similar_matches:
        return empty

    yes_count = 0
    no_count = 0
    total = 0
    w_yes = 0.0
    w_no = 0.0
    weight_sum = 0.0

    for match in similar_matches:
        candidate = match["candidate"]
        score = candidate.get("score")
        hg, ag = _parse_score(score)
        if hg is None:
            continue
        sim_score = match["similarity"]["total_score"]
        total += 1
        if hg > 0 and ag > 0:
            yes_count += 1
            w_yes += sim_score
        else:
            no_count += 1
            w_no += sim_score
        weight_sum += sim_score

    simple = {
        "yes": round(_safe_div(yes_count, total) * 100, 1) if total > 0 else 0,
        "no": round(_safe_div(no_count, total) * 100, 1) if total > 0 else 0,
        "total": total,
    }
    weighted = {"yes": 0, "no": 0}
    if weight_sum > 0:
        weighted = {
            "yes": round(w_yes / weight_sum * 100, 1),
            "no": round(w_no / weight_sum * 100, 1),
        }
    return {"simple": simple, "weighted": weighted}


def explain_single_match(query_entry, match_result):
    candidate = match_result["candidate"]
    sim = match_result["similarity"]
    block_scores = sim.get("block_scores", {})

    numeric_blocks = {k: v for k, v in block_scores.items() if not k.endswith("_detail")}
    sorted_blocks = sorted(numeric_blocks.items(), key=lambda x: x[1], reverse=True)
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
        "score": candidate.get("score"),
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


def run_engine(query_entry, store_entries, top_n=None, market_filter=None):
    if top_n is None:
        top_n = TOP_SIMILAR_COUNT

    similar_matches = find_similar_matches(query_entry, store_entries, top_n, market_filter=market_filter)

    explanations = []
    for match in similar_matches:
        exp = explain_single_match(query_entry, match)
        explanations.append(exp)

    distribution = compute_result_distribution(similar_matches)
    ou25_distribution = compute_ou25_distribution(similar_matches)
    btts_distribution = compute_btts_distribution(similar_matches)
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
        "ou25_distribution": ou25_distribution,
        "btts_distribution": btts_distribution,
        "overall_explainability": overall,
        "candidates_checked": len(store_entries),
        "matches_found": len(similar_matches),
    }
