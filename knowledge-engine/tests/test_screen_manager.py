"""Screen identity, deduplication and persistence."""

from __future__ import annotations

import copy

import pytest

from knowledge import repositories as repo
from knowledge.database import session, transaction
from knowledge.exceptions import ConflictError
from knowledge.screen_manager import ScreenManager, screen_label

SCAN = "scan_test"


def _ingest(observation: dict) -> tuple[dict, bool, list[str]]:
    with transaction() as conn:
        return ScreenManager(SCAN).process_observation(conn, observation)


def test_new_screen_is_created(temp_db, observation):
    screen, created, _ = _ingest(observation)
    assert created is True
    assert screen["screen_id"] == "screen_000001"
    assert screen["observation_count"] == 1
    assert len(screen["elements"]) == 1


def test_identical_observation_reuses_screen(temp_db, observation):
    _ingest(observation)
    repeat = copy.deepcopy(observation)
    repeat["observation_id"] = "obs_000002"
    screen, created, _ = _ingest(repeat)
    assert created is False
    assert screen["screen_id"] == "screen_000001"
    assert screen["observation_count"] == 2


def test_different_screen_gets_new_id(temp_db, observation, second_observation):
    _ingest(observation)
    screen, created, _ = _ingest(second_observation)
    assert created is True
    assert screen["screen_id"] == "screen_000002"


def test_reported_screen_id_is_not_trusted(temp_db, observation):
    """A lying controller must not be able to merge two different screens."""
    _ingest(observation)
    other = copy.deepcopy(observation)
    other["observation_id"] = "obs_000002"
    other["screen_id"] = "screen_000001"  # claims the same screen
    other["elements"][0]["text"] = "Register"  # but it is a different UI
    screen, created, _ = _ingest(other)
    assert created is True
    assert screen["screen_id"] == "screen_000002"


def test_conflicting_screen_id_produces_warning(temp_db, observation):
    _ingest(observation)
    repeat = copy.deepcopy(observation)
    repeat["observation_id"] = "obs_000002"
    repeat["screen_id"] = "screen_000005"
    _, _, warnings = _ingest(repeat)
    assert any("screen_000005" in w for w in warnings)


def test_duplicate_observation_id_rejected(temp_db, observation):
    _ingest(observation)
    with pytest.raises(ConflictError):
        _ingest(copy.deepcopy(observation))


def test_elements_are_not_duplicated_on_rescan(temp_db, observation):
    _ingest(observation)
    repeat = copy.deepcopy(observation)
    repeat["observation_id"] = "obs_000002"
    _ingest(repeat)
    with session() as conn:
        elements = repo.list_elements(conn, SCAN, "screen_000001")
    assert len(elements) == 1


def test_data_survives_reconnect(temp_db, observation):
    _ingest(observation)
    with session() as conn:
        screen = repo.screen_with_elements(conn, SCAN, "screen_000001")
    assert screen is not None
    assert screen["fingerprint"]


def test_empty_observation_warns(temp_db, observation):
    observation["elements"] = []
    _, _, warnings = _ingest(observation)
    assert any("no elements" in w for w in warnings)


def test_screen_label_prefers_activity():
    assert screen_label({"screen_id": "screen_000001", "activity": "com.x.LoginActivity"}) == (
        "LoginActivity"
    )
    assert screen_label({"screen_id": "screen_000001", "elements": [{"text": "Welcome"}]}) == (
        "Welcome"
    )
    assert screen_label({"screen_id": "screen_000001"}) == "screen_000001"


def test_screen_ids_are_sequential_and_padded(temp_db, observation, second_observation):
    _ingest(observation)
    _ingest(second_observation)
    with session() as conn:
        ids = [s["screen_id"] for s in repo.list_screens(conn, SCAN)]
    assert ids == ["screen_000001", "screen_000002"]
