# 18 October raw alarms — verified completion addendum

**Recorded 2026-10-21.** This is an append-only addendum to `2026-10-21_raw_archive_recovery_audit_v3.md`. No prior historical files rewritten.

For 2026-10-18, the following alarm source and research_archive event counts were independently checked:

| Dataset | Source IDs | Archived IDs after repair |
|---|---:|---:|
| sharp_alarms | 23 | 23 |
| insider_alarms | 0 | 0 |
| bigmoney_alarms | 25 | 25 |
| volumeshock_alarms | 62 | 62 |
| dropping_alarms | 9 | 9 |
| publicmove_alarms | 0 | 0 |
| volume_leader_alarms | 74 | 74 |
| mim_alarms | 173 | 173 |

Initially 21 of 23 Sharp alarm IDs were archived. Two source records with null fixture UID were matched to 18 October local-day fixtures using their match hash and timestamp/kickoff window: ID **68692** at 2026-10-17 21:38:44 UTC and ID **68693** at 2026-10-17 22:39:03 UTC. The matching fixtures' UTC kickoffs were 22:30 and 23:30 on 17 October, respectively (18 October in Europe/Istanbul). Inserted source raw columns and 18-Oct archive metadata only when each ID was absent, then verified 23 rows and 23 distinct IDs in `research_archive.sharp_alarms`.

This closes the 18 Oct **alarm-family count gap**, but does **not** certify the full 18 Oct raw archive. Counts of other raw families can exceed directly identity-matched source data, so detailed alias/provenance audit is still required. `archive_runs.status` remains `PARTIAL`; cold backup remains pending. The 20 Oct Dropping 1X2 duplicate fault in v3 remains unresolved; do not infer a full 20-Oct completion from its 139/139 receipt inventory.

No source table rows, production signal rules or live app files were modified, and no destructive cleanup was performed.
