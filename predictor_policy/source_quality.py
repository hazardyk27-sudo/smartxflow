from __future__ import annotations

from urllib.parse import urlparse


# Deterministic, deliberately conservative registry used by the Stage 2 validator.
# Unknown domains are never allowed to self-promote to Tier A/B merely because the
# research worker labels them that way. Add a domain here only after review.
_TIER_A_DOMAINS = {
    "fifa.com",
    "uefa.com",
    "tff.org",
    "thefa.com",
    "premierleague.com",
    "laliga.com",
    "bundesliga.com",
    "legaseriea.it",
    "ligue1.com",
    "eredivisie.nl",
    "fpf.pt",
    "rfef.es",
    "dfb.de",
    "figc.it",
    "fff.fr",
    "knvb.nl",
    "shamrockrovers.ie",
    "fcucluj.ro",
}

_TIER_B_DOMAINS = {
    "reuters.com",
    "apnews.com",
    "bbc.com",
    "bbc.co.uk",
    "skysports.com",
    "theguardian.com",
    "espn.com",
    "theathletic.com",
}

_TIER_C_DOMAINS = {
    "flashscore.com",
    "flashscore.co.uk",
    "fotmob.com",
    "sofascore.com",
    "fbref.com",
    "soccerway.com",
    "mackolik.com",
    "besoccer.com",
    "transfermarkt.com",
}

_TIER_D_DOMAINS = {
    "facebook.com",
    "instagram.com",
    "x.com",
    "twitter.com",
    "tiktok.com",
    "youtube.com",
    "reddit.com",
}

# Maximum age of the underlying evidence at fixture kickoff. This is deliberately
# market-research oriented rather than a generic-news retention policy.
_CATEGORY_MAX_AGE_DAYS = {
    "LINEUP": 2,
    "SQUAD": 10,
    "MANAGER_COMMENT": 10,
    "PERFORMANCE": 45,
    "TACTICAL": 45,
    "CONTEXT": 120,
    "H2H": 730,
}


def normalize_source_host(source: str | None) -> str | None:
    raw = str(source or "").strip()
    if not raw:
        return None
    try:
        parsed = urlparse(raw)
    except ValueError:
        return None
    if parsed.scheme.lower() not in {"http", "https"} or not parsed.hostname:
        return None
    host = parsed.hostname.lower().rstrip(".")
    if host.startswith("www."):
        host = host[4:]
    return host or None


def _matches(host: str, domains: set[str]) -> bool:
    return any(host == domain or host.endswith("." + domain) for domain in domains)


def verified_source_tier(source: str | None) -> str | None:
    host = normalize_source_host(source)
    if host is None:
        return None
    if _matches(host, _TIER_A_DOMAINS):
        return "A"
    if _matches(host, _TIER_B_DOMAINS):
        return "B"
    if _matches(host, _TIER_C_DOMAINS):
        return "C"
    if _matches(host, _TIER_D_DOMAINS):
        return "D"
    # Fail closed: an unreviewed host cannot claim primary/high-reliability status.
    return "D"


def category_max_age_days(category: str | None) -> int | None:
    return _CATEGORY_MAX_AGE_DAYS.get(str(category or "").upper())


def registry_snapshot() -> dict[str, tuple[str, ...]]:
    return {
        "A": tuple(sorted(_TIER_A_DOMAINS)),
        "B": tuple(sorted(_TIER_B_DOMAINS)),
        "C": tuple(sorted(_TIER_C_DOMAINS)),
        "D": tuple(sorted(_TIER_D_DOMAINS)),
    }
