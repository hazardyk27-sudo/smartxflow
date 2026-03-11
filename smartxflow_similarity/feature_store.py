import json
import os
from datetime import datetime

from smartxflow_similarity.parser_layer import build_canonical_match
from smartxflow_similarity.feature_layer import extract_all_features


STORE_VERSION = "1.0"


def _serialize_datetime(obj):
    if isinstance(obj, datetime):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj)} is not JSON serializable")


def build_feature_entry(canonical_match, result=None):
    features = extract_all_features(canonical_match)
    meta = features.get("meta", {})

    entry = {
        "store_version": STORE_VERSION,
        "match_id_hash": meta.get("match_id_hash", ""),
        "match_name": f"{meta.get('home', '?')} vs {meta.get('away', '?')}",
        "league": meta.get("league", ""),
        "kickoff": meta.get("kickoff").isoformat() if meta.get("kickoff") else None,
        "result": result,
        "total_volume": features.get("total_volume"),
        "data_quality_score": features.get("context", {}).get("data_quality_score"),
        "league_tier": features.get("context", {}).get("league_tier"),
        "volume_bucket": features.get("context", {}).get("volume_bucket"),
        "market_duration_hours": features.get("context", {}).get("market_duration_hours"),
        "phase_coverage_score": features.get("context", {}).get("phase_coverage_score"),
        "draw_regime": features.get("draw_regime", {}),
        "cross_market": features.get("cross_market", {}),
        "active_market_weights": features.get("active_market_weights", {}),
        "context": features.get("context", {}),
        "warnings": features.get("warnings", []),
        "markets": {},
    }

    for market_key, mf in features.get("market_features", {}).items():
        if mf is None:
            continue
        entry["markets"][market_key] = {
            "opening_odds": mf.get("opening_odds"),
            "closing_odds": mf.get("closing_odds"),
            "closing_amounts": mf.get("closing_amounts"),
            "opening_nv": mf.get("opening_nv"),
            "closing_nv": mf.get("closing_nv"),
            "selection_labels": mf.get("selection_labels"),
            "phase_coverage": mf.get("phase_coverage"),
            "covered_phases": mf.get("covered_phases"),
            "total_snapshots": mf.get("total_snapshots"),
            "has_late_reversal": mf.get("has_late_reversal"),
            "has_phase_shift": mf.get("has_phase_shift"),
            "timing_signature": mf.get("timing_signature"),
            "overall_price_response_efficiency": mf.get("overall_price_response_efficiency"),
            "overall_mpct_nv_gap": mf.get("overall_mpct_nv_gap"),
            "phase_features": mf.get("phase_features"),
            "block_features": mf.get("block_features"),
            "phase_reactions": mf.get("phase_reactions"),
        }

    return entry


def save_store(entries, filepath):
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    with open(filepath, "w", encoding="utf-8") as f:
        for entry in entries:
            f.write(json.dumps(entry, default=_serialize_datetime, ensure_ascii=False) + "\n")


def load_store(filepath):
    entries = []
    if not os.path.exists(filepath):
        return entries
    with open(filepath, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if line:
                entries.append(json.loads(line))
    return entries


def append_to_store(entry, filepath):
    os.makedirs(os.path.dirname(filepath) if os.path.dirname(filepath) else ".", exist_ok=True)
    with open(filepath, "a", encoding="utf-8") as f:
        f.write(json.dumps(entry, default=_serialize_datetime, ensure_ascii=False) + "\n")


def get_store_info(filepath):
    entries = load_store(filepath)
    if not entries:
        return {"count": 0, "last_updated": None}
    leagues = set()
    for e in entries:
        leagues.add(e.get("league", ""))
    return {
        "count": len(entries),
        "leagues": sorted(leagues),
        "last_updated": datetime.now().isoformat(),
    }
