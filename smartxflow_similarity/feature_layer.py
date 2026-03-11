from smartxflow_similarity.config import (
    PHASE_DEFINITIONS, AGGREGATE_BLOCKS, PHASE_NAMES,
    MARKET_WEIGHTS_DEFAULT, MARKET_WEIGHTS_DRAW_REGIME,
    REACTION_THRESHOLDS, DRAW_REGIME, LEAGUE_TIERS,
    DEFAULT_LEAGUE_TIER, VOLUME_BUCKETS, CONTEXT_PENALTIES,
)
from smartxflow_similarity.utils import (
    parse_number, compute_no_vig, safe_div, hours_before_kickoff,
    clamp, normalize_0_1, is_placeholder_odds,
)


def assign_phase(hours_before):
    if hours_before is None:
        return None
    for name, start_h, end_h in PHASE_DEFINITIONS:
        if start_h <= hours_before < end_h:
            return name
    return "P10_40plus"


def assign_aggregate_block(hours_before):
    if hours_before is None:
        return None
    for block_name, (start_h, end_h) in AGGREGATE_BLOCKS.items():
        if start_h <= hours_before < end_h:
            return block_name
    return "early_block"


def split_into_phases(snapshots, kickoff):
    phases = {name: [] for name in PHASE_NAMES}
    blocks = {name: [] for name in AGGREGATE_BLOCKS}

    for snap in snapshots:
        scraped = snap.get("scraped_at")
        hb = hours_before_kickoff(scraped, kickoff)
        if hb is None:
            continue
        phase = assign_phase(hb)
        if phase:
            phases[phase].append(snap)
        block = assign_aggregate_block(hb)
        if block:
            blocks[block].append(snap)

    return phases, blocks


def _get_odds_fields(market_key):
    if "1x2" in market_key:
        return ["odds1", "oddsx", "odds2"]
    elif "ou25" in market_key or "ou" in market_key:
        if "dropping" in market_key:
            return ["over", "under"]
        return ["over", "under"]
    elif "btts" in market_key:
        if "dropping" in market_key:
            return ["oddsyes", "oddsno"]
        return ["yes", "no"]
    return []


def _get_pct_fields(market_key):
    if "1x2" in market_key:
        return ["pct1", "pctx", "pct2"]
    elif "ou25" in market_key or "ou" in market_key:
        return ["pctover", "pctunder"]
    elif "btts" in market_key:
        return ["pctyes", "pctno"]
    return []


def _get_amt_fields(market_key):
    if "1x2" in market_key:
        return ["amt1", "amtx", "amt2"]
    elif "ou25" in market_key or "ou" in market_key:
        return ["amtover", "amtunder"]
    elif "btts" in market_key:
        return ["amtyes", "amtno"]
    return []


def _get_selection_labels(market_key):
    if "1x2" in market_key:
        return ["home", "draw", "away"]
    elif "ou25" in market_key or "ou" in market_key:
        return ["over", "under"]
    elif "btts" in market_key:
        return ["yes", "no"]
    return []


def compute_phase_odds_features(phase_snaps, odds_fields):
    features = {}
    if not phase_snaps or not odds_fields:
        return features

    for i, field in enumerate(odds_fields):
        vals = [s.get(field) for s in phase_snaps if s.get(field) is not None and not is_placeholder_odds(s.get(field))]
        if not vals:
            features[f"odds_{i}_start"] = None
            features[f"odds_{i}_end"] = None
            features[f"odds_{i}_drift"] = None
            features[f"odds_{i}_min"] = None
            features[f"odds_{i}_max"] = None
            features[f"odds_{i}_velocity"] = None
            features[f"odds_{i}_acceleration"] = None
            continue

        features[f"odds_{i}_start"] = vals[0]
        features[f"odds_{i}_end"] = vals[-1]
        features[f"odds_{i}_drift"] = vals[-1] - vals[0]
        features[f"odds_{i}_min"] = min(vals)
        features[f"odds_{i}_max"] = max(vals)

        if len(vals) >= 2:
            total_time = len(vals) - 1
            features[f"odds_{i}_velocity"] = (vals[-1] - vals[0]) / total_time
        else:
            features[f"odds_{i}_velocity"] = 0.0

        if len(vals) >= 3:
            mid = len(vals) // 2
            v1 = (vals[mid] - vals[0]) / max(mid, 1)
            v2 = (vals[-1] - vals[mid]) / max(len(vals) - mid - 1, 1)
            features[f"odds_{i}_acceleration"] = v2 - v1
        else:
            features[f"odds_{i}_acceleration"] = 0.0

    return features


def compute_phase_volume_features(phase_snaps, amt_fields, total_match_volume):
    features = {}
    if not phase_snaps or not amt_fields:
        return features

    for i, field in enumerate(amt_fields):
        vals = [parse_number(s.get(field)) for s in phase_snaps]
        vals = [v for v in vals if v is not None]
        if not vals:
            features[f"vol_{i}_start"] = None
            features[f"vol_{i}_end"] = None
            features[f"vol_{i}_delta"] = None
            features[f"vol_{i}_phase_total"] = None
            features[f"vol_{i}_phase_share"] = None
            features[f"vol_{i}_match_share"] = None
            continue

        features[f"vol_{i}_start"] = vals[0]
        features[f"vol_{i}_end"] = vals[-1]
        features[f"vol_{i}_delta"] = vals[-1] - vals[0]
        phase_total = sum(vals)
        features[f"vol_{i}_phase_total"] = phase_total

        total_phase_vol = 0
        for j, f2 in enumerate(amt_fields):
            v2 = [parse_number(s.get(f2)) for s in phase_snaps]
            v2 = [v for v in v2 if v is not None]
            if v2:
                total_phase_vol += sum(v2)
        features[f"vol_{i}_phase_share"] = safe_div(phase_total, total_phase_vol)
        features[f"vol_{i}_match_share"] = safe_div(vals[-1], total_match_volume)

    return features


def compute_phase_novig_features(phase_snaps, odds_fields):
    features = {}
    if not phase_snaps or not odds_fields:
        return features

    def _get_nv(snap):
        odds_vals = [snap.get(f) for f in odds_fields]
        if any(o is None or is_placeholder_odds(o) for o in odds_vals):
            return None
        return compute_no_vig(odds_vals)

    first_nv = None
    last_nv = None
    for snap in phase_snaps:
        nv = _get_nv(snap)
        if nv is not None:
            if first_nv is None:
                first_nv = nv
            last_nv = nv

    if first_nv is None or last_nv is None:
        for i in range(len(odds_fields)):
            features[f"nv_{i}_start"] = None
            features[f"nv_{i}_end"] = None
            features[f"nv_{i}_drift"] = None
            features[f"nv_{i}_shift_direction"] = None
        return features

    for i in range(len(odds_fields)):
        features[f"nv_{i}_start"] = first_nv[i]
        features[f"nv_{i}_end"] = last_nv[i]
        drift = last_nv[i] - first_nv[i]
        features[f"nv_{i}_drift"] = drift
        if drift > 0.005:
            features[f"nv_{i}_shift_direction"] = "strengthening"
        elif drift < -0.005:
            features[f"nv_{i}_shift_direction"] = "weakening"
        else:
            features[f"nv_{i}_shift_direction"] = "stable"

    return features


def compute_phase_moneypct_features(phase_snaps, pct_fields, odds_fields):
    features = {}
    if not phase_snaps or not pct_fields:
        return features

    for i, field in enumerate(pct_fields):
        vals = [parse_number(s.get(field)) for s in phase_snaps]
        vals_clean = [v for v in vals if v is not None]
        if not vals_clean:
            features[f"mpct_{i}_start"] = None
            features[f"mpct_{i}_end"] = None
            features[f"mpct_{i}_delta"] = None
            features[f"mpct_{i}_nv_gap"] = None
            features[f"mpct_{i}_nv_aligned"] = None
            continue

        features[f"mpct_{i}_start"] = vals_clean[0]
        features[f"mpct_{i}_end"] = vals_clean[-1]
        features[f"mpct_{i}_delta"] = vals_clean[-1] - vals_clean[0]

        last_snap = phase_snaps[-1]
        odds_vals = [last_snap.get(f) for f in odds_fields]
        if all(o is not None and not is_placeholder_odds(o) for o in odds_vals):
            nv = compute_no_vig(odds_vals)
            if nv and i < len(nv):
                mpct_norm = vals_clean[-1] / 100.0 if vals_clean[-1] > 1 else vals_clean[-1]
                gap = mpct_norm - nv[i]
                features[f"mpct_{i}_nv_gap"] = gap
                features[f"mpct_{i}_nv_aligned"] = abs(gap) < 0.10
            else:
                features[f"mpct_{i}_nv_gap"] = None
                features[f"mpct_{i}_nv_aligned"] = None
        else:
            features[f"mpct_{i}_nv_gap"] = None
            features[f"mpct_{i}_nv_aligned"] = None

    return features


def classify_reaction(odds_drift, volume_delta, nv_drift, money_pct_delta, total_vol):
    th = REACTION_THRESHOLDS

    if odds_drift is None or volume_delta is None:
        return "NOISE"

    vol_ratio = safe_div(abs(volume_delta), max(total_vol, 1))
    drift_abs = abs(odds_drift)
    vol_abs = vol_ratio

    if vol_abs >= th["freeze_min_volume"] and drift_abs <= th["freeze_max_drift"]:
        return "FREEZE"

    if vol_abs >= th["absorbed_pressure_min_volume"] and drift_abs <= th["absorbed_pressure_max_drift"]:
        return "ABSORBED_PRESSURE"

    if (odds_drift != 0 and volume_delta != 0 and
            (odds_drift > 0) != (volume_delta > 0) and
            drift_abs >= th["true_rlm_min_drift"] and
            vol_abs >= th["true_rlm_opposite_volume"]):
        return "TRUE_RLM"

    if drift_abs >= th["accepted_move_min_drift"] and vol_abs >= th["accepted_move_min_volume"]:
        if (odds_drift > 0) == (volume_delta > 0) or nv_drift is None:
            return "ACCEPTED_MOVE"
        return "CROSS_PRESSURE"

    if drift_abs <= th["weak_acceptance_max_drift"] and vol_abs >= th["weak_acceptance_min_volume"]:
        return "WEAK_ACCEPTANCE"

    if drift_abs >= th["accepted_move_min_drift"] and vol_abs < th["noise_max_volume"]:
        return "MARKET_CORRECTION"

    if drift_abs <= th["noise_max_drift"] and vol_abs <= th["noise_max_volume"]:
        return "NOISE"

    return "NOISE"


def detect_late_reversal(phase_reactions, phase_features):
    early_phases = ["P7_16to20h", "P8_20to30h", "P9_30to40h", "P10_40plus"]
    late_phases = ["P1_0to1h", "P2_1to2h", "P3_2to4h"]

    early_directions = []
    late_directions = []

    for p in early_phases:
        drift = phase_features.get(p, {}).get("odds_0_drift")
        if drift is not None and abs(drift) > 0.01:
            early_directions.append(1 if drift > 0 else -1)

    for p in late_phases:
        drift = phase_features.get(p, {}).get("odds_0_drift")
        if drift is not None and abs(drift) > 0.01:
            late_directions.append(1 if drift > 0 else -1)

    if not early_directions or not late_directions:
        return False

    early_avg = sum(early_directions) / len(early_directions)
    late_avg = sum(late_directions) / len(late_directions)

    return (early_avg > 0 and late_avg < 0) or (early_avg < 0 and late_avg > 0)


def detect_phase_shift(phase_reactions):
    accepted_phases = {}
    for phase_name, reactions in phase_reactions.items():
        for sel_idx, reaction in reactions.items():
            if reaction in ("ACCEPTED_MOVE", "TRUE_RLM"):
                if sel_idx not in accepted_phases:
                    accepted_phases[sel_idx] = []
                accepted_phases[sel_idx].append((phase_name, reaction))

    for sel_idx, phase_list in accepted_phases.items():
        if len(phase_list) >= 2:
            directions = []
            for pname, react in phase_list:
                directions.append(react)
            if "ACCEPTED_MOVE" in directions and "TRUE_RLM" in directions:
                return True
    return False


def compute_phase_reactions(phase_snaps, odds_fields, amt_fields, pct_fields, total_volume):
    reactions = {}
    if not phase_snaps or len(phase_snaps) < 2:
        return reactions

    for i in range(len(odds_fields)):
        odds_vals = [s.get(odds_fields[i]) for s in phase_snaps if s.get(odds_fields[i]) is not None]
        if len(odds_vals) < 2:
            reactions[i] = "NOISE"
            continue

        odds_drift = odds_vals[-1] - odds_vals[0]

        vol_delta = 0
        if i < len(amt_fields):
            vol_vals = [parse_number(s.get(amt_fields[i])) for s in phase_snaps]
            vol_vals = [v for v in vol_vals if v is not None]
            if len(vol_vals) >= 2:
                vol_delta = vol_vals[-1] - vol_vals[0]

        nv_drift = None
        first_nv = None
        last_nv = None
        for snap in phase_snaps:
            ov = [snap.get(f) for f in odds_fields]
            if all(o is not None and not is_placeholder_odds(o) for o in ov):
                nv = compute_no_vig(ov)
                if nv:
                    if first_nv is None:
                        first_nv = nv[i]
                    last_nv = nv[i]
        if first_nv is not None and last_nv is not None:
            nv_drift = last_nv - first_nv

        mpct_delta = 0
        if i < len(pct_fields):
            pv = [parse_number(s.get(pct_fields[i])) for s in phase_snaps]
            pv = [v for v in pv if v is not None]
            if len(pv) >= 2:
                mpct_delta = pv[-1] - pv[0]

        reactions[i] = classify_reaction(odds_drift, vol_delta, nv_drift, mpct_delta, total_volume or 1)

    return reactions


def compute_price_response_efficiency(odds_drift, volume_delta, total_volume):
    if total_volume is None or total_volume == 0:
        return 0.0
    vol_ratio = safe_div(abs(volume_delta), total_volume)
    drift_abs = abs(odds_drift) if odds_drift is not None else 0
    if vol_ratio == 0:
        return 0.0
    return safe_div(drift_abs, vol_ratio)


def compute_money_pct_vs_nv_gap(mpct_end, nv_end):
    if mpct_end is None or nv_end is None:
        return None
    mpct_norm = mpct_end / 100.0 if mpct_end > 1 else mpct_end
    return mpct_norm - nv_end


def compute_phase_dominance(phase_features, odds_fields_count):
    dominance = {}
    for i in range(odds_fields_count):
        odds_drift = phase_features.get(f"odds_{i}_drift")
        vol_delta = phase_features.get(f"vol_{i}_delta")
        nv_drift = phase_features.get(f"nv_{i}_drift")

        score = 0
        if odds_drift is not None and odds_drift < -0.02:
            score += 1
        if vol_delta is not None and vol_delta > 0:
            score += 1
        if nv_drift is not None and nv_drift > 0.005:
            score += 1

        dominance[f"sel_{i}_dominance"] = score
    return dominance


def compute_timing_signature(all_phase_features, odds_fields_count):
    early_pressure = 0.0
    mid_pressure = 0.0
    late_pressure = 0.0

    early_phases = ["P7_16to20h", "P8_20to30h", "P9_30to40h", "P10_40plus"]
    mid_phases = ["P4_4to8h", "P5_8to12h", "P6_12to16h"]
    late_phases = ["P1_0to1h", "P2_1to2h", "P3_2to4h"]

    def _phase_pressure(phase_name):
        pf = all_phase_features.get(phase_name, {})
        total = 0.0
        for i in range(odds_fields_count):
            d = pf.get(f"odds_{i}_drift")
            if d is not None:
                total += abs(d)
        return total

    for p in early_phases:
        early_pressure += _phase_pressure(p)
    for p in mid_phases:
        mid_pressure += _phase_pressure(p)
    for p in late_phases:
        late_pressure += _phase_pressure(p)

    total = early_pressure + mid_pressure + late_pressure
    if total == 0:
        return {
            "early_pressure_ratio": 0.33,
            "mid_pressure_ratio": 0.33,
            "late_pressure_ratio": 0.34,
            "dominant_timing": "balanced",
        }

    er = early_pressure / total
    mr = mid_pressure / total
    lr = late_pressure / total

    if lr > 0.50:
        dom = "late_driven"
    elif er > 0.50:
        dom = "early_driven"
    elif mr > 0.50:
        dom = "mid_driven"
    else:
        dom = "balanced"

    return {
        "early_pressure_ratio": round(er, 4),
        "mid_pressure_ratio": round(mr, 4),
        "late_pressure_ratio": round(lr, 4),
        "dominant_timing": dom,
    }


def extract_market_features(snapshots, market_key, kickoff, total_volume):
    odds_fields = _get_odds_fields(market_key)
    pct_fields = _get_pct_fields(market_key)
    amt_fields = _get_amt_fields(market_key)
    sel_labels = _get_selection_labels(market_key)

    phases, blocks = split_into_phases(snapshots, kickoff)

    all_phase_features = {}
    all_phase_reactions = {}
    all_block_features = {}

    for phase_name in PHASE_NAMES:
        phase_snaps = phases[phase_name]
        pf = {}
        pf.update(compute_phase_odds_features(phase_snaps, odds_fields))
        pf.update(compute_phase_volume_features(phase_snaps, amt_fields, total_volume))
        pf.update(compute_phase_novig_features(phase_snaps, odds_fields))
        pf.update(compute_phase_moneypct_features(phase_snaps, pct_fields, odds_fields))

        reactions = compute_phase_reactions(phase_snaps, odds_fields, amt_fields, pct_fields, total_volume)
        all_phase_reactions[phase_name] = reactions

        for sel_i in range(len(odds_fields)):
            drift = pf.get(f"odds_{sel_i}_drift", 0) or 0
            vol_d = pf.get(f"vol_{sel_i}_delta", 0) or 0
            pf[f"pre_{sel_i}"] = compute_price_response_efficiency(drift, vol_d, total_volume)

            mpct_e = pf.get(f"mpct_{sel_i}_end")
            nv_e = pf.get(f"nv_{sel_i}_end")
            pf[f"mpct_nv_gap_{sel_i}"] = compute_money_pct_vs_nv_gap(mpct_e, nv_e)

        pf["dominance"] = compute_phase_dominance(pf, len(odds_fields))
        pf["reactions"] = reactions
        pf["snapshot_count"] = len(phase_snaps)
        all_phase_features[phase_name] = pf

    for block_name, block_snaps in blocks.items():
        bf = {}
        bf.update(compute_phase_odds_features(block_snaps, odds_fields))
        bf.update(compute_phase_volume_features(block_snaps, amt_fields, total_volume))
        bf.update(compute_phase_novig_features(block_snaps, odds_fields))
        bf.update(compute_phase_moneypct_features(block_snaps, pct_fields, odds_fields))

        block_reactions = compute_phase_reactions(block_snaps, odds_fields, amt_fields, pct_fields, total_volume)
        bf["reactions"] = block_reactions
        bf["snapshot_count"] = len(block_snaps)
        all_block_features[block_name] = bf

    has_late_reversal = detect_late_reversal(all_phase_reactions, all_phase_features)
    has_phase_shift = detect_phase_shift(all_phase_reactions)

    timing_sig = compute_timing_signature(all_phase_features, len(odds_fields))

    opening_odds = {}
    closing_odds = {}
    opening_nv = None
    closing_nv = None

    closing_amounts = {}

    if snapshots:
        first = snapshots[0]
        last = snapshots[-1]
        for i, f in enumerate(odds_fields):
            opening_odds[sel_labels[i] if i < len(sel_labels) else f"sel_{i}"] = first.get(f)
            closing_odds[sel_labels[i] if i < len(sel_labels) else f"sel_{i}"] = last.get(f)
        for i, f in enumerate(amt_fields):
            closing_amounts[sel_labels[i] if i < len(sel_labels) else f"sel_{i}"] = last.get(f)

        first_ov = [first.get(f) for f in odds_fields]
        last_ov = [last.get(f) for f in odds_fields]
        if all(o is not None and not is_placeholder_odds(o) for o in first_ov):
            opening_nv = compute_no_vig(first_ov)
        if all(o is not None and not is_placeholder_odds(o) for o in last_ov):
            closing_nv = compute_no_vig(last_ov)

    overall_pre = {}
    overall_mpct_nv_gap = {}
    for i in range(len(odds_fields)):
        pre_vals = [all_phase_features[p].get(f"pre_{i}", 0) for p in PHASE_NAMES if all_phase_features[p].get(f"pre_{i}") is not None]
        overall_pre[f"sel_{i}"] = sum(pre_vals) / max(len(pre_vals), 1)
        gap_vals = [all_phase_features[p].get(f"mpct_nv_gap_{i}") for p in PHASE_NAMES if all_phase_features[p].get(f"mpct_nv_gap_{i}") is not None]
        overall_mpct_nv_gap[f"sel_{i}"] = sum(gap_vals) / max(len(gap_vals), 1) if gap_vals else None

    covered = [p for p in PHASE_NAMES if all_phase_features[p]["snapshot_count"] > 0]

    return {
        "market_key": market_key,
        "odds_fields": odds_fields,
        "selection_labels": sel_labels,
        "opening_odds": opening_odds,
        "closing_odds": closing_odds,
        "closing_amounts": closing_amounts,
        "opening_nv": opening_nv,
        "closing_nv": closing_nv,
        "phase_features": all_phase_features,
        "block_features": all_block_features,
        "phase_reactions": all_phase_reactions,
        "has_late_reversal": has_late_reversal,
        "has_phase_shift": has_phase_shift,
        "timing_signature": timing_sig,
        "overall_price_response_efficiency": overall_pre,
        "overall_mpct_nv_gap": overall_mpct_nv_gap,
        "phase_coverage": len(covered) / len(PHASE_NAMES),
        "covered_phases": covered,
        "total_snapshots": len(snapshots),
    }


def compute_cross_market_features(market_features_dict):
    f1x2 = market_features_dict.get("moneyway_1x2") or market_features_dict.get("dropping_1x2")
    fou = market_features_dict.get("moneyway_ou25") or market_features_dict.get("dropping_ou25")
    fbtts = market_features_dict.get("moneyway_btts") or market_features_dict.get("dropping_btts")

    result = {
        "directional_harmony_score": 0.0,
        "tempo_contradiction_score": 0.0,
        "draw_pressure_score": 0.0,
        "winner_without_goals_pattern": False,
        "open_game_directional_pattern": False,
        "low_event_pattern": False,
        "cross_market_harmony": 0.0,
        "cross_market_contradiction": 0.0,
    }

    if not f1x2:
        return result

    home_nv_drift = None
    away_nv_drift = None
    draw_nv_drift = None
    if f1x2.get("closing_nv") and f1x2.get("opening_nv"):
        home_nv_drift = f1x2["closing_nv"][0] - f1x2["opening_nv"][0]
        draw_nv_drift = f1x2["closing_nv"][1] - f1x2["opening_nv"][1]
        away_nv_drift = f1x2["closing_nv"][2] - f1x2["opening_nv"][2]

    fav_direction = 0
    if home_nv_drift is not None and away_nv_drift is not None:
        if home_nv_drift > away_nv_drift:
            fav_direction = 1
        elif away_nv_drift > home_nv_drift:
            fav_direction = -1

    ou_direction = 0
    if fou and fou.get("closing_nv") and fou.get("opening_nv"):
        over_drift = fou["closing_nv"][0] - fou["opening_nv"][0]
        under_drift = fou["closing_nv"][1] - fou["opening_nv"][1]
        if over_drift > under_drift:
            ou_direction = 1
        elif under_drift > over_drift:
            ou_direction = -1

    btts_direction = 0
    if fbtts and fbtts.get("closing_nv") and fbtts.get("opening_nv"):
        yes_drift = fbtts["closing_nv"][0] - fbtts["opening_nv"][0]
        no_drift = fbtts["closing_nv"][1] - fbtts["opening_nv"][1]
        if yes_drift > no_drift:
            btts_direction = 1
        elif no_drift > yes_drift:
            btts_direction = -1

    harmony = 0
    contradiction = 0
    checks = 0

    if fav_direction != 0:
        if fav_direction != 0 and ou_direction == 1:
            harmony += 1
        elif fav_direction != 0 and ou_direction == -1:
            if abs(fav_direction) > 0:
                contradiction += 0.5
        checks += 1

        if btts_direction == 1:
            harmony += 0.5
        elif btts_direction == -1:
            contradiction += 0.3
        checks += 1

    if checks > 0:
        result["directional_harmony_score"] = harmony / checks
        result["cross_market_harmony"] = harmony / checks
        result["cross_market_contradiction"] = contradiction / checks

    if fav_direction != 0 and ou_direction == -1:
        result["tempo_contradiction_score"] = 0.7
    elif fav_direction != 0 and ou_direction == 0:
        result["tempo_contradiction_score"] = 0.3

    if fav_direction != 0 and ou_direction == -1 and btts_direction == -1:
        result["winner_without_goals_pattern"] = True
    if fav_direction != 0 and ou_direction == 1 and btts_direction == 1:
        result["open_game_directional_pattern"] = True
    if ou_direction == -1 and btts_direction == -1:
        result["low_event_pattern"] = True

    draw_p = 0.0
    if draw_nv_drift is not None and draw_nv_drift > 0:
        draw_p += 0.3
    if ou_direction == -1:
        draw_p += 0.3
    if btts_direction == -1:
        draw_p += 0.2
    if f1x2.get("closing_nv"):
        nv = f1x2["closing_nv"]
        if len(nv) >= 3:
            balance = 1.0 - abs(nv[0] - nv[2])
            draw_p += balance * 0.2
    result["draw_pressure_score"] = clamp(draw_p)

    return result


def compute_draw_regime(market_features_dict, cross_market):
    cfg = DRAW_REGIME
    score = 0.0

    fou = market_features_dict.get("moneyway_ou25") or market_features_dict.get("dropping_ou25")
    fbtts = market_features_dict.get("moneyway_btts") or market_features_dict.get("dropping_btts")
    f1x2 = market_features_dict.get("moneyway_1x2") or market_features_dict.get("dropping_1x2")

    under_strength = 0.0
    if fou and fou.get("closing_nv") and fou.get("opening_nv"):
        under_drift = fou["closing_nv"][1] - fou["opening_nv"][1]
        under_strength = clamp(under_drift * 5, 0, 1)
    score += under_strength * cfg["under_strength_weight"]

    btts_no_strength = 0.0
    if fbtts and fbtts.get("closing_nv") and fbtts.get("opening_nv"):
        no_drift = fbtts["closing_nv"][1] - fbtts["opening_nv"][1]
        btts_no_strength = clamp(no_drift * 5, 0, 1)
    score += btts_no_strength * cfg["btts_no_strength_weight"]

    liq_balance = 0.0
    if f1x2 and f1x2.get("closing_nv"):
        nv = f1x2["closing_nv"]
        if len(nv) >= 3:
            liq_balance = 1.0 - abs(nv[0] - nv[2])
    score += liq_balance * cfg["liquidity_balance_weight"]

    nv_symmetry = 0.0
    if f1x2 and f1x2.get("closing_nv"):
        nv = f1x2["closing_nv"]
        if len(nv) >= 3:
            nv_symmetry = nv[1]
    score += nv_symmetry * cfg["nv_symmetry_weight"]

    low_dir_gap = 0.0
    if f1x2 and f1x2.get("closing_nv") and f1x2.get("opening_nv"):
        home_drift = abs(f1x2["closing_nv"][0] - f1x2["opening_nv"][0])
        away_drift = abs(f1x2["closing_nv"][2] - f1x2["opening_nv"][2])
        max_drift = max(home_drift, away_drift)
        low_dir_gap = clamp(1.0 - max_drift * 10, 0, 1)
    score += low_dir_gap * cfg["low_dir_gap_weight"]

    return {
        "draw_regime_score": round(clamp(score), 4),
        "is_draw_regime": score >= cfg["threshold"],
        "under_strength": round(under_strength, 4),
        "btts_no_strength": round(btts_no_strength, 4),
        "liquidity_balance": round(liq_balance, 4),
        "nv_symmetry": round(nv_symmetry, 4),
        "low_directional_gap": round(low_dir_gap, 4),
    }


def compute_context_features(canonical_match, market_features_dict):
    meta = canonical_match.get("meta", {})
    league = meta.get("league", "")
    total_vol = canonical_match.get("total_volume")

    league_tier = DEFAULT_LEAGUE_TIER
    for tier, leagues in LEAGUE_TIERS.items():
        if league in leagues:
            league_tier = tier
            break

    vol_bucket = 1
    if total_vol is not None:
        for bucket, (lo, hi) in VOLUME_BUCKETS.items():
            if lo <= total_vol < hi:
                vol_bucket = bucket
                break

    total_snaps = canonical_match.get("total_snapshots", 0)
    available = canonical_match.get("available_markets", [])
    missing = canonical_match.get("missing_markets", [])

    all_coverages = []
    for mf in market_features_dict.values():
        if mf:
            all_coverages.append(mf.get("phase_coverage", 0))
    avg_coverage = sum(all_coverages) / max(len(all_coverages), 1) if all_coverages else 0

    first_snap_time = None
    last_snap_time = None
    for key, snaps in canonical_match.get("snapshots", {}).items():
        for s in snaps:
            t = s.get("scraped_at")
            if t is not None:
                if first_snap_time is None or t < first_snap_time:
                    first_snap_time = t
                if last_snap_time is None or t > last_snap_time:
                    last_snap_time = t

    market_duration_hours = 0
    if first_snap_time and last_snap_time:
        market_duration_hours = (last_snap_time - first_snap_time).total_seconds() / 3600.0

    snapshot_density = total_snaps / max(market_duration_hours, 1)

    data_quality = 1.0
    if total_snaps < 20:
        data_quality -= CONTEXT_PENALTIES["low_snapshot_penalty"]
    if len(missing) > 2:
        data_quality -= CONTEXT_PENALTIES["low_snapshot_penalty"]
    if league_tier >= 4:
        data_quality -= CONTEXT_PENALTIES["exotic_league_penalty"]
    if market_duration_hours < 6:
        data_quality -= CONTEXT_PENALTIES["short_duration_penalty"]
    if total_vol is not None and total_vol > 5000000:
        data_quality -= CONTEXT_PENALTIES["suspicious_volume_penalty"]
    data_quality = clamp(data_quality, 0.0, 1.0)

    return {
        "league_tier": league_tier,
        "volume_bucket": vol_bucket,
        "total_volume": total_vol,
        "market_duration_hours": round(market_duration_hours, 2),
        "snapshot_density": round(snapshot_density, 2),
        "phase_coverage_score": round(avg_coverage, 4),
        "total_snapshots": total_snaps,
        "available_markets": available,
        "missing_markets": missing,
        "data_quality_score": round(data_quality, 4),
        "is_exotic": league_tier >= 4,
    }


def extract_all_features(canonical_match):
    meta = canonical_match.get("meta", {})
    kickoff = meta.get("kickoff")
    snapshots = canonical_match.get("snapshots", {})
    total_vol = canonical_match.get("total_volume")

    market_features = {}

    market_map = {
        "moneyway_1x2":  "moneyway_1x2",
        "moneyway_ou25": "moneyway_ou25",
        "moneyway_btts": "moneyway_btts",
        "dropping_1x2":  "dropping_1x2",
        "dropping_ou25": "dropping_ou25",
        "dropping_btts": "dropping_btts",
    }

    for snap_key, market_key in market_map.items():
        snaps = snapshots.get(snap_key, [])
        if snaps:
            market_features[market_key] = extract_market_features(snaps, market_key, kickoff, total_vol)
        else:
            market_features[market_key] = None

    cross_market = compute_cross_market_features(market_features)
    draw_regime = compute_draw_regime(market_features, cross_market)
    context = compute_context_features(canonical_match, market_features)

    is_draw = draw_regime.get("is_draw_regime", False)
    active_weights = MARKET_WEIGHTS_DRAW_REGIME if is_draw else MARKET_WEIGHTS_DEFAULT

    return {
        "meta": meta,
        "market_features": market_features,
        "cross_market": cross_market,
        "draw_regime": draw_regime,
        "context": context,
        "active_market_weights": active_weights,
        "total_volume": total_vol,
        "warnings": canonical_match.get("warnings", []),
    }
