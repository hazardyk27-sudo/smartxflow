---
name: Live match identity
description: Identity rules for associating modal alarms and live snapshots with the correct fixture.
---

The modal must treat `match_id_hash` as the primary identity for alarms, charts, and live snapshots. Team names alone are not a safe key because the same teams can appear in youth or parallel competitions. Legacy records without a hash may only fall back when both league and kickoff also match; future or non-live fixtures must not expose live snapshots.

**Why:** Repeated team names caused U19 and senior fixtures to leak alarms and live snapshots into each other.

**How to apply:** Propagate hash, league, and kickoff through every modal entry point, prefer hash-based endpoints, and keep any team-based fallback strictly context-validated.