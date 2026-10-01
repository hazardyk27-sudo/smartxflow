---
name: Dashboard JavaScript bundle generation
description: Safe handling of the dashboard source and served JavaScript bundles.
---

Treat `static/js/app.js.src` as the input to `minify.py`, but do not assume the served `static/js/app.js` is an exact generated copy. The source and runtime bundles can contain independent changes; editing only one can make preview behavior differ from future rebuilds.

**Why:** A blind minifier run can overwrite runtime-only fixes with older source behavior.

**How to apply:** For startup or authentication changes, keep the relevant behavior aligned in both files and test both. Before a full regeneration, compare the generated output with the current runtime bundle and reconcile the broader differences first.