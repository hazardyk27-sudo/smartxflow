#!/usr/bin/env bash
set -euo pipefail

EXPECTED_SHA="${1:-}"
REPO_SLUG="hazardyk27-sudo/smartxflow"
TARGET_BRANCH="preview"

stop() {
  echo "STOP: $*" >&2
  exit 1
}

[[ "$EXPECTED_SHA" =~ ^[0-9a-f]{40}$ ]] || stop "expected exact 40-character preview SHA as the only argument"

git rev-parse --is-inside-work-tree >/dev/null 2>&1 || stop "not inside a git worktree"
ROOT="$(git rev-parse --show-toplevel)"
cd "$ROOT"

REMOTE=""
while IFS= read -r candidate; do
  url="$(git remote get-url "$candidate" 2>/dev/null || true)"
  case "$url" in
    *github.com:*"$REPO_SLUG"|*github.com:*"$REPO_SLUG.git"|*github.com/*"$REPO_SLUG"|*github.com/*"$REPO_SLUG.git")
      REMOTE="$candidate"
      break
      ;;
  esac
done < <(git remote)

[ -n "$REMOTE" ] || stop "no git remote points to $REPO_SLUG"

BRANCH="$(git branch --show-current)"
[ "$BRANCH" = "$TARGET_BRANCH" ] || stop "workspace branch is '$BRANCH'; expected '$TARGET_BRANCH'"

if ! git diff --quiet || ! git diff --cached --quiet; then
  echo "TRACKED_STATUS_BEGIN" >&2
  git status --short --untracked-files=no >&2 || true
  echo "TRACKED_STATUS_END" >&2
  stop "tracked worktree/index is not clean"
fi

HEAD_BEFORE="$(git rev-parse HEAD)"

echo "READONLY_GUARD: tracked files must be clean; untracked runtime files are preserved"
echo "REPOSITORY: $REPO_SLUG"
echo "REMOTE: $REMOTE"
echo "BRANCH: $BRANCH"
echo "HEAD_BEFORE: $HEAD_BEFORE"
echo "EXPECTED_PREVIEW_SHA: $EXPECTED_SHA"

git fetch --no-tags "$REMOTE" "refs/heads/$TARGET_BRANCH:refs/remotes/$REMOTE/$TARGET_BRANCH"

REMOTE_SHA="$(git rev-parse "refs/remotes/$REMOTE/$TARGET_BRANCH")"
[ "$REMOTE_SHA" = "$EXPECTED_SHA" ] || stop "GitHub preview is $REMOTE_SHA, not requested $EXPECTED_SHA"

git cat-file -e "$EXPECTED_SHA^{commit}" 2>/dev/null || stop "expected SHA is not a commit"

if [ "$HEAD_BEFORE" != "$EXPECTED_SHA" ]; then
  git merge-base --is-ancestor "$HEAD_BEFORE" "$EXPECTED_SHA" || stop "local preview has diverged from the requested preview SHA"
  git merge --ff-only "$EXPECTED_SHA"
fi

HEAD_AFTER="$(git rev-parse HEAD)"
[ "$HEAD_AFTER" = "$EXPECTED_SHA" ] || stop "HEAD after sync is $HEAD_AFTER, expected $EXPECTED_SHA"

TRACKED_STATUS="$(git status --porcelain --untracked-files=no)"
[ -z "$TRACKED_STATUS" ] || stop "tracked worktree is not clean after sync"

AHEAD_BEHIND="$(git rev-list --left-right --count HEAD..."refs/remotes/$REMOTE/$TARGET_BRANCH")"
[ "$AHEAD_BEHIND" = $'0\t0' ] || stop "HEAD and remote preview differ: $AHEAD_BEHIND"

TRACKED_COUNT="$(git ls-files -z | python3 -c 'import sys; data=sys.stdin.buffer.read(); print(sum(1 for x in data.split(b"\0") if x))')"

TREE_FINGERPRINT="$(python3 - <<'PY'
import hashlib
import os
import subprocess

paths = [p for p in subprocess.check_output(["git", "ls-files", "-z"]).split(b"\0") if p]
paths.sort()
out = hashlib.sha256()
for path_b in paths:
    path = os.fsdecode(path_b)
    if os.path.islink(path):
        data = os.fsencode(os.readlink(path))
    else:
        with open(path, "rb") as fh:
            data = fh.read()
    out.update(path_b)
    out.update(b"\0")
    out.update(hashlib.sha256(data).digest())
    out.update(b"\0")
print(out.hexdigest())
PY
)"

HEALTHCHECK="not-configured"
if [ -n "${SMARTXFLOW_PREVIEW_HEALTH_URL:-}" ]; then
  curl -fsS --max-time 15 "$SMARTXFLOW_PREVIEW_HEALTH_URL" >/dev/null || stop "health check failed: $SMARTXFLOW_PREVIEW_HEALTH_URL"
  HEALTHCHECK="ok:$SMARTXFLOW_PREVIEW_HEALTH_URL"
fi

echo "SYNC OK"
echo "BRANCH: $BRANCH"
echo "HEAD: $HEAD_AFTER"
echo "REMOTE_PREVIEW: $REMOTE_SHA"
echo "AHEAD_BEHIND: $AHEAD_BEHIND"
echo "TRACKED_STATUS: clean"
echo "TRACKED_FILE_COUNT: $TRACKED_COUNT"
echo "TREE_SHA256: $TREE_FINGERPRINT"
echo "HEALTHCHECK: $HEALTHCHECK"
