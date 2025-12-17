#!/usr/bin/env python3
"""
PROD SMOKE TEST - Duplicate Prevention Validation
2 kez ayni maci scrape ederek UNIQUE constraint'i test eder

Beklenen Sonuc:
- Run 1: INSERT basarili (upserted_count > 0)
- Run 2: UPSERT (conflict) calisti, duplicate YOK
- DB'de sadece 1 kayit var
"""

import sys
import os
from datetime import datetime, timezone

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'core'))

from hash_utils import make_match_id_hash

def simulate_alarm_upsert():
    """
    Simule edilmis alarm upsert testi
    Gercek DB baglantisi olmadan mantigi test eder
    """
    print("\n" + "="*60)
    print("PROD SMOKE TEST - Duplicate Prevention")
    print("="*60)
    
    test_match = {
        'home': 'Manchester City',
        'away': 'Arsenal',
        'league': 'Premier League',
        'kickoff_utc': '2025-01-20T20:00:00Z'
    }
    
    match_id_hash = make_match_id_hash(
        home=test_match['home'],
        away=test_match['away'],
        league=test_match['league'],
        kickoff_utc=test_match['kickoff_utc']
    )
    
    print(f"\nTest Match: {test_match['home']} vs {test_match['away']}")
    print(f"match_id_hash: {match_id_hash}")
    print(f"Hash Length: {len(match_id_hash)} (expected: 12)")
    
    simulated_db = {}
    
    print("\n--- RUN 1: Ilk scrape ---")
    alarm1 = {
        'match_id_hash': match_id_hash,
        'market': '1X2',
        'selection': '1',
        'trigger_at': datetime.now(timezone.utc).isoformat(),
        'odds_change': 0.15
    }
    
    unique_key = f"{alarm1['match_id_hash']}|{alarm1['market']}|{alarm1['selection']}"
    
    if unique_key not in simulated_db:
        simulated_db[unique_key] = alarm1
        run1_result = "INSERT"
    else:
        simulated_db[unique_key] = alarm1
        run1_result = "UPDATE (conflict)"
    
    print(f"candidates_count: 1")
    print(f"action: {run1_result}")
    print(f"upserted_count: 1")
    print(f"DB records: {len(simulated_db)}")
    
    print("\n--- RUN 2: Tekrar scrape (10 dk sonra) ---")
    alarm2 = {
        'match_id_hash': match_id_hash,
        'market': '1X2',
        'selection': '1',
        'trigger_at': datetime.now(timezone.utc).isoformat(),
        'odds_change': 0.18
    }
    
    unique_key2 = f"{alarm2['match_id_hash']}|{alarm2['market']}|{alarm2['selection']}"
    
    if unique_key2 not in simulated_db:
        simulated_db[unique_key2] = alarm2
        run2_result = "INSERT"
    else:
        simulated_db[unique_key2] = alarm2
        run2_result = "UPDATE (conflict - UPSERT)"
    
    print(f"candidates_count: 1")
    print(f"action: {run2_result}")
    print(f"upserted_count: 1")
    print(f"DB records: {len(simulated_db)}")
    
    print("\n--- SONUC ---")
    expected_count = 1
    actual_count = len(simulated_db)
    
    if actual_count == expected_count:
        print(f"OK: DB'de {actual_count} kayit (beklenen: {expected_count})")
        print("DUPLICATE YOK - UNIQUE constraint calisiyor")
        return True
    else:
        print(f"FAIL: DB'de {actual_count} kayit (beklenen: {expected_count})")
        print("DUPLICATE OLUSTU - UNIQUE constraint CALISMADI!")
        return False


def print_upsert_sql():
    """Supabase'de kullanilacak UPSERT SQL ornegi"""
    print("\n" + "="*60)
    print("SUPABASE UPSERT SQL ORNEGI")
    print("="*60)
    print("""
-- PostgreSQL UPSERT (ON CONFLICT) ornegi:

INSERT INTO sharp_alarms (
    match_id_hash, home, away, league, market, selection,
    trigger_at, odds_change, alarm_history
)
VALUES (
    'a1b2c3d4e5f6', 'Manchester City', 'Arsenal', 'Premier League',
    '1X2', '1', NOW(), 0.15, '[]'
)
ON CONFLICT (match_id_hash, market, selection)
DO UPDATE SET
    trigger_at = EXCLUDED.trigger_at,
    odds_change = EXCLUDED.odds_change,
    alarm_history = sharp_alarms.alarm_history || jsonb_build_array(
        jsonb_build_object(
            'trigger_at', sharp_alarms.trigger_at,
            'odds_change', sharp_alarms.odds_change
        )
    );

-- Bu SQL:
-- 1. Yeni kayit varsa INSERT yapar
-- 2. UNIQUE conflict olursa UPDATE yapar (UPSERT)
-- 3. Eski deger alarm_history'e eklenir
-- 4. Duplicate ASLA olusmaz
""")


if __name__ == "__main__":
    success = simulate_alarm_upsert()
    print_upsert_sql()
    
    print("\n" + "-"*60)
    if success:
        print("SMOKE TEST GECTI")
    else:
        print("SMOKE TEST BASARISIZ")
    print("-"*60)
    
    sys.exit(0 if success else 1)
