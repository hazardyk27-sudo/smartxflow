---
name: Alarm engine OOM crash-loop (Sept 2026)
description: Root cause and fix for smartxflow-alarm.service repeatedly OOM-killed on Hetzner; two independent contributing causes, neither was the first suspected one.
---

## What actually happened
`smartxflow-alarm.service` was OOM-killed every ~5 minutes for hours. The
initial hypothesis (unbounded per-match history array in the calculator) was
wrong — that cap (`MAX_HISTORY_ROWS_PER_MATCH`) was already correctly wired
in and cleared every cycle. The real causes were two separate things:

1. **Stale signal backlog reprocessing.** `alarm_engine.py` pulled the
   *oldest* unprocessed `scraper_signal` row and processed the backlog
   one-by-one. `run_all_calculations()` always reads live DB state — it
   never uses the signal's own payload — so replaying hundreds of stale
   signals recomputed the exact same thing over and over for zero benefit,
   at ~9-10 min-per-cycle to catch up. A backlog can silently grow to
   hundreds of rows within days if the engine ever falls behind (crash-loop,
   deploy gap, etc.), and nothing was clearing it.
   **Fix:** always fetch the newest unprocessed signal; bulk-mark all older
   unprocessed rows as processed without computing for them.

2. **glibc not returning freed memory to the OS.** Even with the backlog
   cleared, a single full calculation cycle across the whole live-match
   universe pushes RSS to ~1.5-1.8GB, and `gc.collect()` alone did not bring
   it back down afterward — RSS kept climbing cycle over cycle. This is a
   classic Python/glibc malloc-arena fragmentation symptom, not a Python
   object leak.
   **Fix:** call `ctypes.CDLL("libc.so.6").malloc_trim(0)` right after
   `gc.collect()` at the end of `run_all_calculations()`. Confirmed on
   Hetzner: RSS now drops from a ~1.6-1.7GB cycle peak down to a ~500MB
   steady state after each run, instead of only ever growing.

**Why this matters for future debugging:** a memory-growth report on this
service can have either or both causes. Check the `scraper_signal` backlog
size first (`processed=eq.false` count) before assuming it's a leak in
`AlarmCalculator` — an old backlog looks identical to a "constant" leak from
the outside, since the engine has no throttling and no idle gaps while it
has any pending signal, however old.

## Non-obvious sys.path gotcha
`alarm_engine.py` inserts three lookup dirs at index 0 in this order: own
dir, then `scraper_standalone/`, then `desktop/scraper_standalone/`. Since
each `sys.path.insert(0, ...)` pushes to the front, **the last insert wins**
— so the live `AlarmCalculator` actually resolves to
`desktop/scraper_standalone/alarm_calculator.py`, not a same-named file in
`scraper_standalone/` (which doesn't currently exist, but if one were ever
added it would be shadowed and never used). Always verify which file
actually loads via `sys.path` order, not by grepping for the file name.
