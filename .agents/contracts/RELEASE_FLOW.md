# SmartXFlow Release Flow

REFERENCE_VERSION: 1

Open only for GitHub/Replit/Hetzner sync, release or deployment work.

## Canonical roles

- GitHub tracked source/history is canonical.
- `preview` is development/Preview.
- `main` is the exact latest user-approved production SHA.
- Replit Preview only runs the exact GitHub `preview` SHA.
- Hetzner runs production; never edit production files in place.

## Required flow

1. Start from current `main`; make/test changes on `preview`.
2. Sync Replit Preview only to the exact GitHub `preview` SHA and obtain user Preview approval.
3. Before approval, never promote to `main` or deploy Hetzner/Replit Production.
4. After approval, fast-forward the exact approved `preview` SHA to `main`, then deploy/publish that exact `main` SHA.
5. Stop on divergence; no force-push, reset, rebase, cherry-pick or improvised merge around the guardrails.

## Replit Preview synchronization

Never use Replit Agent for source transfer/edit/sync. Use only the canonical helper from Replit Shell against an exact 40-character `preview` SHA:

```bash
cd ~/workspace || exit 1
set -euo pipefail
EXPECTED="<EXACT_PREVIEW_SHA>"
curl -fsSL "https://raw.githubusercontent.com/hazardyk27-sudo/smartxflow/$EXPECTED/scripts/replit-sync-preview.sh" \
  | bash -s -- "$EXPECTED"
```

The helper must preserve untracked runtime data and must not perform migrations, cleanup, delete/truncate or other destructive data operations.

A completed sync must verify repo/branch, requested SHA, clean tracked tree, fast-forward ancestry, final HEAD, ahead/behind `0/0`, tracked-file count and deterministic tracked-tree fingerprint.

## Safety

Never operate on the user's personal computer. Remote desktop tooling may only bridge to explicitly authorized remote targets; all substantive work stays remote.
