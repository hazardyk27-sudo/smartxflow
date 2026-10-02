#!/usr/bin/env python3
"""Read-only Analysis V2 provider-market capability audit.

Prints market names/counts only; never prints the API token.
"""

from collections import Counter
import json

from betwatch_client import fetch_prematch


def main():
    matches = fetch_prematch(timeout=40)
    counts = Counter()
    usable = Counter()

    for match in matches:
        for market in match.get("markets", []) or []:
            name = (market.get("name") or "").strip()
            counts[name] += 1
            runners = market.get("runners", []) or []
            if any(r.get("odd") or r.get("volume") for r in runners):
                usable[name] += 1

    print(f"matches={len(matches)}")
    for name, count in counts.most_common():
        print(json.dumps({
            "market": name,
            "events": count,
            "events_with_quote_or_volume": usable[name],
        }, ensure_ascii=False))

    dc = sum(v for k, v in counts.items() if k.lower().startswith("double chance"))
    dnb = sum(v for k, v in counts.items() if k.lower().startswith("draw no bet"))
    print(json.dumps({
        "analysis_v2": {
            "double_chance_events": dc,
            "draw_no_bet_events": dnb,
            "double_chance_real_data_available": dc > 0,
        }
    }, ensure_ascii=False))


if __name__ == "__main__":
    main()
