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


def _compact_snapshot(row, table_name):
    keep = {
        'scraped_at', 'ScrapedAt',
        'odds1', 'oddsx', 'odds2', 'pct1', 'pctx', 'pct2', 'amt1', 'amtx', 'amt2',
        'over', 'under', 'pctover', 'pctunder', 'amtover', 'amtunder',
        'oddsyes', 'oddsno', 'pctyes', 'pctno', 'amtyes', 'amtno',
        'volume', 'line',
        'odds1_prev', 'oddsx_prev', 'odds2_prev',
        'over_prev', 'under_prev', 'oddsyes_prev', 'oddsno_prev',
        'trend1', 'trendx', 'trend2', 'trendover', 'trendunder', 'trendyes', 'trendno',
        'droppct1', 'droppctx', 'droppct2', 'droppctover', 'droppctunder', 'droppctyes', 'droppctno',
    }
    out = {}
    for k, v in row.items():
        if k.lower() in {x.lower() for x in keep} and v is not None and v != '':
            out[k] = v
    return out


def _compact_alarm(alarm):
    skip = {'id', 'created_at', 'updated_at'}
    out = {}
    for k, v in alarm.items():
        if k.lower() not in skip and v is not None and v != '':
            out[k] = v
    return out


_TABLE_TO_MARKET = {
    'moneyway_1x2_history': 'moneyway_1x2',
    'moneyway_ou25_history': 'moneyway_ou25',
    'moneyway_btts_history': 'moneyway_btts',
    'dropping_1x2_history': 'dropping_1x2',
    'dropping_ou25_history': 'dropping_ou25',
    'dropping_btts_history': 'dropping_btts',
}


def build_feature_entry(canonical_match, result=None, raw_snapshots=None, alarms=None):
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

    if raw_snapshots:
        for table_name, rows in raw_snapshots.items():
            market_key = _TABLE_TO_MARKET.get(table_name, table_name)
            if market_key not in entry["markets"]:
                entry["markets"][market_key] = {}
            sorted_rows = sorted(rows, key=lambda r: r.get('scraped_at', r.get('ScrapedAt', '')))
            entry["markets"][market_key]["raw_history"] = [_compact_snapshot(r, table_name) for r in sorted_rows]

    if alarms:
        compacted = {}
        for alarm_type, alarm_list in alarms.items():
            if alarm_list:
                compacted[alarm_type] = [_compact_alarm(a) for a in alarm_list]
        if compacted:
            entry["alarms"] = compacted

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
    with_result = 0
    result_counts = {}
    for e in entries:
        leagues.add(e.get("league", ""))
        r = e.get("result")
        if r:
            with_result += 1
            result_counts[r] = result_counts.get(r, 0) + 1
    return {
        "count": len(entries),
        "leagues": sorted(leagues),
        "with_result": with_result,
        "without_result": len(entries) - with_result,
        "result_distribution": result_counts,
        "last_updated": datetime.now().isoformat(),
    }
