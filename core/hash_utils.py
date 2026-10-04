#!/usr/bin/env python3
"""Canonical SmartXFlow match identity helpers.

Stable `match_id_hash` contract:
    md5("<league_norm>|<home_norm>|<away_norm>")[:12]

Kickoff deliberately stays out of `match_id_hash` for backward compatibility.
Use `make_fixture_identity_key()` when deciding whether two fixture rows are the
same physical match; that key also includes canonical kickoff minute.
"""

import hashlib
import re
from datetime import datetime, timezone


def normalize_field(value: str) -> str:
    """Normalize team/league text for canonical match identity."""
    if not value:
        return ""

    value = str(value).strip()
    tr_map = {
        "ş": "s", "Ş": "S", "ğ": "g", "Ğ": "G", "ü": "u", "Ü": "U",
        "ı": "i", "İ": "I", "ö": "o", "Ö": "O", "ç": "c", "Ç": "C",
    }
    for tr_char, en_char in tr_map.items():
        value = value.replace(tr_char, en_char)

    value = value.lower()
    value = re.sub(r"[^a-z0-9\s]", "", value)
    value = " ".join(value.split())

    suffixes = ("fc", "fk", "sk", "sc", "afc", "cf", "ac", "as")
    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            token = " " + suffix
            if value.endswith(token):
                value = value[:-len(token)].strip()
                changed = True
                break
    return value


def normalize_kickoff(kickoff: str) -> str:
    """Legacy-compatible kickoff normalizer retained for existing callers."""
    if not kickoff:
        return ""
    kickoff = str(kickoff).strip()
    kickoff = re.sub(r"[+-]\d{2}:\d{2}$", "", kickoff)
    kickoff = kickoff.replace("Z", "")
    if "T" in kickoff and len(kickoff) >= 16:
        return kickoff[:16]

    month_map = {
        "jan": "01", "feb": "02", "mar": "03", "apr": "04",
        "may": "05", "jun": "06", "jul": "07", "aug": "08",
        "sep": "09", "oct": "10", "nov": "11", "dec": "12",
    }
    match = re.match(r"^(\d{1,2})\.([A-Za-z]{3})\s+(\d{1,2}):(\d{2})", kickoff)
    if match:
        day = match.group(1).zfill(2)
        month = month_map.get(match.group(2).lower(), "01")
        hour = match.group(3).zfill(2)
        minute = match.group(4)
        year = datetime.now(timezone.utc).year
        return f"{year}-{month}-{day}T{hour}:{minute}"

    if len(kickoff) >= 10 and kickoff[4] == "-":
        return kickoff[:16] if len(kickoff) >= 16 else kickoff[:10] + "T00:00"
    return kickoff


def normalize_kickoff_identity(kickoff: str) -> str:
    """Normalize ISO kickoff variants to one UTC minute for duplicate detection."""
    if not kickoff:
        return ""
    raw = str(kickoff).strip()
    try:
        parsed = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        if parsed.tzinfo is not None:
            parsed = parsed.astimezone(timezone.utc)
        parsed = parsed.replace(second=0, microsecond=0)
        if parsed.tzinfo is not None:
            return parsed.strftime("%Y-%m-%dT%H:%MZ")
        return parsed.strftime("%Y-%m-%dT%H:%M")
    except (TypeError, ValueError):
        return normalize_kickoff(raw)


def make_match_id_hash(home: str, away: str, league: str, kickoff_utc: str = None, debug: bool = False) -> str:
    """Generate the canonical 12-character match hash.

    `kickoff_utc` remains accepted for backward compatibility but is
    intentionally not part of the stable hash contract.
    """
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    canonical = f"{league_norm}|{home_norm}|{away_norm}"
    if debug:
        print(f"  Home: '{home}' -> '{home_norm}'")
        print(f"  Away: '{away}' -> '{away_norm}'")
        print(f"  League: '{league}' -> '{league_norm}'")
        print(f"  Canonical: '{canonical}'")
    return hashlib.md5(canonical.encode("utf-8")).hexdigest()[:12]


def make_fixture_identity_key(home: str, away: str, league: str, kickoff_utc: str):
    """Return a physical-fixture dedupe key, or None if identity is incomplete."""
    home_norm = normalize_field(home)
    away_norm = normalize_field(away)
    league_norm = normalize_field(league)
    kickoff_norm = normalize_kickoff_identity(kickoff_utc)
    if not home_norm or not away_norm or not league_norm or not kickoff_norm:
        return None
    return league_norm, home_norm, away_norm, kickoff_norm
