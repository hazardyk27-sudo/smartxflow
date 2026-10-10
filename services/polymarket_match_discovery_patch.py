"""Memory-bounded Polymarket match discovery for the scraper.

Gamma event objects contain full market payloads and are large. The legacy
``get_all_active_matches`` fetched every active Soccer event into one list and
only then applied the seven-day discovery window. On the production host this
can exceed memory as Polymarket's active-event catalogue grows.

This patch preserves the exact discovery window while pushing date bounds into
Gamma and compacting each keyset page to the small match contract immediately.
It does not change tracked-bettor visibility or sport classification rules.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Dict, List


def bind_polymarket_match_discovery_patch() -> None:
    from . import polymarket_client as client

    if getattr(client, "_sxf_bounded_match_discovery_bound", False):
        return

    def _fetch_match_window_paginated(
        base_params: Dict[str, Any],
        back_cutoff: datetime,
        forward_cutoff: datetime,
        page_size: int = 100,
    ) -> List[Dict[str, Any]]:
        params_base = dict(base_params)
        params_base["end_date_min"] = back_cutoff.isoformat()
        params_base["end_date_max"] = forward_cutoff.isoformat()

        matches: List[Dict[str, Any]] = []
        seen_ids: set = set()
        seen_cursors: set = set()
        cursor = None

        while True:
            params = dict(params_base)
            params["limit"] = page_size
            if cursor:
                params["after_cursor"] = cursor

            data = client._get_json(
                f"{client.GAMMA_BASE}/events/keyset",
                params,
            )
            if not isinstance(data, dict):
                break
            page = data.get("events") or []
            if not page:
                break

            for event in page:
                event_id = event.get("id")
                if not event_id or event_id in seen_ids:
                    continue
                match = client._event_to_match(event)
                if not match or not match.get("kickoff_utc"):
                    continue
                try:
                    kickoff_dt = datetime.fromisoformat(
                        match["kickoff_utc"].replace("Z", "+00:00")
                    )
                except Exception:
                    continue
                if kickoff_dt < back_cutoff or kickoff_dt > forward_cutoff:
                    continue
                seen_ids.add(event_id)
                matches.append(match)

            next_cursor = data.get("next_cursor")
            if not next_cursor or next_cursor in seen_cursors:
                break
            seen_cursors.add(next_cursor)
            cursor = next_cursor

        return matches

    def get_all_active_matches(hours_ahead: int = 168) -> List[Dict[str, Any]]:
        try:
            from zoneinfo import ZoneInfo
            tz = ZoneInfo("Europe/Istanbul")
        except Exception:
            tz = timezone(timedelta(hours=3))

        now = datetime.now(timezone.utc)
        now_local = now.astimezone(tz)
        start_of_yesterday_local = (now_local - timedelta(days=1)).replace(
            hour=0,
            minute=0,
            second=0,
            microsecond=0,
        )
        back_cutoff = start_of_yesterday_local.astimezone(timezone.utc)
        forward_cutoff = now + timedelta(hours=hours_ahead)

        active_matches = _fetch_match_window_paginated(
            {
                "tag_id": client.SOCCER_TAG_ID,
                "active": "true",
                "closed": "false",
                "order": "endDate",
                "ascending": "true",
            },
            back_cutoff,
            forward_cutoff,
        )
        closed_matches = _fetch_match_window_paginated(
            {
                "tag_id": client.SOCCER_TAG_ID,
                "closed": "true",
                "order": "endDate",
                "ascending": "false",
            },
            back_cutoff,
            forward_cutoff,
        )

        matches: List[Dict[str, Any]] = []
        seen_ids: set = set()
        for match in active_matches + closed_matches:
            event_id = match.get("event_id")
            if not event_id or event_id in seen_ids:
                continue
            seen_ids.add(event_id)
            matches.append(match)
        matches.sort(key=lambda row: row.get("kickoff_utc") or "")
        return matches

    client.get_all_active_matches = get_all_active_matches
    client._sxf_bounded_match_discovery_bound = True
