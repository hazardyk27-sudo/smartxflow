import unittest
from unittest.mock import patch

from services import polymarket_client


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = ""

    def json(self):
        return self._payload


class EventsKeysetPaginationTests(unittest.TestCase):
    def test_paginates_past_a_2000_event_growth_threshold(self):
        # 25 pages of 100 events each = 2500 events, well past the old
        # offset-endpoint ~2000-2100 cap that originally dropped real matches.
        total_events = 2500
        page_size = 100

        def fake_get(url, params=None, headers=None, timeout=None):
            after_cursor = (params or {}).get("after_cursor")
            start = int(after_cursor) if after_cursor else 0
            page = [{"id": str(i)} for i in range(start, min(start + page_size, total_events))]
            next_cursor = str(start + page_size) if start + page_size < total_events else None
            return FakeResponse(200, {"events": page, "next_cursor": next_cursor})

        with patch("services.polymarket_client.requests.get", side_effect=fake_get):
            events = polymarket_client._fetch_events_paginated({"tag_id": 1})

        self.assertEqual(len(events), total_events)
        self.assertEqual({e["id"] for e in events}, {str(i) for i in range(total_events)})

    def test_stops_on_empty_page_rather_than_looping_forever(self):
        def fake_get(url, params=None, headers=None, timeout=None):
            after_cursor = (params or {}).get("after_cursor")
            if after_cursor:
                return FakeResponse(200, {"events": [], "next_cursor": None})
            return FakeResponse(200, {"events": [{"id": "1"}], "next_cursor": "next"})

        with patch("services.polymarket_client.requests.get", side_effect=fake_get):
            events = polymarket_client._fetch_events_paginated({"tag_id": 1})

        self.assertEqual(len(events), 1)

    def test_stops_on_a_repeated_cursor_cycle_instead_of_looping_forever(self):
        # Cursor sequence A -> B -> A: a longer cycle than an immediate
        # repeat, which the "seen cursors" guard must still catch.
        calls = {"n": 0}

        def fake_get(url, params=None, headers=None, timeout=None):
            calls["n"] += 1
            after_cursor = (params or {}).get("after_cursor")
            if after_cursor is None:
                return FakeResponse(200, {"events": [{"id": "1"}], "next_cursor": "A"})
            if after_cursor == "A":
                return FakeResponse(200, {"events": [{"id": "2"}], "next_cursor": "B"})
            if after_cursor == "B":
                return FakeResponse(200, {"events": [{"id": "3"}], "next_cursor": "A"})
            raise AssertionError(f"unexpected cursor {after_cursor}")

        with patch("services.polymarket_client.requests.get", side_effect=fake_get):
            events = polymarket_client._fetch_events_paginated({"tag_id": 1})

        self.assertEqual([e["id"] for e in events], ["1", "2", "3"])
        self.assertEqual(calls["n"], 3)

    def test_stop_check_halts_pagination_early(self):
        def fake_get(url, params=None, headers=None, timeout=None):
            after_cursor = (params or {}).get("after_cursor")
            start = int(after_cursor) if after_cursor else 0
            page = [{"id": str(start)}]
            return FakeResponse(200, {"events": page, "next_cursor": str(start + 1)})

        with patch("services.polymarket_client.requests.get", side_effect=fake_get):
            events = polymarket_client._fetch_events_paginated(
                {"tag_id": 1},
                stop_check=lambda page: page[-1]["id"] == "2",
            )

        self.assertEqual([e["id"] for e in events], ["0", "1", "2"])


if __name__ == "__main__":
    unittest.main()
