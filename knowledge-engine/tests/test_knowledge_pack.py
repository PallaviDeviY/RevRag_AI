"""Knowledge Pack generation."""

from __future__ import annotations

import copy
import json

import pytest

from knowledge import repositories as repo
from knowledge.database import session, transaction
from knowledge.knowledge_pack import build_pack, generate_and_store, validate_pack, write_pack
from knowledge.screen_manager import ScreenManager

SCAN = "scan_test"


def _seed(observation, second_observation):
    with transaction() as conn:
        manager = ScreenManager(SCAN)
        manager.process_observation(conn, observation)
        manager.process_observation(conn, second_observation)
        repo.upsert_action(
            conn,
            scan_id=SCAN,
            action={"action_id": "action_000001", "action_type": "tap", "element_id": "element_000001"},
        )
        repo.insert_transition(
            conn,
            scan_id=SCAN,
            source_screen_id="screen_000001",
            target_screen_id="screen_000002",
            action_id="action_000001",
            action_type="tap",
            element_id="element_000001",
        )


def test_required_compatibility_fields(temp_db, observation, second_observation):
    _seed(observation, second_observation)
    with session() as conn:
        pack = build_pack(conn, scan_id=SCAN, pack_id="pack_000001", run_design_analysis=False)
    assert pack["pack_id"] == "pack_000001"
    assert pack["source_observation_ids"] == ["obs_000001", "obs_000002"]


def test_statistics(temp_db, observation, second_observation):
    _seed(observation, second_observation)
    with session() as conn:
        pack = build_pack(conn, scan_id=SCAN, pack_id="pack_000001", run_design_analysis=False)
    stats = pack["statistics"]
    assert stats["screen_count"] == 2
    assert stats["element_count"] == 2
    assert stats["action_count"] == 1
    assert stats["transition_count"] == 1
    assert stats["journey_count"] == 1


def test_deterministic_output(temp_db, observation, second_observation):
    _seed(observation, second_observation)
    with session() as conn:
        args = dict(
            scan_id=SCAN,
            pack_id="pack_000001",
            generated_at="2026-09-17T00:00:00+00:00",
            run_design_analysis=False,
        )
        first = build_pack(conn, **args)
        second = build_pack(conn, **args)
    assert json.dumps(first, sort_keys=True) == json.dumps(second, sort_keys=True)


def test_no_duplicate_screens_after_repeat_observation(temp_db, observation, second_observation):
    _seed(observation, second_observation)
    repeat = copy.deepcopy(observation)
    repeat["observation_id"] = "obs_000003"
    with transaction() as conn:
        ScreenManager(SCAN).process_observation(conn, repeat)
    with session() as conn:
        pack = build_pack(conn, scan_id=SCAN, pack_id="pack_000002", run_design_analysis=False)
    screen_ids = [s["screen_id"] for s in pack["screens"]]
    assert screen_ids == sorted(set(screen_ids))
    assert len(pack["source_observation_ids"]) == 3


def test_warnings_for_missing_screenshots(temp_db, observation, second_observation):
    _seed(observation, second_observation)
    with session() as conn:
        pack = build_pack(conn, scan_id=SCAN, pack_id="pack_000001", run_design_analysis=True)
    assert any("Screenshot not found" in w for w in pack["warnings"])
    assert pack["design_language"]["confidence"] == 0.0


def test_empty_scan_produces_valid_pack(temp_db):
    with session() as conn:
        pack = build_pack(conn, scan_id="scan_empty", pack_id="pack_000001", run_design_analysis=False)
    assert pack["screens"] == []
    assert any("No screens" in w for w in pack["warnings"])


def test_validate_rejects_broken_pack():
    with pytest.raises(ValueError):
        validate_pack({"source_observation_ids": []})
    with pytest.raises(ValueError):
        validate_pack({"pack_id": "p", "source_observation_ids": "nope"})
    with pytest.raises(ValueError):
        validate_pack(
            {
                "pack_id": "p",
                "source_observation_ids": [],
                "screens": [{"screen_id": "s1"}, {"screen_id": "s1"}],
            }
        )


def test_generate_and_store_writes_file(temp_db, observation, second_observation, tmp_path):
    _seed(observation, second_observation)
    with transaction() as conn:
        pack = generate_and_store(conn, scan_id=SCAN, save_to_disk=True)
    output = tmp_path / "output" / f"{pack['pack_id']}.json"
    assert output.exists()
    assert json.loads(output.read_text())["pack_id"] == pack["pack_id"]


def test_latest_pack_round_trip(temp_db, observation, second_observation):
    _seed(observation, second_observation)
    with transaction() as conn:
        generate_and_store(conn, scan_id=SCAN, save_to_disk=False)
    with session() as conn:
        latest = repo.latest_pack(conn, SCAN)
    assert latest["statistics"]["screen_count"] == 2


def test_official_schema_validation(temp_db, observation, second_observation):
    import jsonschema
    from pathlib import Path

    _seed(observation, second_observation)
    with session() as conn:
        pack = build_pack(conn, scan_id=SCAN, pack_id="pack_000001", run_design_analysis=False)

    schema_path = Path(__file__).parent.parent / "schemas" / "knowledge_pack.v0_2.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))

    # Must pass official jsonschema validation without raising jsonschema.ValidationError
    jsonschema.validate(instance=pack, schema=schema)
