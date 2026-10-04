---
name: Web workflow reload behavior
description: How to verify that a running Python web process has loaded recent service-module changes.
---

When runtime behavior disagrees with current source, compare the active web process start time with the commit or source-file modification time. The SmartXFlow Web `REPL_DEPLOYMENT=1 python app.py` workers did not reload an imported service module after its source changed; periodic cache warmups continued to use the already-loaded code.

**Why:** Python processes retain imported modules in memory. Refreshing an application-data cache does not reload code.

**How to apply:** Check the active PID/start time before trusting a recent source change. Restart only the relevant workflow when authorized, then confirm the new behavior in its logs.