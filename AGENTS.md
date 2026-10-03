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

- **The user's personal computer must never be used as a work target.** Do not browse, inspect, read, write, modify, delete, enumerate, or otherwise interact with local PC files, folders, browser tabs/windows, applications, processes, settings, clipboard, personal data, or UI. Do not open browser tabs or GUI applications on the PC. Do not create notes, logs, scripts, downloads, or any other files on the PC. Do not make local configuration changes.
- **Desktop Commander / Remote Desktop Commander is allowed only as a transport bridge to authorized remote targets** such as Hetzner, Replit, GitHub, SmartXFlow APIs/data, databases, or other explicitly authorized cloud/server services. Commands issued through Desktop Commander must target the remote service/server and must not operate on the local PC, except for the minimal shell invocation strictly necessary to establish or maintain that outbound remote connection. Do not inspect the local machine as part of that process.
- When Desktop Commander is used as a bridge, keep all substantive reads, writes, searches, tests, code changes, data queries, and file operations on the remote target only. Never store intermediate or final artifacts on the local PC.
- Never overwrite or delete secrets, local `.env` files, logs, virtual environments, caches, uploads, or untracked runtime data during source sync.
- If refs, tracked trees, counts, or fingerprints diverge, stop and compare; never sync blindly.
- No force-push, rebase, reset, or improvised merge. Use only reviewed, controlled fast-forward/promotion; stop on divergence.