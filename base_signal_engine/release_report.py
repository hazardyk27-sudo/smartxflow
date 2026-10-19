"""Local-only operator preflight report. Never deploys or self-approves."""
from __future__ import annotations

import argparse
import json
import sys

from .release_gate import render_offline_report


def main(argv=None) -> int:
    parser=argparse.ArgumentParser(description="SXF Base source-only NO-GO preflight")
    parser.add_argument("--manifest",help="optional local operator evidence JSON")
    parser.add_argument("--shadow",help="optional local shadow evidence JSONL")
    args=parser.parse_args(argv)
    result=render_offline_report(args.manifest,args.shadow)
    print(json.dumps(result,sort_keys=True,ensure_ascii=True))
    # The offline report has no authority to approve releases: it always
    # exits nonzero even when every self-declared check is supplied.
    return 2 if "INVALID_RELEASE_EVIDENCE" in result["blockers"] else 1


if __name__=="__main__":
    sys.exit(main())
