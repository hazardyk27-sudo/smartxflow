#!/bin/bash
pip install -r requirements.txt

# Deploy-only cleanup: archive/ holds ~105MB of legacy files (data dumps, old SQLs,
# unused scripts, log/exe under manual_review/). Not needed at runtime. This script
# only runs during Replit deploy build, NOT in the dev workspace. See
# docs/cleanup_audit_2026_05_03.md.
if [ -d "archive" ]; then
  echo "[build] Removing archive/ from deploy bundle ($(du -sh archive | cut -f1))..."
  rm -rf archive
fi

# Precompile our own Python source to .pyc during the build step. Without this,
# a fresh deploy VM compiles app.py (11k+ lines) and its local modules from
# scratch on first import -- on the constrained production machine (0.5 vCPU)
# this can add enough delay to the cold start that the promote-step health
# check on GET / times out before the server ever binds. .pythonlibs
# (third-party packages) already ships precompiled, so this only targets our
# own code. __pycache__/ is git-ignored, so it never survives a fresh deploy
# checkout without this step.
echo "[build] Precompiling application bytecode..."
python -m compileall -q -x '\.pythonlibs|__pycache__|node_modules|\.git|attached_assets|archive|static|templates|data/|sql|migrations|docs|screenshots|exports' . || true
