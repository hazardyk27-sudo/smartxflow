#!/usr/bin/env python3
"""
Hash Utilities - Minimal, standalone hash functions
No external dependencies - only hashlib and re (built-in)
"""

import hashlib
import re


def normalize_field(value: str) -> str:
    """
    String normalizasyonu:
    1. Trim
    2. Turkce karakter normalizasyonu
    3. Lowercase
    4. Ozel karakterleri kaldir
    5. Coklu bosluk -> tek bosluk
    6. Suffix kaldir (FC, SK, etc.)
    """
    if not value:
        return ""
    
    value = value.strip()
    
    # Turkce karakter normalizasyonu
    tr_map = {
        'ş': 's', 'Ş': 'S',
        'ğ': 'g', 'Ğ': 'G',
        'ü': 'u', 'Ü': 'U',
        'ı': 'i', 'İ': 'I',
        'ö': 'o', 'Ö': 'O',
        'ç': 'c', 'Ç': 'C'
    }
    for tr_char, en_char in tr_map.items():
        value = value.replace(tr_char, en_char)
    
    value = value.lower()
    
    # Ozel karakterleri kaldir (sadece harf, rakam, bosluk)
    value = re.sub(r'[^a-z0-9\s]', '', value)
    value = ' '.join(value.split())
    
    # Suffix kaldir (birden fazla kez kontrol et)
    suffixes = ['fc', 'fk', 'sk', 'sc', 'afc', 'cf', 'ac', 'as']
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if value.endswith(' ' + suffix):
                value = value[:-len(suffix)-1].strip()
                changed = True
                break
    
    return value


def normalize_kickoff(kickoff: str) -> str:
    """
    Kickoff normalizasyonu:
    Hedef: YYYY-MM-DDTHH:MM (UTC, saniye yok)
    
    Desteklenen formatlar:
    1. ISO 8601: "2025-12-21T13:30:00+00:00" -> "2025-12-21T13:30"
    2. History format: "21.Dec 13:30:00" -> "2025-12-21T13:30"
    """
    if not kickoff:
        return ""
    
    kickoff = str(kickoff).strip()
    
    # Timezone offset'leri kaldir
    kickoff = re.sub(r'[+-]\d{2}:\d{2}$', '', kickoff)
    kickoff = kickoff.replace('Z', '')
    
    # ISO 8601 formati: ilk 16 karakter
    if 'T' in kickoff and len(kickoff) >= 16:
        return kickoff[:16]
    
    # History format: "21.Dec 13:30:00" veya "21.Dec 13:30"
    month_map = {
        'jan': '01', 'feb': '02', 'mar': '03', 'apr': '04',
        'may': '05', 'jun': '06', 'jul': '07', 'aug': '08',
        'sep': '09', 'oct': '10', 'nov': '11', 'dec': '12'
    }
    
    history_match = re.match(r'^(\d{1,2})\.([A-Za-z]{3})\s+(\d{1,2}):(\d{2})', kickoff)
    if history_match:
        day = history_match.group(1).zfill(2)
        month_str = history_match.group(2).lower()
        hour = history_match.group(3).zfill(2)
        minute = history_match.group(4)
        
        month = month_map.get(month_str, '01')
        
        from datetime import datetime
        current_year = datetime.utcnow().year
        
        return f"{current_year}-{month}-{day}T{hour}:{minute}"
    
    # Fallback: YYYY-MM-DD format
    if len(kickoff) >= 10 and kickoff[4] == '-':
        return kickoff[:16] if len(kickoff) >= 16 else kickoff[:10] + "T00:00"
    
    return kickoff


def make_match_id_hash(home: str, away: str, league: str, kickoff_utc: str, debug: bool = False) -> str:
    """
    12 karakterlik MD5 hash uret
    Format: league|kickoff|home|away
    """
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    kickoff_norm = normalize_kickoff(kickoff_utc)
    
    canonical = f"{league_norm}|{kickoff_norm}|{home_norm}|{away_norm}"
    
    if debug:
        print(f"  Home: '{home}' -> '{home_norm}'")
        print(f"  Away: '{away}' -> '{away_norm}'")
        print(f"  League: '{league}' -> '{league_norm}'")
        print(f"  Kickoff: '{kickoff_utc}' -> '{kickoff_norm}'")
        print(f"  Canonical: '{canonical}'")
    
    return hashlib.md5(canonical.encode('utf-8')).hexdigest()[:12]
