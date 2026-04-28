"""
Verification script for active_keys filtering across all scan types.
Tests that:
  1. Each scan/helper skips rows NOT in active_keys when the set is provided.
  2. Each scan/helper processes ALL rows when active_keys=None.
  3. Key format (home|away|date) is consistent between fetch_live_active_keys
     and every filtering site.

Run with:  python test_active_keys_filtering.py
No live database connection required — all DB calls are patched.
"""

import sys
import types
import unittest
from unittest.mock import patch, MagicMock


# ---------------------------------------------------------------------------
# Minimal stubs so sinyal_engine can be imported without real credentials
# ---------------------------------------------------------------------------

def _make_stub_module(name):
    mod = types.ModuleType(name)
    sys.modules[name] = mod
    return mod

# requests stub — every call returns a 200 with [] by default
requests_stub = _make_stub_module("requests")
class _FakeResp:
    status_code = 200
    text = "[]"
    def json(self):
        return []
requests_stub.get  = MagicMock(return_value=_FakeResp())
requests_stub.post = MagicMock(return_value=_FakeResp())
requests_stub.patch = MagicMock(return_value=_FakeResp())
requests_stub.delete = MagicMock(return_value=_FakeResp())
requests_stub.Session = MagicMock()

# dotenv stub
dotenv_stub = _make_stub_module("dotenv")
dotenv_stub.load_dotenv = lambda *a, **kw: None

import os
os.environ.setdefault("SUPABASE_URL", "http://fake")
os.environ.setdefault("SUPABASE_KEY", "fakekey")
os.environ.setdefault("SUPABASE_SERVICE_KEY", "fakeservicekey")

import sinyal_engine as se  # noqa: E402  (imported after stubs)


# ---------------------------------------------------------------------------
# Helper builders
# ---------------------------------------------------------------------------

def _make_snapshot(home, away, date, **extra):
    """Return a minimal snapshot row dict."""
    return {
        "home": home,
        "away": away,
        "date": date,
        "odds1": 2.0,
        "oddsx": 3.5,
        "odds2": 3.8,
        "pct1": 30,
        "pctx": 30,
        "pct2": 40,
        "volume": 1000,
        **extra,
    }


def _make_snapshots_dict(*matches):
    """Build the ``{hash: row}`` dict that scan functions receive."""
    result = {}
    for i, (home, away, date) in enumerate(matches):
        result[f"hash_{i}"] = _make_snapshot(home, away, date)
    return result


def _make_history_rows(*matches):
    """Build a flat list of history rows (as returned by Supabase)."""
    rows = []
    for home, away, date in matches:
        rows.append({
            "home": home, "away": away, "date": date,
            "odds1": 2.0, "oddsx": 3.5, "odds2": 3.8,
            "pct1": 30, "pctx": 30, "pct2": 40,
            "volume": 1000, "scraped_at": "2026-04-27T10:00:00+00:00",
        })
    return rows


# Active / finished matches used in all tests
ACTIVE_MATCH   = ("TeamA", "TeamB", "27.Apr 18:00")
FINISHED_MATCH = ("TeamX", "TeamY", "26.Apr 15:00")

ACTIVE_KEY   = f"{ACTIVE_MATCH[0]}|{ACTIVE_MATCH[1]}|{ACTIVE_MATCH[2]}"
FINISHED_KEY = f"{FINISHED_MATCH[0]}|{FINISHED_MATCH[1]}|{FINISHED_MATCH[2]}"

ACTIVE_KEYS_SET = {ACTIVE_KEY}     # only the active match is in this set


# ===========================================================================
# 1.  KEY FORMAT: fetch_live_active_keys
# ===========================================================================

class TestKeyFormat(unittest.TestCase):
    """Verifies fetch_live_active_keys() produces home|away|date strings."""

    def test_key_format_matches_scan_format(self):
        """Keys from fetch_live_active_keys must be 'home|away|date'."""
        fake_rows = [{"home": "A", "away": "B", "date": "27.Apr 18:00"}]
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = fake_rows

        with patch.object(se.requests, "get", return_value=fake_resp):
            keys = se.fetch_live_active_keys()

        self.assertIsNotNone(keys, "fetch_live_active_keys returned None unexpectedly")
        self.assertIn("A|B|27.Apr 18:00", keys,
                      "Key format must be 'home|away|date'")

    def test_returns_none_on_empty_table(self):
        """Empty table → None (filter disabled)."""
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = []

        with patch.object(se.requests, "get", return_value=fake_resp):
            keys = se.fetch_live_active_keys()

        self.assertIsNone(keys)

    def test_returns_none_on_http_error(self):
        """Non-200 → None (filter disabled)."""
        fake_resp = MagicMock()
        fake_resp.status_code = 500

        with patch.object(se.requests, "get", return_value=fake_resp):
            keys = se.fetch_live_active_keys()

        self.assertIsNone(keys)

    def test_skips_rows_missing_fields(self):
        """Rows missing home/away/date are excluded from the key set."""
        fake_rows = [
            {"home": "A", "away": "B", "date": "27.Apr 18:00"},
            {"home": "",  "away": "B", "date": "27.Apr 18:00"},   # empty home
            {"home": "C", "away": "",  "date": "27.Apr 18:00"},   # empty away
            {"home": "D", "away": "E", "date": ""},               # empty date
        ]
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = fake_rows

        with patch.object(se.requests, "get", return_value=fake_resp):
            keys = se.fetch_live_active_keys()

        self.assertIsNotNone(keys)
        self.assertEqual(len(keys), 1, "Only the fully-populated row should be keyed")


# ===========================================================================
# 2.  run_underdog_scan — direct snapshot filtering
# ===========================================================================

class TestUnderdogScanFiltering(unittest.TestCase):
    """run_underdog_scan filters the snapshots dict directly."""

    def _run(self, snapshots, active_keys):
        processed_args = []

        def fake_find_signals(snaps):
            processed_args.append(snaps)
            return []

        with patch.object(se, "check_columns_exist", return_value=False), \
             patch.object(se, "cleanup_low_volume_signals"), \
             patch.object(se, "find_signals", side_effect=fake_find_signals):
            se.run_underdog_scan(snapshots, {}, active_keys=active_keys)

        return processed_args[0] if processed_args else {}

    def test_active_keys_none_processes_all(self):
        """active_keys=None → all snapshots forwarded to find_signals."""
        snaps = _make_snapshots_dict(ACTIVE_MATCH, FINISHED_MATCH)
        processed = self._run(snaps, active_keys=None)
        self.assertEqual(set(processed.keys()), set(snaps.keys()))

    def test_active_keys_set_skips_finished(self):
        """Finished match key is absent from active_keys → row excluded."""
        snaps = _make_snapshots_dict(ACTIVE_MATCH, FINISHED_MATCH)
        processed = self._run(snaps, active_keys=ACTIVE_KEYS_SET)
        self.assertEqual(len(processed), 1)
        row = next(iter(processed.values()))
        self.assertEqual(row["home"], ACTIVE_MATCH[0])

    def test_active_keys_empty_set_skips_all(self):
        """Empty active_keys set → all snapshots excluded."""
        snaps = _make_snapshots_dict(ACTIVE_MATCH, FINISHED_MATCH)
        processed = self._run(snaps, active_keys=set())
        self.assertEqual(len(processed), 0)

    def test_active_keys_keeps_exact_key_match(self):
        """Only the row whose home|away|date is in active_keys passes through."""
        snaps = _make_snapshots_dict(ACTIVE_MATCH, FINISHED_MATCH)
        processed = self._run(snaps, active_keys={FINISHED_KEY})
        self.assertEqual(len(processed), 1)
        row = next(iter(processed.values()))
        self.assertEqual(row["home"], FINISHED_MATCH[0])


# ===========================================================================
# 3.  fetch_recent_history — active_keys filtering
# ===========================================================================

class TestFetchRecentHistoryFiltering(unittest.TestCase):
    """fetch_recent_history() skips rows whose key is absent from active_keys."""

    def _fetch(self, rows, active_keys):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = rows

        with patch.object(se.requests, "get", return_value=fake_resp):
            return se.fetch_recent_history(active_keys=active_keys)

    def test_none_processes_all(self):
        rows = _make_history_rows(ACTIVE_MATCH, FINISHED_MATCH)
        result = self._fetch(rows, active_keys=None)
        self.assertEqual(len(result), 2)
        self.assertIn(ACTIVE_KEY, result)
        self.assertIn(FINISHED_KEY, result)

    def test_set_skips_finished(self):
        rows = _make_history_rows(ACTIVE_MATCH, FINISHED_MATCH)
        result = self._fetch(rows, active_keys=ACTIVE_KEYS_SET)
        self.assertIn(ACTIVE_KEY, result)
        self.assertNotIn(FINISHED_KEY, result)

    def test_empty_set_skips_all(self):
        rows = _make_history_rows(ACTIVE_MATCH, FINISHED_MATCH)
        result = self._fetch(rows, active_keys=set())
        self.assertEqual(len(result), 0)

    def test_rows_missing_home_or_away_skipped(self):
        rows = [
            {"home": "", "away": "B", "date": "27.Apr 18:00",
             "odds1": 2.0, "oddsx": 3.5, "odds2": 3.8,
             "pct1": 30, "pctx": 30, "pct2": 40, "volume": 1000,
             "scraped_at": "2026-04-27T10:00:00+00:00"},
        ]
        result = self._fetch(rows, active_keys=None)
        self.assertEqual(len(result), 0,
                         "Row with empty home must be skipped regardless of active_keys")


# ===========================================================================
# 4.  fetch_first_snapshots — active_keys filtering
# ===========================================================================

class TestFetchFirstSnapshotsFiltering(unittest.TestCase):
    """fetch_first_snapshots() keeps only the earliest row per active match key."""

    def _fetch(self, rows, active_keys):
        fake_resp = MagicMock()
        fake_resp.status_code = 200
        fake_resp.json.return_value = rows

        with patch.object(se.requests, "get", return_value=fake_resp):
            return se.fetch_first_snapshots(active_keys=active_keys)

    def test_none_processes_all(self):
        rows = _make_history_rows(ACTIVE_MATCH, FINISHED_MATCH)
        result = self._fetch(rows, active_keys=None)
        self.assertIn(ACTIVE_KEY, result)
        self.assertIn(FINISHED_KEY, result)

    def test_set_skips_finished(self):
        rows = _make_history_rows(ACTIVE_MATCH, FINISHED_MATCH)
        result = self._fetch(rows, active_keys=ACTIVE_KEYS_SET)
        self.assertIn(ACTIVE_KEY, result)
        self.assertNotIn(FINISHED_KEY, result)

    def test_only_first_snapshot_kept_per_key(self):
        """When two rows share the same key, only the first (asc order) is kept."""
        rows = _make_history_rows(ACTIVE_MATCH, ACTIVE_MATCH)  # duplicate
        result = self._fetch(rows, active_keys=None)
        self.assertEqual(len(result), 1)


# ===========================================================================
# 5.  find_early_money_lock — active_keys filtering in EML loop (real function)
# ===========================================================================

class TestFindEarlyMoneyLockFiltering(unittest.TestCase):
    """Calls the real find_early_money_lock(); only fetch_eml_history is mocked.

    Strategy: fetch_eml_history receives the set of computed MD5 hashes that
    passed the active_keys filter.  By comparing that set against the hashes
    of known active/finished matches we can verify which rows were skipped.
    """

    def _build_latest(self, *matches):
        """latest_snapshots uses 'home|away|date' string keys (as in production)."""
        result = {}
        for home, away, date in matches:
            key = f"{home}|{away}|{date}"
            result[key] = _make_snapshot(home, away, date)
        return result

    def _hash_of(self, match):
        home, away, date = match
        return se._make_match_id_hash(home, away, "")  # league="" in our snapshots

    def _run_real(self, latest_snapshots, active_keys):
        """Run the real find_early_money_lock; return the hash set passed to fetch_eml_history."""
        captured_hashes = {}

        def fake_fetch_eml_history(hashes):
            captured_hashes["hashes"] = set(hashes)
            return {}  # no history → no signals emitted

        with patch.object(se, "fetch_eml_history", side_effect=fake_fetch_eml_history):
            se.find_early_money_lock(
                latest_snapshots, [], {}, active_keys=active_keys
            )

        return captured_hashes.get("hashes", set())

    def test_none_processes_all(self):
        """active_keys=None → both matches reach fetch_eml_history."""
        ls = self._build_latest(ACTIVE_MATCH, FINISHED_MATCH)
        hashes = self._run_real(ls, active_keys=None)
        self.assertIn(self._hash_of(ACTIVE_MATCH), hashes)
        self.assertIn(self._hash_of(FINISHED_MATCH), hashes)
        self.assertEqual(len(hashes), 2)

    def test_set_skips_finished(self):
        """Finished match key absent from active_keys → its hash excluded from fetch_eml_history."""
        ls = self._build_latest(ACTIVE_MATCH, FINISHED_MATCH)
        hashes = self._run_real(ls, active_keys=ACTIVE_KEYS_SET)
        self.assertIn(self._hash_of(ACTIVE_MATCH), hashes)
        self.assertNotIn(self._hash_of(FINISHED_MATCH), hashes)
        self.assertEqual(len(hashes), 1)

    def test_empty_set_skips_all(self):
        """Empty active_keys → fetch_eml_history called with empty set."""
        ls = self._build_latest(ACTIVE_MATCH, FINISHED_MATCH)
        hashes = self._run_real(ls, active_keys=set())
        self.assertEqual(len(hashes), 0)

    def test_key_format_matches_active_keys_format(self):
        """latest_snapshots key must be 'home|away|date' — same format as active_keys."""
        ls = self._build_latest(ACTIVE_MATCH)
        first_key = next(iter(ls.keys()))
        expected = f"{ACTIVE_MATCH[0]}|{ACTIVE_MATCH[1]}|{ACTIVE_MATCH[2]}"
        self.assertEqual(first_key, expected,
                         "latest_snapshots key format must match active_keys format")


# ===========================================================================
# 6.  run_cm_scan / run_cm_v2_scan / run_fs_scan — delegation verification
# ===========================================================================

class TestCMScanDelegation(unittest.TestCase):
    """CM, CMv2, and FS scans must forward active_keys to fetch_recent_history
    and fetch_first_snapshots rather than filtering locally."""

    def _captured_active_keys_for(self, scan_fn, extra_patches=None):
        captured = {}

        def fake_history(active_keys=None):
            captured["history_keys"] = active_keys
            return {}

        def fake_snaps(active_keys=None):
            captured["snaps_keys"] = active_keys
            return {}

        patches = {
            "fetch_recent_history": fake_history,
            "fetch_first_snapshots": fake_snaps,
        }
        if extra_patches:
            patches.update(extra_patches)

        with patch.multiple(se, **{k: v for k, v in patches.items()}):
            scan_fn()

        return captured

    def test_run_cm_scan_forwards_active_keys(self):
        def run():
            with patch.object(se, "check_cm_table_exists", return_value=True), \
                 patch.object(se, "fetch_cm_recent_cooldowns", return_value=set()), \
                 patch.object(se, "find_confirmed_money", return_value=[]), \
                 patch.object(se, "fetch_existing_cm_signals", return_value=[]), \
                 patch.object(se, "save_confirmed_money_signals", return_value=0), \
                 patch.object(se, "update_cm_current_values", return_value=(0, 0)), \
                 patch.object(se, "delete_invalid_cm_signals", return_value=0):
                se.run_cm_scan({}, {}, active_keys=ACTIVE_KEYS_SET)

        captured = self._captured_active_keys_for(run)
        self.assertEqual(captured.get("history_keys"), ACTIVE_KEYS_SET,
                         "run_cm_scan must forward active_keys to fetch_recent_history")
        self.assertEqual(captured.get("snaps_keys"), ACTIVE_KEYS_SET,
                         "run_cm_scan must forward active_keys to fetch_first_snapshots")

    def test_run_cm_scan_none_forwards_none(self):
        def run():
            with patch.object(se, "check_cm_table_exists", return_value=True), \
                 patch.object(se, "fetch_cm_recent_cooldowns", return_value=set()), \
                 patch.object(se, "find_confirmed_money", return_value=[]), \
                 patch.object(se, "fetch_existing_cm_signals", return_value=[]), \
                 patch.object(se, "save_confirmed_money_signals", return_value=0), \
                 patch.object(se, "update_cm_current_values", return_value=(0, 0)), \
                 patch.object(se, "delete_invalid_cm_signals", return_value=0):
                se.run_cm_scan({}, {}, active_keys=None)

        captured = self._captured_active_keys_for(run)
        self.assertIsNone(captured.get("history_keys"),
                          "run_cm_scan with active_keys=None must forward None")

    def test_run_cm_v2_scan_forwards_active_keys(self):
        def run():
            with patch.object(se, "check_cm_v2_table_exists", return_value=True), \
                 patch.object(se, "fetch_cm_v2_recent_cooldowns", return_value=set()), \
                 patch.object(se, "find_confirmed_money_v2", return_value=[]), \
                 patch.object(se, "fetch_existing_cm_v2_signals", return_value=[]), \
                 patch.object(se, "save_confirmed_money_v2_signals", return_value=0), \
                 patch.object(se, "delete_invalid_cm_v2_signals", return_value=0):
                se.run_cm_v2_scan({}, {}, active_keys=ACTIVE_KEYS_SET)

        captured = self._captured_active_keys_for(run)
        self.assertEqual(captured.get("history_keys"), ACTIVE_KEYS_SET,
                         "run_cm_v2_scan must forward active_keys to fetch_recent_history")

    def test_run_fs_scan_forwards_active_keys(self):
        def run():
            with patch.object(se, "check_fs_table_exists", return_value=True), \
                 patch.object(se, "fetch_fs_cooldown", return_value=set()), \
                 patch.object(se, "find_fake_sharp", return_value=[]), \
                 patch.object(se, "fetch_existing_fs_signals", return_value=[]), \
                 patch.object(se, "save_fake_sharp_signals", return_value=0), \
                 patch.object(se, "update_fs_current_odds", return_value=(0, 0)), \
                 patch.object(se, "delete_invalid_fs_signals", return_value=0):
                se.run_fs_scan({}, {}, active_keys=ACTIVE_KEYS_SET)

        captured = self._captured_active_keys_for(run)
        self.assertEqual(captured.get("history_keys"), ACTIVE_KEYS_SET,
                         "run_fs_scan must forward active_keys to fetch_recent_history")


# ===========================================================================
# 7.  run_eml_scan — delegation verification
# ===========================================================================

class TestEMLScanDelegation(unittest.TestCase):
    """run_eml_scan must forward active_keys to find_early_money_lock."""

    def test_forwards_active_keys(self):
        captured = {}

        def fake_eml(ls, existing, kickoff_map, active_keys=None):
            captured["active_keys"] = active_keys
            return []

        with patch.object(se, "check_eml_table_exists", return_value=True), \
             patch.object(se, "fetch_eml_kickoffs", return_value={"dummy": "val"}), \
             patch.object(se, "fetch_eml_existing", return_value=[]), \
             patch.object(se, "find_early_money_lock", side_effect=fake_eml):
            se.run_eml_scan({}, active_keys=ACTIVE_KEYS_SET)

        self.assertEqual(captured.get("active_keys"), ACTIVE_KEYS_SET,
                         "run_eml_scan must forward active_keys to find_early_money_lock")

    def test_forwards_none(self):
        captured = {}

        def fake_eml(ls, existing, kickoff_map, active_keys=None):
            captured["active_keys"] = active_keys
            return []

        with patch.object(se, "check_eml_table_exists", return_value=True), \
             patch.object(se, "fetch_eml_kickoffs", return_value={"dummy": "val"}), \
             patch.object(se, "fetch_eml_existing", return_value=[]), \
             patch.object(se, "find_early_money_lock", side_effect=fake_eml):
            se.run_eml_scan({}, active_keys=None)

        self.assertIsNone(captured.get("active_keys"),
                          "run_eml_scan with active_keys=None must forward None")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    loader = unittest.TestLoader()
    suite  = unittest.TestSuite()
    suite.addTests(loader.loadTestsFromTestCase(TestKeyFormat))
    suite.addTests(loader.loadTestsFromTestCase(TestUnderdogScanFiltering))
    suite.addTests(loader.loadTestsFromTestCase(TestFetchRecentHistoryFiltering))
    suite.addTests(loader.loadTestsFromTestCase(TestFetchFirstSnapshotsFiltering))
    suite.addTests(loader.loadTestsFromTestCase(TestFindEarlyMoneyLockFiltering))
    suite.addTests(loader.loadTestsFromTestCase(TestCMScanDelegation))
    suite.addTests(loader.loadTestsFromTestCase(TestEMLScanDelegation))

    runner = unittest.TextTestRunner(verbosity=2)
    result = runner.run(suite)
    sys.exit(0 if result.wasSuccessful() else 1)
