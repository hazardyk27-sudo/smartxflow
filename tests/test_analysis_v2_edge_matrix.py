from analysis_v2.edge_matrix import (
    build_edge_matrix,
    bucket_label,
    chronological_split,
    evaluate_locked_segments,
    research_candidates,
)


def _row(i, *, odds=1.80, pct=87.0, drop=6.0, outcome="WIN", ts=None):
    return {
        "trigger_at": ts or f"2026-01-{(i % 28) + 1:02d}T12:00:00Z",
        "entry_odds": odds,
        "trigger_pct": pct,
        "odds_drop_pct": drop,
        "outcome": outcome,
    }


def test_expected_research_buckets_are_stable():
    assert bucket_label("money_pct", 84.9) == "80-84.9"
    assert bucket_label("money_pct", 85.0) == "85-89.9"
    assert bucket_label("money_pct", 95.0) == "95+"
    assert bucket_label("price_drop_pct", 5.0) == "drop_5-7"
    assert bucket_label("price_drop_pct", 7.0) == "drop_7-10"
    assert bucket_label("odds", 3.40) == "2.90-3.99"


def test_matrix_calculates_flat_stake_roi_from_entry_odds():
    rows = [
        _row(1, odds=2.0, outcome="WIN"),
        _row(2, odds=2.0, outcome="LOSS"),
        _row(3, odds=2.0, outcome="WIN"),
        _row(4, odds=2.0, outcome="LOSS"),
    ]
    cells = build_edge_matrix(
        rows,
        dimensions=("odds", "money_pct", "price_drop_pct"),
        min_sample=4,
    )
    assert len(cells) == 1
    cell = cells[0]
    assert cell["n"] == 4
    assert cell["hit_rate_pct"] == 50.0
    assert cell["roi_pct"] == 0.0
    assert cell["sample_status"] == "SUFFICIENT"
    assert cell["evidence_status"] == "RESEARCH"


def test_small_high_roi_cell_is_not_research_candidate():
    rows = [_row(i, odds=2.0, outcome="WIN") for i in range(5)]
    cells = build_edge_matrix(rows, min_sample=30)
    assert cells[0]["roi_pct"] == 100.0
    assert cells[0]["sample_status"] == "SMALL_SAMPLE"
    assert research_candidates(cells, min_sample=30) == []


def test_positive_sufficient_cell_is_only_research_candidate():
    rows = []
    for i in range(40):
        rows.append(_row(i, odds=1.80, outcome="WIN" if i < 28 else "LOSS"))
    cells = build_edge_matrix(rows, min_sample=30)
    candidates = research_candidates(cells, min_sample=30)
    assert len(candidates) == 1
    assert candidates[0]["evidence_status"] == "RESEARCH_CANDIDATE"
    assert candidates[0]["roi_pct"] > 0


def test_chronological_split_does_not_randomize_future_into_train():
    rows = [
        _row(i, ts=f"2026-01-{i + 1:02d}T12:00:00Z")
        for i in range(10)
    ]
    split = chronological_split(rows, train_fraction=0.6, validation_fraction=0.2)
    assert len(split["train"]) == 6
    assert len(split["validation"]) == 2
    assert len(split["holdout"]) == 2
    assert split["train"][0]["trigger_at"].startswith("2026-01-01")
    assert split["holdout"][-1]["trigger_at"].startswith("2026-01-10")


def test_locked_segment_must_survive_holdout_without_reoptimizing():
    segment = ("1.80-1.99", "85-89.9", "drop_5-7")
    rows = []
    for i in range(40):
        rows.append(_row(i, odds=1.85, pct=87.0, drop=6.0, outcome="LOSS"))
    checked = evaluate_locked_segments(
        rows,
        dimensions=("odds", "money_pct", "price_drop_pct"),
        locked_segments=[segment],
        min_sample=30,
    )
    assert len(checked) == 1
    assert checked[0]["segment"] == segment
    assert checked[0]["evidence_status"] == "HOLDOUT_REJECTED"


def test_missing_feature_rows_are_not_forced_into_a_bucket():
    rows = [{"entry_odds": 1.8, "outcome": "WIN"}]
    assert build_edge_matrix(rows) == []
