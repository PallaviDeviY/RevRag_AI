"""Fingerprint determinism and normalisation."""

from __future__ import annotations

import copy

from knowledge.fingerprint import (
    compute_fingerprint,
    compute_structural_fingerprint,
    normalize_bounds,
    normalize_text,
    similarity_score,
)


def _fp(observation: dict) -> str:
    return compute_fingerprint(
        package_name=observation["package_name"],
        activity=observation["activity"],
        elements=observation["elements"],
    )


def test_same_screen_same_fingerprint(observation):
    assert _fp(observation) == _fp(copy.deepcopy(observation))


def test_fingerprint_is_deterministic_across_calls(observation):
    assert len({_fp(observation) for _ in range(5)}) == 1


def test_element_ids_do_not_affect_fingerprint(observation):
    other = copy.deepcopy(observation)
    other["elements"][0]["element_id"] = "element_999999"
    assert _fp(observation) == _fp(other)


def test_observation_and_screen_id_do_not_affect_fingerprint(observation):
    other = copy.deepcopy(observation)
    other["observation_id"] = "obs_999999"
    other["screen_id"] = "screen_999999"
    assert _fp(observation) == _fp(other)


def test_different_text_gives_different_fingerprint(observation):
    other = copy.deepcopy(observation)
    other["elements"][0]["text"] = "Sign in"
    assert _fp(observation) != _fp(other)


def test_case_and_whitespace_are_normalised(observation):
    other = copy.deepcopy(observation)
    other["elements"][0]["text"] = "   LOG  IN   "
    observation["elements"][0]["text"] = "log in"
    assert _fp(observation) == _fp(other)


def test_element_order_does_not_matter(observation):
    other = copy.deepcopy(observation)
    extra = copy.deepcopy(observation["elements"][0])
    extra["text"] = "Cancel"
    observation["elements"].append(extra)
    other["elements"].insert(0, copy.deepcopy(extra))
    assert _fp(observation) == _fp(other)


def test_different_activity_gives_different_fingerprint(observation):
    other = copy.deepcopy(observation)
    other["activity"] = "com.example.app.OtherActivity"
    assert _fp(observation) != _fp(other)


def test_structural_fingerprint_ignores_text(observation):
    other = copy.deepcopy(observation)
    other["elements"][0]["text"] = "Sign in now"
    args = lambda o: dict(
        package_name=o["package_name"], activity=o["activity"], elements=o["elements"]
    )
    assert compute_structural_fingerprint(**args(observation)) == compute_structural_fingerprint(
        **args(other)
    )


def test_normalize_text_handles_none():
    assert normalize_text(None) == ""
    assert normalize_text("  A   B ") == "a b"


def test_normalize_bounds_handles_missing_and_buckets():
    assert normalize_bounds(None) is None
    assert normalize_bounds({"left": 1}) is None
    assert normalize_bounds({"left": 100, "top": 400, "right": 500, "bottom": 480}) == [
        100,
        400,
        500,
        480,
    ]
    assert normalize_bounds(
        {"left": 100, "top": 404, "right": 500, "bottom": 481}, bucket=16
    ) == [96, 400, 496, 480]


def test_similarity_score_bounds(observation):
    elements = observation["elements"]
    assert similarity_score(elements, elements) == 1.0
    assert similarity_score([], []) == 1.0
    different = [{"type": "android.widget.ImageView", "clickable": False}]
    assert similarity_score(elements, different) == 0.0
