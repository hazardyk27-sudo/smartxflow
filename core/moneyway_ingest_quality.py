"""Pure per-batch Moneyway snapshot completeness telemetry (no DB access).

This module never fills, interpolates, or rewrites an odds/volume/share field.
It describes what the *scraper actually emitted* so production can distinguish
incomplete provider markets from non-atomic source writes.
"""
from __future__ import annotations

from collections import defaultdict
from typing import Mapping, Sequence

EXPECTED = {
    "1X2": frozenset(("1", "X", "2")),
    "OU25": frozenset(("O", "U")),
    "BTTS": frozenset(("Y", "N")),
}


def summarize_ingest_quality(rows: Sequence[Mapping]) -> dict[str, dict[str, int]]:
    groups = defaultdict(list)
    for row in rows:
        market = row.get("market")
        if market not in EXPECTED:
            continue
        # The tuple is only a batch-local diagnostic, NOT a fixture identity.
        # Grouping by UUID where present avoids rematch hash collisions.
        key = (str(row.get("fixture_uid") or row.get("match_id_hash") or ""),
               market, str(row.get("scraped_at_utc") or ""))
        groups[key].append(row)
    result = {market: {"groups":0,"complete":0,"missing_sides":0,
                       "duplicate_sides":0,"invalid_fields":0,"bad_share_sum":0}
              for market in EXPECTED}
    for (_,market,_), parts in groups.items():
        output=result[market]
        output["groups"]+=1
        selections=[str(r.get("selection") or "") for r in parts]
        if len(selections)!=len(set(selections)):
            output["duplicate_sides"]+=1
            continue
        if set(selections)!=EXPECTED[market]:
            output["missing_sides"]+=1
            continue
        if any(r.get(field) is None for r in parts for field in ("odds","volume","share")):
            output["invalid_fields"]+=1
            continue
        try:
            if abs(sum(float(r["share"]) for r in parts)-100.0)>0.5:
                output["bad_share_sum"]+=1
                continue
        except (ValueError,TypeError):
            output["invalid_fields"]+=1
            continue
        output["complete"]+=1
    return result
