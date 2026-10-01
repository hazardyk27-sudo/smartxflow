# SmartXFlow Repository Rules

**Repository:** `hazardyk27-sudo/smartxflow`. This root file is binding for agents and overrides conflicting legacy deployment notes.

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

## Safety rules

- Never overwrite or delete secrets, local `.env` files, logs, virtual environments, caches, uploads, or untracked runtime data during source sync.
- If refs, tracked trees, counts, or fingerprints diverge, stop and compare; never sync blindly.
- No force-push, rebase, reset, or improvised merge. Use only reviewed, controlled fast-forward/promotion; stop on divergence.