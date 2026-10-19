"""Pure conservative market projection from immutable SXF Base events.

Read model only: never adds signals, invents odds, or rewrites the audit ledger.
The authoritative T-6 market decision always outranks T-8 preliminary rows.
Only a fully COMPLETED durable reconciliation batch can supersede a fallback.
"""
from __future__ import annotations

_MARKETS = ("1X2", "OU25", "BTTS")


def project_market_events(response: dict) -> dict:
    if not isinstance(response, dict) or type(response.get("fixture_authoritative")) is not bool:
        raise ValueError("invalid projection result")
    events = response.get("events")
    if not isinstance(events, list) or len(events) > 500:
        raise ValueError("unbounded/malformed projection events")
    if not response["fixture_authoritative"]:
        if events:
            raise ValueError("non-authoritative fixture cannot have current events")
        return {"fixture_authoritative": False, "markets": {
            market: {"status":"IDENTITY_NOT_CURRENT", "signals":[]} for market in _MARKETS}}
    ids=set()
    for event in events:
        if not isinstance(event,dict) or event.get("market") not in _MARKETS:
            raise ValueError("invalid market event")
        number=event.get("event_id")
        if type(number) is not int or number <= 0 or number in ids:
            raise ValueError("missing/duplicate event identity")
        ids.add(number)

    result={}
    for market in _MARKETS:
        rows=sorted((e for e in events if e["market"]==market),key=lambda x:x["event_id"])
        decisions=[e for e in rows if e.get("kind")=="MARKET_DECISION"
                   and e.get("job_checkpoint_hours")==6]
        if len(decisions)>1:
            raise ValueError("ambiguous T-6 market decision")
        decision=decisions[0] if decisions else None
        def signals(chosen):
            unique={}
            for e in chosen:
                engine=e.get("engine")
                selection=e.get("selection")
                if not isinstance(engine,str) or not engine or not isinstance(selection,str) or not selection:
                    raise ValueError("invalid signal identity")
                unique[(engine,selection)]={"engine":engine,"selection":selection}
            return list(unique.values())

        if decision is not None:
            corrections=[e for e in rows if e.get("kind")=="CORRECTED"
                         and e.get("origin_event_key")==decision.get("event_key")
                         and e.get("reconciled") is True]
            if corrections:
                current=signals(e for e in corrections if e.get("decision")=="HIT")
                if any(e.get("decision") not in ("HIT","NO_HIT") for e in corrections):
                    raise ValueError("invalid reconciled decision")
                result[market]={"status":"RECONCILED_T6" if current else "RECONCILED_T6_NO_HIT",
                                "signals":current}
            elif decision.get("source_checkpoint_hours")==6:
                final=[e for e in rows if e.get("kind")=="FINAL_SIGNAL"
                       and e.get("job_checkpoint_hours")==6
                       and e.get("source_checkpoint_hours")==6]
                current=signals(final)
                result[market]={"status":"AUTHORITATIVE_T6" if current else "AUTHORITATIVE_T6_NO_HIT",
                                "signals":current}
            else:
                fallback=[e for e in rows if e.get("kind")=="FINAL_SIGNAL"
                          and e.get("job_checkpoint_hours")==6
                          and e.get("source_checkpoint_hours")==8]
                result[market]={"status":"PROVISIONAL_T8_RECONCILIATION_PENDING",
                                "signals":signals(fallback)}
        else:
            preliminary=[e for e in rows if e.get("kind")=="PRELIMINARY_SIGNAL"
                         and e.get("job_checkpoint_hours")==8
                         and e.get("source_checkpoint_hours")==8]
            result[market]={"status":"PRELIMINARY_T8" if preliminary else "NO_T6_DECISION",
                            "signals":signals(preliminary)}
    return {"fixture_authoritative":True,"markets":result}


def current_market_projection(store, fixture_uid: str, kickoff_utc) -> dict:
    """Query only the service-role RPC; render a strictly bounded read model."""
    return project_market_events(store.read_market_events(fixture_uid,kickoff_utc))
