"""Phase 5A source-change outbox consumer — opt-in only, never auto-start.

Each source event is a durable SQL outbox claim. The consumer never trusts a
legacy hash or guessed ingestion date, and ACKs only after its idempotent
checkpoint enqueue / obsolete UID quarantine / T6 wake action completed.
"""
from __future__ import annotations

from .scheduler import FixtureRef
from .storage import DurableStoreError


def _apply(item: dict, store, *, quarantine_limit: int) -> None:
    kind=item["event_kind"]
    if kind.startswith("FIXTURE_"):
        current_uid=item["fixture_uid"]
        previous_uid=item.get("previous_fixture_uid")
        current_kickoff=store.source_fixture_state(current_uid)
        if current_kickoff is not None:
            store.enqueue([FixtureRef(current_uid,current_kickoff)])
        for uid in {current_uid,previous_uid} - {None}:
            # Count==limit means additional rows might remain. Refuse ACK
            # until a subsequent retry proves the source UID is fully clean.
            changed=store.quarantine_obsolete_uid(uid,limit=quarantine_limit)
            if changed>=quarantine_limit:
                raise RuntimeError("MORE_OBSOLETE_JOBS")
    elif kind=="SNAPSHOT_INSERT":
        if item.get("source_observed_at") is None:
            raise ValueError("missing source observation time")
        if item.get("market") not in ("1X2","OU25","BTTS"):
            # Unknown market is irrelevant to frozen BASE; do not label it T6.
            return
        store.wake_late_t6(item["fixture_uid"],item["market"],
                           item["source_observed_at"])
    elif kind in ("SNAPSHOT_CHANGE","SNAPSHOT_DELETE"):
        # Mutated evidence can invalidate prior immutable decisions. Do not
        # silently ACK until an explicit correction/review policy is approved.
        raise SourceMutationReviewRequired()
    else:
        raise ValueError("unrecognized source event kind")


class SourceMutationReviewRequired(RuntimeError):
    """A previously observed moneyway row changed; manual audit required."""


def process_source_change_once(store, *, worker_id: str, lease_seconds: int = 900,
                               quarantine_limit: int = 250) -> dict:
    """One claim, short RPC chain, token-fenced ACK; duplicate delivery is safe."""
    if type(quarantine_limit) is not int or not 1<=quarantine_limit<=1000:
        raise ValueError("invalid source quarantine limit")
    claimed=store.claim_source_changes(worker_id,lease_seconds=lease_seconds)
    stats={"claimed":len(claimed),"acknowledged":0,
           "retry":0,"manual_review":0,"uncertain":0}
    for item in claimed:
        try:
            _apply(item,store,quarantine_limit=quarantine_limit)
        except SourceMutationReviewRequired:
            try:
                store.retry_source_change(item,reason="SOURCE_MUTATION_REVIEW",
                                          delay_seconds=3600)
                stats["manual_review"]+=1
            except DurableStoreError:
                stats["uncertain"]+=1
            continue
        except Exception as error:
            name=type(error).__name__.upper()
            if name not in ("DURABLESTOREERROR","VALUEERROR","RUNTIMEERROR",
                            "CONNECTIONERROR","TIMEOUTERROR","SNAPSHOTREADERROR"):
                name="WORKER_ERROR"
            try:
                store.retry_source_change(item,reason=name,delay_seconds=300)
                stats["retry"]+=1
            except DurableStoreError:
                stats["uncertain"]+=1
            continue
        try:
            store.ack_source_change(item)
        except DurableStoreError:
            # The ACK may have committed before its HTTP response was lost.
            # Never claim success or re-run by local timer.
            stats["uncertain"]+=1
        else:
            stats["acknowledged"]+=1
    return stats
