# SmartXFlow Release Flow

REFERENCE_VERSION: 2

Open only for GitHub/Replit/Hetzner sync, release or deployment work.

## Canonical roles

- GitHub tracked source/history is canonical.
- `preview` is development/Preview.
- `main` is the exact latest user-approved production SHA.
- Replit Preview only runs the exact GitHub `preview` tracked tree/history.
- Hetzner runs production; never edit production files in place.

## Required flow

1. Start from current `main`; make/test changes on `preview`.
2. Sync Replit Preview only to the exact GitHub `preview` SHA and obtain user Preview approval.
3. Before approval, never promote to `main` or deploy Hetzner/Replit Production.
4. After approval, fast-forward the exact approved `preview` SHA to `main`, then deploy/publish that exact `main` SHA.
5. Stop on ordinary divergence; no force-push, reset, rebase, cherry-pick or improvised merge around the guardrails.

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

A completed sync must verify repo/branch, requested SHA, clean tracked tree, final HEAD, ahead/behind `0/0`, tracked-file count and deterministic tracked-tree fingerprint.

### Replit-generated empty publish commit recovery

Replit publishing can create a local `Published your App` metadata commit whose tracked tree is identical to its parent. This can make Replit appear diverged even though no source changed.

Only for that exact case, and only with explicit sync/recovery intent from the user, the same canonical helper may be run with `SMARTXFLOW_ALLOW_EMPTY_PUBLISH_RECOVERY=1`. Recovery must fail closed unless every local-only commit:

- is single-parent,
- changes no tracked tree content compared with its parent, and
- is recognizably Replit-generated publish metadata.

The helper then creates a history-preserving two-parent commit whose tree is exactly the requested GitHub `preview` tree, rechecks that GitHub `preview` has not moved, pushes the recovery commit as a normal fast-forward, and fast-forwards the Replit workspace to it. No force-push, reset, rebase or cherry-pick is permitted. The resulting recovery SHA becomes the new canonical `preview` SHA and must finish at ahead/behind `0/0`.

Recovery invocation:

```bash
cd ~/workspace || exit 1
set -euo pipefail
EXPECTED="<EXACT_PREVIEW_SHA>"
curl -fsSL "https://raw.githubusercontent.com/hazardyk27-sudo/smartxflow/$EXPECTED/scripts/replit-sync-preview.sh" \
  | SMARTXFLOW_ALLOW_EMPTY_PUBLISH_RECOVERY=1 bash -s -- "$EXPECTED"
```

## Safety

Never operate on the user's personal computer. Remote desktop tooling may only bridge to explicitly authorized remote targets; all substantive work stays remote.
