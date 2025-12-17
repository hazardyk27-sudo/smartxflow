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
    
    # Fallback
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
