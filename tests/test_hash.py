#!/usr/bin/env python3
"""
Hash Sistemi Dogrulama Testleri
4 zorunlu test - hepsi gecmeli
CI'da her push'ta calisir
Bagimsiz - dis bagimlilik yok
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'core'))

from hash_utils import make_match_id_hash, normalize_field, normalize_kickoff


def test_a_same_match_two_scrapes():
    """Test A: Ayni mac, 2 scrape (10 dk arayla)"""
    print("\n" + "="*60)
    print("TEST A: Ayni mac, 2 scrape (10 dk arayla)")
    print("="*60)
    
    hash1 = make_match_id_hash(
        home="Manchester City",
        away="Arsenal",
        league="Premier League",
        kickoff_utc="2025-01-15T20:00:00Z",
        debug=True
    )
    
    hash2 = make_match_id_hash(
        home="Manchester City",
        away="Arsenal",
        league="Premier League",
        kickoff_utc="2025-01-15T20:00:00Z",
        debug=True
    )
    
    result = hash1 == hash2
    print(f"\nSONUC: {'OK' if result else 'FAIL'}")
    print(f"Run1: {hash1}")
    print(f"Run2: {hash2}")
    assert result, f"Hash mismatch: {hash1} != {hash2}"
    return result


def test_b_name_variation():
    """Test B: Ayni mac, isim varyasyonu - suffix stripped"""
    print("\n" + "="*60)
    print("TEST B: Ayni mac, isim varyasyonu (suffix stripped)")
    print("="*60)
    
    hash1 = make_match_id_hash(
        home="Galatasaray",
        away="Fenerbahce",
        league="Super Lig",
        kickoff_utc="2025-01-20T19:00:00Z",
        debug=True
    )
    
    hash2 = make_match_id_hash(
        home="GALATASARAY  ",
        away="  Fenerbahce",
        league="Super Lig",
        kickoff_utc="2025-01-20T19:00:00Z",
        debug=True
    )
    
    hash3 = make_match_id_hash(
        home="Galatasaray SK.",
        away="Fenerbahce FC",
        league="Super Lig!",
        kickoff_utc="2025-01-20T19:00:00Z",
        debug=True
    )
    
    result = hash1 == hash2 == hash3
    print(f"\nSONUC: {'OK' if result else 'FAIL'}")
    print(f"Var1 (clean): {hash1}")
    print(f"Var2 (spaces): {hash2}")
    print(f"Var3 (suffix): {hash3}")
    assert result, f"Hash mismatch: {hash1}, {hash2}, {hash3}"
    return result


def test_c_utc_tr_difference():
    """Test C: UTC/TR farki - timezone normalization"""
    print("\n" + "="*60)
    print("TEST C: UTC/TR farki")
    print("="*60)
    
    hash1 = make_match_id_hash(
        home="Liverpool",
        away="Chelsea",
        league="Premier League",
        kickoff_utc="2025-01-25T15:00:00Z",
        debug=True
    )
    
    hash2 = make_match_id_hash(
        home="Liverpool",
        away="Chelsea",
        league="Premier League",
        kickoff_utc="2025-01-25T15:00:00+00:00",
        debug=True
    )
    
    hash3 = make_match_id_hash(
        home="Liverpool",
        away="Chelsea",
        league="Premier League",
        kickoff_utc="2025-01-25T15:00",
        debug=True
    )
    
    result = hash1 == hash2 == hash3
    print(f"\nSONUC: {'OK' if result else 'FAIL'}")
    print(f"UTC Z: {hash1}")
    print(f"UTC +00:00: {hash2}")
    print(f"No seconds: {hash3}")
    assert result, f"Hash mismatch: {hash1}, {hash2}, {hash3}"
    return result


def test_d_join_test():
    """Test D: Join testi (simulasyon)"""
    print("\n" + "="*60)
    print("TEST D: Join testi (simulasyon)")
    print("="*60)
    
    fixture = {
        'match_id_hash': make_match_id_hash("Real Madrid", "Barcelona", "La Liga", "2025-02-01T20:00:00Z"),
        'home_team': "Real Madrid",
        'away_team': "Barcelona",
        'league': "La Liga",
        'kickoff_utc': "2025-02-01T20:00:00Z"
    }
    
    alarm = {
        'match_id_hash': make_match_id_hash("Real Madrid", "Barcelona", "La Liga", "2025-02-01T20:00:00Z"),
        'market': '1X2',
        'selection': '1',
        'alarm_type': 'volumeshock'
    }
    
    hash_match = fixture['match_id_hash'] == alarm['match_id_hash']
    assert hash_match, "Hash mismatch between fixture and alarm"
    
    joined = {
        **alarm,
        'home_team': fixture['home_team'],
        'away_team': fixture['away_team'],
        'league': fixture['league'],
        'kickoff_utc': fixture['kickoff_utc']
    }
    
    has_home = 'home_team' in joined and joined['home_team']
    has_away = 'away_team' in joined and joined['away_team']
    has_league = 'league' in joined and joined['league']
    has_kickoff = 'kickoff_utc' in joined and joined['kickoff_utc']
    
    result = has_home and has_away and has_league and has_kickoff
    print(f"\nSONUC: {'OK' if result else 'FAIL'}")
    assert result, "Missing metadata in joined record"
    return result


def run_all_tests():
    """Tum testleri calistir"""
    print("\n" + "#"*60)
    print("# HASH SISTEMI DOGRULAMA TESTLERI")
    print("#"*60)
    
    results = {
        'A': test_a_same_match_two_scrapes(),
        'B': test_b_name_variation(),
        'C': test_c_utc_tr_difference(),
        'D': test_d_join_test()
    }
    
    print("\n" + "="*60)
    print("OZET RAPOR")
    print("="*60)
    
    all_passed = all(results.values())
    
    for test, passed in results.items():
        status = "OK" if passed else "FAIL"
        print(f"Test {test}: {status}")
    
    print("\n" + "-"*60)
    final_status = "TUM TESTLER GECTI" if all_passed else "BAZI TESTLER BASARISIZ!"
    print(f"GENEL SONUC: {final_status}")
    print("-"*60)
    
    return all_passed


if __name__ == "__main__":
    success = run_all_tests()
    sys.exit(0 if success else 1)
