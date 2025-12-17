#!/usr/bin/env python3
"""
Hash Sistemi Dogrulama Testleri
4 zorunlu test - hepsi gecmeli
"""

import sys
import os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from alarm_calculator import make_match_id_hash, normalize_field, normalize_kickoff

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
    print(f"\nScrape 1 Hash: {hash1}")
    
    hash2 = make_match_id_hash(
        home="Manchester City",
        away="Arsenal",
        league="Premier League",
        kickoff_utc="2025-01-15T20:00:00Z",
        debug=True
    )
    print(f"\nScrape 2 Hash: {hash2}")
    
    result = hash1 == hash2
    status = "OK - Hash ayni" if result else "FAIL - Hash farkli!"
    print(f"\nSONUC: {status}")
    print(f"Run1: {hash1}")
    print(f"Run2: {hash2}")
    return result


def test_b_name_variation():
    """Test B: Ayni mac, isim varyasyonu"""
    print("\n" + "="*60)
    print("TEST B: Ayni mac, isim varyasyonu")
    print("="*60)
    
    hash1 = make_match_id_hash(
        home="Galatasaray",
        away="Fenerbahce",
        league="Super Lig",
        kickoff_utc="2025-01-20T19:00:00Z",
        debug=True
    )
    print(f"\nVaryasyon 1 Hash: {hash1}")
    
    hash2 = make_match_id_hash(
        home="GALATASARAY  ",
        away="  Fenerbahce",
        league="Super Lig",
        kickoff_utc="2025-01-20T19:00:00Z",
        debug=True
    )
    print(f"\nVaryasyon 2 Hash: {hash2}")
    
    hash3 = make_match_id_hash(
        home="Galatasaray SK.",
        away="Fenerbahce FC",
        league="Super Lig!",
        kickoff_utc="2025-01-20T19:00:00Z",
        debug=True
    )
    print(f"\nVaryasyon 3 Hash: {hash3}")
    
    result = hash1 == hash2 == hash3
    status = "OK - Tum hashler ayni" if result else "FAIL - Hashler farkli!"
    print(f"\nSONUC: {status}")
    print(f"Var1: {hash1}")
    print(f"Var2: {hash2}")
    print(f"Var3: {hash3}")
    return result


def test_c_utc_tr_difference():
    """Test C: UTC/TR farki"""
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
    print(f"\nUTC (Z) Hash: {hash1}")
    
    hash2 = make_match_id_hash(
        home="Liverpool",
        away="Chelsea",
        league="Premier League",
        kickoff_utc="2025-01-25T15:00:00+00:00",
        debug=True
    )
    print(f"\nUTC (+00:00) Hash: {hash2}")
    
    hash3 = make_match_id_hash(
        home="Liverpool",
        away="Chelsea",
        league="Premier League",
        kickoff_utc="2025-01-25T15:00",
        debug=True
    )
    print(f"\nUTC (no seconds) Hash: {hash3}")
    
    result = hash1 == hash2 == hash3
    status = "OK - Tum hashler ayni" if result else "FAIL - Hashler farkli!"
    print(f"\nSONUC: {status}")
    print(f"UTC Z: {hash1}")
    print(f"UTC +00:00: {hash2}")
    print(f"No seconds: {hash3}")
    
    print("\n[UYARI] TR timezone test (FARKLI hash beklenir - bu dogru):")
    hash_tr = make_match_id_hash(
        home="Liverpool",
        away="Chelsea",
        league="Premier League",
        kickoff_utc="2025-01-25T18:00:00+03:00",
        debug=True
    )
    print(f"TR (+03:00) Hash: {hash_tr}")
    is_different = hash_tr != hash1
    print(f"TR hash UTC ye donusturulmeden gecirildi - FARKLI olmasi bekleniyor: {is_different}")
    
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
    print(f"\nFixture: {fixture}")
    
    alarm = {
        'match_id_hash': make_match_id_hash("Real Madrid", "Barcelona", "La Liga", "2025-02-01T20:00:00Z"),
        'market': '1X2',
        'selection': '1',
        'alarm_type': 'volumeshock'
    }
    print(f"Alarm: {alarm}")
    
    if fixture['match_id_hash'] == alarm['match_id_hash']:
        joined = {
            **alarm,
            'home_team': fixture['home_team'],
            'away_team': fixture['away_team'],
            'league': fixture['league'],
            'kickoff_utc': fixture['kickoff_utc']
        }
        print(f"\nJoined Record: {joined}")
        
        has_home = 'home_team' in joined and joined['home_team']
        has_away = 'away_team' in joined and joined['away_team']
        has_league = 'league' in joined and joined['league']
        has_kickoff = 'kickoff_utc' in joined and joined['kickoff_utc']
        
        result = has_home and has_away and has_league and has_kickoff
        status = "OK - Metadata eksiksiz" if result else "FAIL - Metadata eksik!"
        print(f"\nSONUC: {status}")
        print(f"  home_team: {'OK' if has_home else 'MISSING'}")
        print(f"  away_team: {'OK' if has_away else 'MISSING'}")
        print(f"  league: {'OK' if has_league else 'MISSING'}")
        print(f"  kickoff_utc: {'OK' if has_kickoff else 'MISSING'}")
        return result
    else:
        print("\nSONUC: FAIL - Hashler eslesmedi!")
        return False


def run_all_tests():
    """Tum testleri calistir ve rapor uret"""
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
