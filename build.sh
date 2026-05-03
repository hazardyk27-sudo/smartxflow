#!/bin/bash
pip install -r requirements.txt
python -m playwright install chromium

# Deploy-only cleanup: archive/ holds ~105MB of legacy files (data dumps, old SQLs,
# unused scripts, log/exe under manual_review/). Not needed at runtime. This script
# only runs during Replit deploy build, NOT in the dev workspace. See
# docs/cleanup_audit_2026_05_03.md.
if [ -d "archive" ]; then
  echo "[build] Removing archive/ from deploy bundle ($(du -sh archive | cut -f1))..."
  rm -rf archive
fi
