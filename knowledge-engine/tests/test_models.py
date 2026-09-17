"""Pydantic model validation."""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from knowledge.schemas import Action, Bounds, Element, Observation, TransitionCreate


def test_valid_observation(observation):
    model = Observation(**observation)
    assert model.observation_id == "obs_000001"
    assert model.elements[0].bounds.width == 400


def test_missing_required_field(observation):
    observation.pop("observation_id")
    with pytest.raises(ValidationError):
        Observation(**observation)


def test_unknown_fields_are_preserved(observation):
    observation["explorer_note"] = "reached via deep link"
    model = Observation(**observation)
    assert model.model_dump()["explorer_note"] == "reached via deep link"


def test_optional_fields_default(observation):
    minimal = {"observation_id": "obs_000009"}
    model = Observation(**minimal)
    assert model.elements == []
    assert model.screenshot_path is None


def test_bad_screen_id_pattern(observation):
    observation["screen_id"] = "screen_1"
    with pytest.raises(ValidationError):
        Observation(**observation)


@pytest.mark.parametrize(
    "bad",
    [
        {"left": 500, "top": 400, "right": 100, "bottom": 480},  # left > right
        {"left": 100, "top": 500, "right": 500, "bottom": 480},  # top > bottom
        {"left": 100, "top": 400, "right": 500},  # missing bottom
        {"left": "a", "top": 400, "right": 500, "bottom": 480},  # non-integer
    ],
)
def test_invalid_bounds(bad):
    with pytest.raises(ValidationError):
        Bounds(**bad)


def test_valid_bounds_allow_zero_area():
    bounds = Bounds(left=10, top=10, right=10, bottom=10)
    assert bounds.area == 0


def test_element_defaults():
    element = Element(type="android.widget.TextView")
    assert element.clickable is False
    assert element.enabled is True
    assert element.bounds is None


def test_valid_action(action):
    model = Action(**action)
    assert model.action_type == "tap"
    assert model.target_screen_id is None


def test_action_accepts_future_fields(action):
    action.update(
        {
            "source_screen_id": "screen_000001",
            "target_screen_id": "screen_000002",
            "success": True,
            "result": "ok",
        }
    )
    model = Action(**action)
    assert model.success is True


def test_invalid_action_missing_type(action):
    action.pop("action_type")
    with pytest.raises(ValidationError):
        Action(**action)


def test_transition_requires_both_endpoints():
    with pytest.raises(ValidationError):
        TransitionCreate(source_screen_id="screen_000001")
