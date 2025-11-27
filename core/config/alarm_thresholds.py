"""
Alarm Threshold Configuration
Easily adjustable thresholds for Smart Money detection
"""

ALARM_CONFIG = {
    'sharp_money': {
        'min_money_inflow': 3000,
        'min_odds_drop': 0.03,
        'description': 'Sharp Money: £3,000+ para girisi + oran dususu'
    },
    
    'big_money': {
        'min_money_inflow': 15000,
        'time_window_minutes': 10,
        'description': 'Big Money: 10 dakika icinde £15,000+ para girisi (oran sarti yok)'
    },
    
    'rlm': {
        'min_money_inflow': 3000,
        'min_odds_up': 0.03,
        'description': 'Reverse Line Move: £3,000+ para girisi + ters yonde oran hareketi'
    },
    
    'momentum': {
        'consecutive_count': 3,
        'min_total_diff': 1000,
        'description': 'Sustained money flow in same direction'
    },
    
    'dropping': {
        'min_total_drop': 0.30,
        'min_money_pct': 60,
        'description': 'Significant odds drop from opening'
    },
    
    'line_freeze': {
        'max_odds_change': 0.02,
        'min_money_inflow': 1500,
        'description': 'Odds stable despite money inflow'
    },
    
    'public_surge': {
        'min_money_diff': 100,
        'max_odds_change': 0.02,
        'description': 'Public money - money up, odds flat'
    },
    
    'momentum_change': {
        'dominance_threshold': 50,
        'description': 'Dominance change - when >50% share switches to different option'
    }
}

def get_threshold(alarm_type: str, key: str, default=None):
    """Get a specific threshold value"""
    config = ALARM_CONFIG.get(alarm_type, {})
    return config.get(key, default)

def get_all_thresholds():
    """Get all thresholds for display/editing"""
    return ALARM_CONFIG.copy()
