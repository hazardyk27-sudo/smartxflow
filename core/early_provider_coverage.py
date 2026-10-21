"""Pure live Betwatch Early Money source-availability telemetry.

One READ-ONLY aggregate of the existing authoritative prematch GET payload;
no second scraper, no added provider request, no synthetic odds or market side.
"""
from __future__ import annotations
from datetime import datetime,timezone
import math


_BUCKETS=((0,24,"T0_24"),(24,40,"T24_40"),(40,60,"T40_60"),
          (60,72,"T60_72"),(72,96,"T72_96"),(96,float("inf"),"T96_PLUS"))


def _real_number(value, *, minimum):
    if value in (None,""):
        return None
    try:
        f=float(value)
        return f if math.isfinite(f) and f>=minimum else None
    except (ValueError,TypeError,OverflowError):
        return None


def summarize_early_provider_coverage(matches, *, now: datetime, map_market):
    if now.tzinfo is None:
        raise ValueError("UTC-aware source observation required")
    now=now.astimezone(timezone.utc)
    if not callable(map_market):
        raise ValueError("authoritative outcome mapper required")
    report={bucket:{"fixtures":0,"market_present":0,"fully_priced":0,
                    "partially_priced":0,"no_priced_sides":0,
                    "missing_market":0,"runner_field_missing":0}
            for _,_,bucket in _BUCKETS}
    for event in matches:
        if not isinstance(event,dict):
            continue
        raw=event.get("kickoff")
        try:
            kickoff=datetime.fromisoformat(str(raw).replace("Z","+00:00"))
            if kickoff.tzinfo is None:
                continue
            h=(kickoff.astimezone(timezone.utc)-now).total_seconds()/3600
        except (ValueError,TypeError,OverflowError):
            continue
        bucket=next((label for low,high,label in _BUCKETS
                     if low<=h<high),None)
        if bucket is None:
            continue
        stats=report[bucket]
        stats["fixtures"]+=1
        teams=event.get("teams") or {}
        if not isinstance(teams,dict):
            teams={}
        market=next((m for m in (event.get("markets") or [])
                     if isinstance(m,dict) and m.get("name")=="Match Odds"),None)
        if market is None:
            stats["missing_market"]+=1
            continue
        stats["market_present"]+=1
        key,mapped=map_market("Match Odds",market.get("runners") or [],
                              home=teams.get("v1"),away=teams.get("v2"))
        if key!="1X2":
            mapped=[]
        sides={side:runner for side,runner in mapped
               if side in ("1","X","2") and isinstance(runner,dict)}
        priced=0
        total=0.0
        for side in ("1","X","2"):
            runner=sides.get(side)
            if not runner:
                stats["runner_field_missing"]+=1
                continue
            odds=_real_number(runner.get("odd"),minimum=1)
            amount=_real_number(runner.get("volume"),minimum=0)
            if odds is None or amount is None:
                stats["runner_field_missing"]+=1
                continue
            priced+=1
            total+=amount
        if priced==3 and total>0:
            stats["fully_priced"]+=1
        elif priced>0:
            stats["partially_priced"]+=1
        else:
            stats["no_priced_sides"]+=1
    return report
