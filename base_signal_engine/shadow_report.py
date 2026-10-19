"""Offline Phase 5C shadow integrity report; no credentials or network access."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .shadow_evidence import _read, assess_shadow, ShadowEvidenceError


def main(argv=None) -> int:
    p=argparse.ArgumentParser(description="Offline SmartXFlow Base shadow evidence audit")
    p.add_argument("--evidence",required=True,help="local append-only JSONL file")
    p.add_argument("--min-hours",type=float,default=24.0)
    p.add_argument("--max-gap-seconds",type=int,default=180)
    p.add_argument("--max-pending-due",type=int,default=250)
    p.add_argument("--max-review-required",type=int,default=0)
    args=p.parse_args(argv)
    try:
        records=_read(Path(args.evidence))
        assessment=assess_shadow(
            records,min_duration_hours=args.min_hours,
            max_gap_seconds=args.max_gap_seconds,
            max_pending_due=args.max_pending_due,
            max_review_required=args.max_review_required)
        if not records:
            assessment["blockers"]=sorted(set(assessment["blockers"]+
                                              ["NO_EVIDENCE_FILE_OR_RECORDS"]))
            assessment["meets_observation_gates"]=False
    except (ShadowEvidenceError,ValueError,TypeError) as exc:
        # Do not print raw evidence, file content, secrets or exception messages.
        print(json.dumps({"status":"INVALID_EVIDENCE",
                          "error_type":type(exc).__name__,
                          "production_approved":False},sort_keys=True))
        return 2
    print(json.dumps({"status":"OBSERVATION_REVIEW",
                      **assessment},sort_keys=True))
    return 0 if assessment["meets_observation_gates"] else 1


if __name__=="__main__":
    sys.exit(main())
