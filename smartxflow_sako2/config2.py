BLOCK_WEIGHTS = {
    "odds_1x2": 0.25,
    "odds_ou": 0.15,
    "odds_kg": 0.10,
    "money_distribution": 0.30,
    "total_volume": 0.20,
}

BLOCK_LABELS = {
    "odds_1x2": "1X2 Oranları",
    "odds_ou": "ÜA 2.5 Oranları",
    "odds_kg": "KG Oranları",
    "money_distribution": "Para Dağılımı",
    "total_volume": "Hacim",
}

HARD_FILTER = {
    "odds_1x2_max_diff": 0.60,
    "volume_ratio_max": 8.0,
    "league_tier_max_diff": 2,
    "min_data_quality": 0.30,
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
