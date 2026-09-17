"""Repeat-scan stability comparison."""

from __future__ import annotations

import copy

from knowledge.stability_checker import compare_screen_sets


def _screen(screen_id, fingerprint, structural, elements=None):
    return {
        "screen_id": screen_id,
        "fingerprint": fingerprint,
        "structural_fingerprint": structural,
        "elements": elements or [{"type": "android.widget.Button", "text": "Login"}],
    }


def _scan(count=3):
    return [_screen(f"screen_{i:06d}", f"fp{i}", f"sf{i}") for i in range(1, count + 1)]


def test_identical_scans_score_one():
    previous = _scan()
    report = compare_screen_sets(previous, copy.deepcopy(previous))
    assert report["stability_score"] == 1.0
    assert report["matched_screens"] == 3
    assert report["fingerprint_matches"] == 3
    assert report["added_screens"] == []
    assert report["removed_screens"] == []


def test_added_screen():
    previous = _scan(2)
    current = copy.deepcopy(previous) + [_screen("screen_000003", "fp3", "sf3")]
    report = compare_screen_sets(previous, current)
    assert report["added_screens"] == ["screen_000003"]
    assert report["stability_score"] < 1.0


def test_removed_screen():
    previous = _scan(3)
    current = copy.deepcopy(previous[:2])
    report = compare_screen_sets(previous, current)
    assert report["removed_screens"] == ["screen_000003"]
    assert report["current_screen_count"] == 2


def test_changed_screen_same_structure():
    previous = _scan(1)
    current = copy.deepcopy(previous)
    current[0]["fingerprint"] = "fp1-changed"  # text changed, structure identical
    report = compare_screen_sets(previous, current)
    assert report["matched_screens"] == 0
    assert len(report["changed_screens"]) == 1
    assert report["changed_screens"][0]["previous_screen_id"] == "screen_000001"
    assert report["stability_score"] == 0.5


def test_changed_screen_by_similarity():
    previous = [
        _screen(
            "screen_000001",
            "fp1",
            "sf1",
            [{"type": "a"}, {"type": "b"}, {"type": "c"}, {"type": "d"}],
        )
    ]
    current = [
        _screen(
            "screen_000001",
            "fp1-x",
            "sf1-x",
            [{"type": "a"}, {"type": "b"}, {"type": "c"}, {"type": "e"}],
        )
    ]
    report = compare_screen_sets(previous, current)
    assert len(report["changed_screens"]) == 1
    assert report["changed_screens"][0]["similarity"] >= 0.6


def test_unrelated_screens_are_added_and_removed():
    previous = [_screen("screen_000001", "fp1", "sf1", [{"type": "a"}])]
    current = [_screen("screen_000001", "fp9", "sf9", [{"type": "z"}, {"type": "y"}])]
    report = compare_screen_sets(previous, current)
    assert report["added_screens"] == ["screen_000001"]
    assert report["removed_screens"] == ["screen_000001"]
    assert report["changed_screens"] == []


def test_empty_scans_warn():
    report = compare_screen_sets([], [], previous_scan_id="a", current_scan_id="b")
    assert report["stability_score"] == 1.0
    assert any("not meaningful" in w for w in report["warnings"])


def test_report_always_flags_metric_limits():
    report = compare_screen_sets(_scan(1), _scan(1))
    assert any("engineering metric" in w for w in report["warnings"])
