PHASE_DEFINITIONS = [
    ("P1_0to1h",   0,   1),
    ("P2_1to2h",   1,   2),
    ("P3_2to4h",   2,   4),
    ("P4_4to8h",   4,   8),
    ("P5_8to12h",  8,  12),
    ("P6_12to16h", 12, 16),
    ("P7_16to20h", 16, 20),
    ("P8_20to30h", 20, 30),
    ("P9_30to40h", 30, 40),
    ("P10_40plus", 40, 9999),
]

PHASE_NAMES = [p[0] for p in PHASE_DEFINITIONS]

AGGREGATE_BLOCKS = {
    "late_block":  (0,  4),
    "mid_block":   (4,  16),
    "early_block": (16, 9999),
}

PHASE_WEIGHTS = {
    "P1_0to1h":   0.16,
    "P2_1to2h":   0.14,
    "P3_2to4h":   0.13,
    "P4_4to8h":   0.12,
    "P5_8to12h":  0.10,
    "P6_12to16h": 0.09,
    "P7_16to20h": 0.08,
    "P8_20to30h": 0.07,
    "P9_30to40h": 0.06,
    "P10_40plus": 0.05,
}

MARKET_WEIGHTS_DEFAULT = {
    "1x2":  0.50,
    "ou25": 0.25,
    "btts": 0.25,
}

MARKET_WEIGHTS_DRAW_REGIME = {
    "1x2":  0.45,
    "ou25": 0.30,
    "btts": 0.25,
}

SIMILARITY_BLOCK_WEIGHTS = {
    "market_shape":      0.20,
    "flow_shape":        0.25,
    "price_reaction":    0.25,
    "cross_market_draw": 0.20,
    "context":           0.10,
}

MARKET_SHAPE_SUB_WEIGHTS = {
    "opening_odds_profile": 0.20,
    "closing_odds_profile": 0.10,
    "nv_drift_pattern":     0.40,
    "favorite_shape":       0.15,
    "balance_index":        0.15,
}

FLOW_SHAPE_SUB_WEIGHTS = {
    "total_volume_normalized": 0.10,
    "dom_pattern":             0.20,
    "phase_liquidity":         0.40,
    "late_money_ratio":        0.20,
    "night_money_ratio":       0.10,
}

PRICE_REACTION_SUB_WEIGHTS = {
    "phase_odds_drift":     0.20,
    "response_efficiency":  0.35,
    "freeze_profile":       0.20,
    "rlm_profile":          0.15,
    "closing_behavior":     0.10,
}

CROSS_MARKET_DRAW_SUB_WEIGHTS = {
    "ou_support":     0.20,
    "btts_support":   0.20,
    "draw_regime":    0.40,
    "harmony_score":  0.20,
}

CONTEXT_SUB_WEIGHTS = {
    "league_tier":     0.35,
    "volume_bucket":   0.25,
    "data_quality":    0.20,
    "market_duration": 0.20,
}

HARD_FILTER = {
    "odds_band_tolerance":       0.80,
    "league_tier_max_diff":      2,
    "volume_bucket_max_diff":    2,
    "min_data_quality":          0.30,
    "market_duration_max_diff":  60,
}

DRAW_REGIME = {
    "under_strength_weight":     0.25,
    "btts_no_strength_weight":   0.25,
    "liquidity_balance_weight":  0.20,
    "nv_symmetry_weight":        0.15,
    "low_dir_gap_weight":        0.15,
    "threshold":                 0.55,
}

REACTION_THRESHOLDS = {
    "accepted_move_min_drift":      0.03,
    "accepted_move_min_volume":     0.05,
    "weak_acceptance_max_drift":    0.03,
    "weak_acceptance_min_volume":   0.03,
    "freeze_max_drift":             0.005,
    "freeze_min_volume":            0.05,
    "absorbed_pressure_max_drift":  0.015,
    "absorbed_pressure_min_volume": 0.07,
    "true_rlm_min_drift":          0.02,
    "true_rlm_opposite_volume":    0.05,
    "noise_max_volume":             0.02,
    "noise_max_drift":              0.01,
}

CONTEXT_PENALTIES = {
    "exotic_league_penalty":     0.15,
    "low_snapshot_penalty":      0.10,
    "suspicious_volume_penalty": 0.10,
    "short_duration_penalty":    0.10,
}

LEAGUE_TIERS = {
    1: [
        "England Premier League", "Spain La Liga", "Germany Bundesliga",
        "Italy Serie A", "France Ligue 1", "UEFA Champions League",
        "UEFA Europa League", "UEFA Conference League",
    ],
    2: [
        "Netherlands Eredivisie", "Portugal Primeira Liga", "Turkey Super Lig",
        "Belgium First Division A", "Scotland Premiership", "Austria Bundesliga",
        "Switzerland Super League", "England Championship", "Spain Segunda",
        "Germany 2. Bundesliga", "Italy Serie B", "France Ligue 2",
    ],
    3: [
        "Denmark Superliga", "Norway Eliteserien", "Sweden Allsvenskan",
        "Greece Super League", "Czech First League", "Poland Ekstraklasa",
        "Croatia HNL", "Serbia Super Liga", "Romania Liga 1",
    ],
}

DEFAULT_LEAGUE_TIER = 4

VOLUME_BUCKETS = {
    1: (0, 50000),
    2: (50000, 200000),
    3: (200000, 500000),
    4: (500000, 1000000),
    5: (1000000, float("inf")),
}

TOP_SIMILAR_COUNT = 10
