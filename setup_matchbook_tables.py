#!/usr/bin/env python3
"""
Matchbook Exchange tablolarini Supabase'de olusturur.
Bir kez calistirilmasi yeterlidir.
"""
import os
import sys
import httpx

def get_credentials():
    try:
        sys.path.insert(0, os.path.dirname(__file__))
        from services import embedded_credentials
        url = getattr(embedded_credentials, 'SUPABASE_URL', '')
        key = getattr(embedded_credentials, 'SUPABASE_KEY', '')
        if url and key:
            return url, key
    except:
        pass
    
    url = os.environ.get('SUPABASE_URL', '')
    key = os.environ.get('SUPABASE_ANON_KEY', '') or os.environ.get('SUPABASE_KEY', '')
    return url, key

def run_sql(url, key, sql):
    rpc_url = f"{url}/rest/v1/rpc/exec_sql"
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json"
    }
    resp = httpx.post(rpc_url, json={"query": sql}, headers=headers, timeout=30)
    if resp.status_code in [200, 201, 204]:
        print(f"  OK")
        return True
    else:
        print(f"  RPC failed ({resp.status_code}): {resp.text[:200]}")
        return False

def create_tables_via_rest(url, key):
    tables_sql = [
        ("matchbook_fixtures", """
CREATE TABLE IF NOT EXISTS matchbook_fixtures (
    id bigserial PRIMARY KEY,
    event_id bigint,
    home_team text NOT NULL,
    away_team text NOT NULL,
    league text DEFAULT '',
    kickoff_utc timestamptz,
    match_id_hash varchar(12),
    arbworld_hash varchar(12),
    meta_tags jsonb DEFAULT '[]'::jsonb,
    last_scraped timestamptz DEFAULT now(),
    created_at timestamptz DEFAULT now(),
    UNIQUE(event_id)
);
CREATE INDEX IF NOT EXISTS idx_mb_fix_hash ON matchbook_fixtures(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mb_fix_arb ON matchbook_fixtures(arbworld_hash);
CREATE INDEX IF NOT EXISTS idx_mb_fix_kickoff ON matchbook_fixtures(kickoff_utc);
"""),
        ("matchbook_1x2_history", """
CREATE TABLE IF NOT EXISTS matchbook_1x2_history (
    id bigserial PRIMARY KEY,
    home text NOT NULL,
    away text NOT NULL,
    league text DEFAULT '',
    date text DEFAULT '',
    match_id_hash varchar(12),
    arbworld_hash varchar(12),
    odds1 numeric,
    oddsx numeric,
    odds2 numeric,
    pct1 text DEFAULT '',
    pctx text DEFAULT '',
    pct2 text DEFAULT '',
    amt1 text DEFAULT '',
    amtx text DEFAULT '',
    amt2 text DEFAULT '',
    volume text DEFAULT '',
    odds1_prev text DEFAULT '',
    oddsx_prev text DEFAULT '',
    odds2_prev text DEFAULT '',
    trend1 text DEFAULT '',
    trendx text DEFAULT '',
    trend2 text DEFAULT '',
    scraped_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mb_1x2_hash ON matchbook_1x2_history(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mb_1x2_arb ON matchbook_1x2_history(arbworld_hash);
CREATE INDEX IF NOT EXISTS idx_mb_1x2_scraped ON matchbook_1x2_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_mb_1x2_home_away ON matchbook_1x2_history(home, away);
"""),
        ("matchbook_ou25_history", """
CREATE TABLE IF NOT EXISTS matchbook_ou25_history (
    id bigserial PRIMARY KEY,
    home text NOT NULL,
    away text NOT NULL,
    league text DEFAULT '',
    date text DEFAULT '',
    match_id_hash varchar(12),
    arbworld_hash varchar(12),
    under numeric,
    over numeric,
    line text DEFAULT '2.5',
    pctunder text DEFAULT '',
    pctover text DEFAULT '',
    amtunder text DEFAULT '',
    amtover text DEFAULT '',
    volume text DEFAULT '',
    under_prev text DEFAULT '',
    over_prev text DEFAULT '',
    trendunder text DEFAULT '',
    trendover text DEFAULT '',
    scraped_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mb_ou25_hash ON matchbook_ou25_history(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mb_ou25_arb ON matchbook_ou25_history(arbworld_hash);
CREATE INDEX IF NOT EXISTS idx_mb_ou25_scraped ON matchbook_ou25_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_mb_ou25_home_away ON matchbook_ou25_history(home, away);
"""),
        ("matchbook_btts_history", """
CREATE TABLE IF NOT EXISTS matchbook_btts_history (
    id bigserial PRIMARY KEY,
    home text NOT NULL,
    away text NOT NULL,
    league text DEFAULT '',
    date text DEFAULT '',
    match_id_hash varchar(12),
    arbworld_hash varchar(12),
    oddsyes numeric,
    oddsno numeric,
    pctyes text DEFAULT '',
    pctno text DEFAULT '',
    amtyes text DEFAULT '',
    amtno text DEFAULT '',
    volume text DEFAULT '',
    oddsyes_prev text DEFAULT '',
    oddsno_prev text DEFAULT '',
    trendyes text DEFAULT '',
    trendno text DEFAULT '',
    scraped_at timestamptz DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_mb_btts_hash ON matchbook_btts_history(match_id_hash);
CREATE INDEX IF NOT EXISTS idx_mb_btts_arb ON matchbook_btts_history(arbworld_hash);
CREATE INDEX IF NOT EXISTS idx_mb_btts_scraped ON matchbook_btts_history(scraped_at);
CREATE INDEX IF NOT EXISTS idx_mb_btts_home_away ON matchbook_btts_history(home, away);
"""),
        ("matchbook_league_map", """
CREATE TABLE IF NOT EXISTS matchbook_league_map (
    id bigserial PRIMARY KEY,
    matchbook_league text NOT NULL,
    arbworld_league text DEFAULT '',
    auto_matched boolean DEFAULT true,
    created_at timestamptz DEFAULT now(),
    UNIQUE(matchbook_league)
);
""")
    ]
    
    for table_name, sql in tables_sql:
        print(f"Creating {table_name}...")
        success = run_sql(url, key, sql)
        if not success:
            print(f"  Trying individual statements...")
            for stmt in sql.strip().split(';'):
                stmt = stmt.strip()
                if stmt:
                    run_sql(url, key, stmt + ';')

def try_direct_insert_test(url, key):
    headers = {
        "apikey": key,
        "Authorization": f"Bearer {key}",
        "Content-Type": "application/json",
        "Prefer": "return=representation"
    }
    test_url = f"{url}/rest/v1/matchbook_league_map?matchbook_league=eq.__test__"
    resp = httpx.get(test_url, headers=headers, timeout=10)
    if resp.status_code == 200:
        print("\n[OK] matchbook_league_map tablosu erisilebilir!")
        return True
    elif resp.status_code == 404:
        print(f"\n[WARN] Tablo bulunamadi (404) - SQL Editor'den manuel olusturmaniz gerekebilir")
        return False
    else:
        print(f"\n[WARN] Test sonucu: HTTP {resp.status_code}")
        return False

if __name__ == '__main__':
    url, key = get_credentials()
    if not url or not key:
        print("HATA: Supabase URL veya KEY bulunamadi!")
        sys.exit(1)
    
    print(f"Supabase URL: {url}")
    print(f"Supabase KEY: {key[:20]}...\n")
    
    create_tables_via_rest(url, key)
    
    print("\n--- Tablo Erisim Testi ---")
    try_direct_insert_test(url, key)
    
    print("\n[INFO] Eger tablolar olusturulamadiysa, asagidaki SQL'i Supabase SQL Editor'de calistirin:")
    print("  -> setup_matchbook_tables.py icindeki SQL ifadelerini kopyalayin")
