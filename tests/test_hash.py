#!/usr/bin/env python3
"""Canonical SmartXFlow match identity regression tests."""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), ".."))

from core.hash_utils import make_fixture_identity_key, make_match_id_hash


def test_same_match_two_scrapes():
    a = make_match_id_hash("Manchester City", "Arsenal", "Premier League", "2026-10-15T20:00:00Z")
    b = make_match_id_hash("Manchester City", "Arsenal", "Premier League", "2026-10-15T20:00:00+00:00")
    assert a == b


def test_case_whitespace_and_suffix_variations():
    clean = make_match_id_hash("Galatasaray", "Fenerbahce", "Super Lig")
    spaces = make_match_id_hash("  GALATASARAY  ", " fenerbahce ", " SUPER   LIG ")
    suffixes = make_match_id_hash("Galatasaray SK.", "Fenerbahce FC", "Super Lig!")
    assert clean == spaces == suffixes


def test_turkiye_ascii_equivalence():
    accented = make_match_id_hash("Italy", "Türkiye", "UEFA Nations League A")
    ascii_name = make_match_id_hash("Italy", "Turkiye", "UEFA Nations League A")
    assert accented == ascii_name == "f26381742135"


def test_ceuta_suffix_equivalence():
    with_suffix = make_match_id_hash("CD Castellon", "AD Ceuta FC", "Spanish Segunda Division")
    without_suffix = make_match_id_hash("CD Castellon", "AD Ceuta", "Spanish Segunda Division")
    assert with_suffix == without_suffix == "d0666bbeb294"


def test_same_kickoff_teams_league_same_hash():
    variants = {
        make_match_id_hash("Italy", "Türkiye", "UEFA Nations League A", "2026-10-05T18:45:00Z"),
        make_match_id_hash(" italy ", " TURKIYE ", "uefa nations league a", "2026-10-05T18:45:00+00:00"),
        make_match_id_hash("ITALY", "Turkiye", "UEFA  Nations League A", "2026-10-05T21:45:00+03:00"),
    }
    assert variants == {"f26381742135"}


def test_physical_identity_normalizes_timezone_to_utc_minute():
    utc = make_fixture_identity_key("Italy", "Türkiye", "UEFA Nations League A", "2026-10-05T18:45:00Z")
    tr = make_fixture_identity_key(" italy ", "Turkiye", "UEFA Nations League A", "2026-10-05T21:45:00+03:00")
    assert utc == tr
    assert utc[-1] == "2026-10-05T18:45Z"


def test_physical_identity_includes_league_and_kickoff():
    base = make_fixture_identity_key("Home FC", "Away FC", "League A", "2026-10-05T18:45:00Z")
    other_league = make_fixture_identity_key("Home", "Away", "League B", "2026-10-05T18:45:00Z")
    other_kickoff = make_fixture_identity_key("Home", "Away", "League A", "2026-10-05T18:46:00Z")
    assert base != other_league
    assert base != other_kickoff


def run_all_tests():
    tests = [
        test_same_match_two_scrapes,
        test_case_whitespace_and_suffix_variations,
        test_turkiye_ascii_equivalence,
        test_ceuta_suffix_equivalence,
        test_same_kickoff_teams_league_same_hash,
        test_physical_identity_normalizes_timezone_to_utc_minute,
        test_physical_identity_includes_league_and_kickoff,
    ]
    for test in tests:
        test()
        print(f"PASS {test.__name__}")
    print(f"PASS all {len(tests)} canonical hash tests")


if __name__ == "__main__":
    run_all_tests()
