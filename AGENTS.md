# SmartXFlow Repository Rules

**Repository:** `hazardyk27-sudo/smartxflow`. This root file is binding for agents and overrides conflicting legacy deployment notes.

## Agent instruction loading

- Every new agent/session must read this `AGENTS.md` once before substantive work and keep the rules in session context.
- Do not reread this file for routine tasks after it has been loaded once in the same session.
- Reread it only when one of these conditions is true: the user says repository rules changed, the `AGENTS.md` blob/SHA changed, the repository or branch context changed, or an instruction conflict/ambiguity appears.
- If the file changes during an active session, the newer version becomes authoritative immediately after rereading it.

## Specialized agent bootstrap

- `SXF-MATCH-ANALYST` starts the dedicated daily football Match Analyst role.
- On a new Match Analyst session, after reading this root file once, read `.agents/roles/MATCH_ANALYST.md` and then follow its bootstrap order for methodology, source policy, output/postmortem standards, and state.
- Specialized role files are session-cached the same way as this root file: read once per session, and reread only if their SHA/rules change, the repository/branch changes, or an instruction conflict appears.
- The Match Analyst is a research/prediction role only. It must not independently edit/deploy SmartXFlow application code or promote research observations into production engine rules.

## Source and environment roles

- GitHub-tracked source and history are canonical.
- `main` identifies the latest user-approved production SHA; `preview` is the development and Preview branch.
- GitHub stores source and history.
- The Replit workspace is only a runner for the exact GitHub `preview` SHA; do not make independent code changes there.
- Replit Production may publish only an explicitly approved `main` SHA.
- Hetzner hosts the production backend/runtime. Never edit production files in place.

## Required release flow

1. Start from current `main`; make and test changes on `preview`.
2. Sync the Replit workspace to the exact GitHub `preview` SHA and obtain the user's Preview approval.
3. Before approval, do not promote to `main` or deploy to Hetzner.
4. After approval, promote that exact `preview` SHA to `main` using a controlled fast-forward only. Deploy the exact resulting `main` SHA to Hetzner and publish that same SHA to Replit Production.
5. A release is complete only when GitHub `main`, Replit Production, and Hetzner report the same exact Git SHA, clean tracked trees, tracked-file counts, and deterministic full-tree SHA256 fingerprints. Before approval, verify the Replit workspace matches the exact `preview` SHA.
6. Fingerprint method: bytewise-sort paths from `git ls-files -z`; for each path, append path bytes, NUL, the raw 32-byte SHA256 digest of its file bytes, and NUL; SHA256 the resulting stream. For symlinks, hash the link-target bytes.

## Replit Preview sync policy

- **Never use Replit Agent to transfer, apply, merge, rewrite, or synchronize GitHub changes into Replit Preview.** Replit Agent must not be asked to edit source as part of preview synchronization.
- Replit Preview synchronization is performed only from the Replit Shell through the canonical helper `scripts/replit-sync-preview.sh`.
- Every sync must target one exact 40-character GitHub `preview` commit SHA. Never sync by trusting only a moving branch name.
- The one canonical Replit Shell invocation is:

```bash
cd ~/workspace || exit 1
set -euo pipefail
EXPECTED="<EXACT_PREVIEW_SHA>"
curl -fsSL "https://raw.githubusercontent.com/hazardyk27-sudo/smartxflow/$EXPECTED/scripts/replit-sync-preview.sh" \
  | bash -s -- "$EXPECTED"
```

- When the user asks for the Replit shell code, provide only this canonical command shape with the current exact `preview` SHA substituted for `<EXACT_PREVIEW_SHA>`; do not provide alternative manual git sync recipes.
- After every completed part or operation that creates a new GitHub `preview` commit, report the exact resulting `preview` SHA and include the canonical Replit Shell command so the user can transfer that change to Replit.
- If a completed part creates no tracked source change, explicitly say that no Replit sync is required instead of inventing a new SHA.
- If the canonical helper stops because of a dirty tracked tree, wrong repo, wrong branch, remote mismatch, divergence, or SHA mismatch, stop and resolve that cause first. Do not bypass it with `git pull`, manual merge, rebase, checkout, reset, cherry-pick, force operations, or ad-hoc commands.
- The canonical helper may only synchronize tracked source by controlled fast-forward and verify the result. It must preserve untracked runtime files and must never run database migrations, cleanup, delete, truncate, schema push, retention maintenance, or other destructive data operations.
- A successful sync must verify at least: correct repository, `preview` branch, exact requested SHA equals GitHub `preview`, tracked tree clean before/after, fast-forward-only ancestry, final `HEAD`, ahead/behind `0/0`, tracked file count, and deterministic tracked-tree SHA256 fingerprint. A health check may run only through a configured non-destructive health URL.

## Safety rules

- **The user's personal computer must never be used as a work target.** Do not browse, inspect, read, write, modify, delete, enumerate, or otherwise interact with local PC files, folders, browser tabs/windows, applications, processes, settings, clipboard, personal data, or UI. Do not open browser tabs or GUI applications on the PC. Do not create notes, logs, scripts, downloads, or any other files on the PC. Do not make local configuration changes.
- **Desktop Commander / Remote Desktop Commander is allowed only as a transport bridge to authorized remote targets** such as Hetzner, Replit, GitHub, SmartXFlow APIs/data, databases, or other explicitly authorized cloud/server services. Commands issued through Desktop Commander must target the remote service/server and must not operate on the local PC, except for the minimal shell invocation strictly necessary to establish or maintain that outbound remote connection. Do not inspect the local machine as part of that process.
- When Desktop Commander is used as a bridge, keep all substantive reads, writes, searches, tests, code changes, data queries, and file operations on the remote target only. Never store intermediate or final artifacts on the local PC.
- Never overwrite or delete secrets, local `.env` files, logs, virtual environments, caches, uploads, or untracked runtime data during source sync.
- If refs, tracked trees, counts, or fingerprints diverge, stop and compare; never sync blindly.
- No force-push, rebase, reset, or improvised merge. Use only reviewed, controlled fast-forward/promotion; stop on divergence.
