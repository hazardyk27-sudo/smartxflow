"""Source-faithful Betwatch snapshot quote normalization.

An explicit numeric provider zero is evidence of zero bets, not missing data.
An omitted/null volume is unknown, NEVER a manufactured zero. Only source
observations with actual provider odds/volume can make a complete market.
"""
from __future__ import annotations
import math


def observed_snapshot_quote(runner: dict, value: float | None, total: float | None) -> tuple:
    """Return (odds,volume,share) from one actual provider runner only."""
    raw_odd=runner.get("odd")
    try:
        odd=float(raw_odd) if raw_odd not in (None,"") else None
        if odd is not None and (not math.isfinite(odd) or odd < 1):
            odd=None
    except (TypeError,ValueError,OverflowError):
        odd=None
    raw_volume=runner.get("volume")
    try:
        source_volume=float(raw_volume) if raw_volume not in (None,"") else None
        observed=(source_volume is not None and math.isfinite(source_volume)
                  and source_volume >= 0)
    except (TypeError,ValueError,OverflowError):
        observed=False
        source_volume=None
    volume=source_volume if observed else None
    try:
        denominator=float(total) if total is not None else None
        share=(round(source_volume / denominator * 100,1)
               if observed and denominator is not None
               and math.isfinite(denominator) and denominator > 0
               else (0.0 if observed and denominator == 0 and source_volume == 0 else None))
    except (TypeError,ValueError,OverflowError,ZeroDivisionError):
        share=None
    return odd,volume,share
