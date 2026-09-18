"""End-to-end integration tests for Member 1 + Member 2 + Member 3.

Verifies:
1. Member 1 Android Controller -> Member 2 AI Brain mock flow
2. Member 2 Decision -> Member 3 Knowledge Engine action & transition storage
3. Comprehensive Action Matrix (tap, type, scroll, swipe, back, invalid, failed, self-loop)
4. Full autonomous exploration pipeline with mock backend and knowledge engine persistence
5. Structural schema validation of generated Knowledge Pack against knowledge_pack.v0_2.schema.json
"""

from __future__ import annotations

import copy
import json
from pathlib import Path

import jsonschema
import pytest

from ai.ai_brain import AIBrain
from ai.autonomous_runner import AutonomousRunner
from android.actions import ActionExecutor
from android.config import load_config
from knowledge import repositories as repo
from knowledge.database import session, transaction
from knowledge.screen_manager import ScreenManager


# ==============================================================================
# 1. Member 1 -> Member 2 Mock Flow
# ==============================================================================

def test_member1_to_member2_mock_flow(tmp_path, monkeypatch):
    """Verify Member 1 generates valid observations that Member 2 AI Brain consumes."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path / "screenshots"))
    monkeypatch.setenv("UI_TREE_DIR", str(tmp_path / "ui_trees"))
    monkeypatch.setenv("OBSERVATION_DIR", str(tmp_path / "observations"))
    monkeypatch.setenv("ANDROID_MOCK", "1")

    executor = ActionExecutor(config=load_config(), mock=True)
    launch_res = executor.launch("com.example.app")

    assert launch_res.success, f"Mock launch failed: {launch_res.error}"
    assert launch_res.observation is not None

    obs = launch_res.observation
    obs_dict = obs.to_dict()

    # Verify M1 Observation contract
    assert obs_dict["observation_id"].startswith("obs_")
    assert obs_dict["package_name"] == "com.example.app"
    assert obs_dict["activity"] == "com.example.app.MainActivity"
    assert len(obs_dict["elements"]) > 0

    # Feed M1 Observation into M2 AI Brain
    brain = AIBrain()
    decision = brain.decide(obs_dict)

    # Verify M2 Decision contract
    assert "decision_id" in decision
    assert "validated_action" in decision
    action = decision["validated_action"]
    assert action is not None
    assert action["action_type"] in ["tap", "type", "scroll", "swipe", "back"]
    assert action.get("element_id") is not None or action.get("bounds") is not None


# ==============================================================================
# 2. Member 2 -> Member 3 Action & Transition Storage
# ==============================================================================

def test_member2_to_member3_action_storage(temp_db, observation, second_observation):
    """Verify actions and transitions from Member 2 are persisted into Member 3 SQLite."""
    scan_id = "scan_m2_m3_test"

    with transaction() as conn:
        repo.ensure_scan(conn, scan_id=scan_id, package_name="com.example.app")
        manager = ScreenManager(scan_id)

        screen_1, _, _ = manager.process_observation(conn, observation)
        screen_2, _, _ = manager.process_observation(conn, second_observation)

        action_payload = {
            "action_id": "action_test_001",
            "action_type": "tap",
            "element_id": "element_000001",
            "bounds": {"left": 100, "top": 400, "right": 500, "bottom": 480},
            "source_screen_id": screen_1["screen_id"],
            "target_screen_id": screen_2["screen_id"],
            "success": True,
        }
        repo.upsert_action(conn, scan_id=scan_id, action=action_payload)

        trans_id = repo.insert_transition(
            conn,
            scan_id=scan_id,
            source_screen_id=screen_1["screen_id"],
            target_screen_id=screen_2["screen_id"],
            action_id="action_test_001",
            action_type="tap",
            element_id="element_000001",
            success=True,
        )

    with session() as conn:
        # Check action in DB
        cur = conn.cursor()
        cur.execute("SELECT action_id, action_type, element_id, source_screen_id, target_screen_id, success FROM actions WHERE action_id = ?", ("action_test_001",))
        row = cur.fetchone()
        assert row is not None
        assert row[0] == "action_test_001"
        assert row[1] == "tap"
        assert row[2] == "element_000001"
        assert row[3] == screen_1["screen_id"]
        assert row[4] == screen_2["screen_id"]
        assert row[5] == 1

        # Check transition in DB
        cur.execute("SELECT transition_id, source_screen_id, target_screen_id, action_type, success FROM transitions WHERE transition_id = ?", (trans_id,))
        t_row = cur.fetchone()
        assert t_row is not None
        assert t_row[1] == screen_1["screen_id"]
        assert t_row[2] == screen_2["screen_id"]
        assert t_row[3] == "tap"
        assert t_row[4] == 1


# ==============================================================================
# 3. Action Matrix: tap, type, scroll, swipe, back, invalid, failed, self-loop
# ==============================================================================

def test_action_matrix(temp_db, tmp_path, monkeypatch):
    """Comprehensive action matrix testing execution and persistence."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path / "screenshots"))
    monkeypatch.setenv("UI_TREE_DIR", str(tmp_path / "ui_trees"))
    monkeypatch.setenv("OBSERVATION_DIR", str(tmp_path / "observations"))
    monkeypatch.setenv("ANDROID_MOCK", "1")

    scan_id = "scan_matrix_test"
    executor = ActionExecutor(config=load_config(), mock=True)

    with transaction() as conn:
        repo.ensure_scan(conn, scan_id=scan_id, package_name="com.example.app")

    manager = ScreenManager(scan_id)

    # Initial launch
    launch_res = executor.launch("com.example.app")
    assert launch_res.success
    with transaction() as conn:
        s1, _, _ = manager.process_observation(conn, launch_res.observation.to_dict())

    # a) TAP: valid element (Login button) -> transitions launch -> form (s1 -> s2)
    login_btn = next(el for el in launch_res.observation.elements if el.text == "Login")
    tap_res = executor.execute({
        "action_id": "act_matrix_tap",
        "action_type": "tap",
        "element_id": login_btn.element_id,
        "bounds": {"left": 100, "top": 400, "right": 500, "bottom": 480},
    })
    assert tap_res.success
    with transaction() as conn:
        s2, _, _ = manager.process_observation(conn, tap_res.observation.to_dict())
        repo.upsert_action(
            conn,
            scan_id=scan_id,
            action={
                "action_id": "act_matrix_tap",
                "action_type": "tap",
                "element_id": login_btn.element_id,
                "source_screen_id": s1["screen_id"],
                "target_screen_id": s2["screen_id"],
                "success": True,
            },
        )
        repo.insert_transition(
            conn,
            scan_id=scan_id,
            source_screen_id=s1["screen_id"],
            target_screen_id=s2["screen_id"],
            action_id="act_matrix_tap",
            action_type="tap",
            element_id=login_btn.element_id,
            success=True,
        )

    # b) SELF-LOOP: tapping on form screen stays on form screen (s2 -> s2)
    email_el = next(el for el in tap_res.observation.elements if el.resource_id and el.resource_id.endswith("/email"))
    tap_self_res = executor.execute({
        "action_id": "act_matrix_tap_self",
        "action_type": "tap",
        "element_id": email_el.element_id,
        "bounds": email_el.bounds.to_dict(),
    })
    assert tap_self_res.success
    with transaction() as conn:
        s2_loop, _, _ = manager.process_observation(conn, tap_self_res.observation.to_dict())
        assert s2_loop["screen_id"] == s2["screen_id"], "Tapping on form should stay on same screen (self-loop)"
        repo.upsert_action(
            conn,
            scan_id=scan_id,
            action={
                "action_id": "act_matrix_tap_self",
                "action_type": "tap",
                "element_id": email_el.element_id,
                "source_screen_id": s2["screen_id"],
                "target_screen_id": s2_loop["screen_id"],
                "success": True,
            },
        )
        repo.insert_transition(
            conn,
            scan_id=scan_id,
            source_screen_id=s2["screen_id"],
            target_screen_id=s2_loop["screen_id"],
            action_id="act_matrix_tap_self",
            action_type="tap",
            element_id=email_el.element_id,
            success=True,
        )

    # c) TYPE: type text into email field -> transitions to typed form (s2 -> s3)
    type_res = executor.execute({
        "action_id": "act_matrix_type",
        "action_type": "type",
        "element_id": email_el.element_id,
        "text": "test@example.com",
    })
    assert type_res.success
    with transaction() as conn:
        s3, _, _ = manager.process_observation(conn, type_res.observation.to_dict())
        repo.upsert_action(
            conn,
            scan_id=scan_id,
            action={
                "action_id": "act_matrix_type",
                "action_type": "type",
                "element_id": email_el.element_id,
                "source_screen_id": s2["screen_id"],
                "target_screen_id": s3["screen_id"],
                "success": True,
            },
        )
        repo.insert_transition(
            conn,
            scan_id=scan_id,
            source_screen_id=s2["screen_id"],
            target_screen_id=s3["screen_id"],
            action_id="act_matrix_type",
            action_type="type",
            element_id=email_el.element_id,
            success=True,
        )

    # d) SCROLL: scroll down -> transitions to scrolled screen (s3 -> s4)
    scroll_res = executor.execute({
        "action_id": "act_matrix_scroll",
        "action_type": "scroll",
        "direction": "down",
    })
    assert scroll_res.success
    with transaction() as conn:
        s4, _, _ = manager.process_observation(conn, scroll_res.observation.to_dict())
        repo.upsert_action(
            conn,
            scan_id=scan_id,
            action={
                "action_id": "act_matrix_scroll",
                "action_type": "scroll",
                "source_screen_id": s3["screen_id"],
                "target_screen_id": s4["screen_id"],
                "success": True,
            },
        )
        repo.insert_transition(
            conn,
            scan_id=scan_id,
            source_screen_id=s3["screen_id"],
            target_screen_id=s4["screen_id"],
            action_id="act_matrix_scroll",
            action_type="scroll",
            element_id=None,
            success=True,
        )

    # e) SWIPE: swipe coordinates
    swipe_res = executor.execute({
        "action_id": "act_matrix_swipe",
        "action_type": "swipe",
        "x": 100,
        "y": 800,
        "x2": 100,
        "y2": 200,
        "duration_ms": 300,
    })
    assert swipe_res.success

    # f) BACK: press back -> returns to launch screen (s4 -> s5 == s1)
    back_res = executor.execute({
        "action_id": "act_matrix_back",
        "action_type": "back",
    })
    assert back_res.success
    with transaction() as conn:
        s5, _, _ = manager.process_observation(conn, back_res.observation.to_dict())
        assert s5["screen_id"] == s1["screen_id"], "Pressing back should return to initial launch screen"
        repo.insert_transition(
            conn,
            scan_id=scan_id,
            source_screen_id=s4["screen_id"],
            target_screen_id=s5["screen_id"],
            action_id="act_matrix_back",
            action_type="back",
            element_id=None,
            success=True,
        )

    # g) INVALID ACTION: unsupported action type
    inv_res = executor.execute({
        "action_id": "act_matrix_invalid",
        "action_type": "unsupported_xyz",
    })
    assert not inv_res.success
    assert inv_res.error is not None
    assert inv_res.error.code == "UNSUPPORTED_ACTION"

    # h) FAILED ACTION: targeting non-existent element
    fail_res = executor.execute({
        "action_id": "act_matrix_failed",
        "action_type": "tap",
        "element_id": "element_nonexistent_999",
    })
    assert not fail_res.success
    assert fail_res.error is not None
    assert fail_res.error.code == "ELEMENT_NOT_FOUND"

    # Store failed action in Knowledge Engine
    with transaction() as conn:
        repo.upsert_action(
            conn,
            scan_id=scan_id,
            action={
                "action_id": "act_matrix_failed",
                "action_type": "tap",
                "element_id": "element_nonexistent_999",
                "source_screen_id": s5["screen_id"],
                "success": False,
            },
        )

    # Verify all records in SQLite
    with session() as conn:
        cur = conn.cursor()
        actions_count = cur.execute("SELECT COUNT(*) FROM actions WHERE scan_id = ?", (scan_id,)).fetchone()[0]
        assert actions_count == 5  # tap, tap_self, type, scroll, failed

        transitions_count = cur.execute("SELECT COUNT(*) FROM transitions WHERE scan_id = ?", (scan_id,)).fetchone()[0]
        assert transitions_count == 5  # s1->s2, s2->s2 (self-loop), s2->s3, s3->s4, s4->s1

        # Check self-loop transition explicitly
        self_loop = cur.execute(
            "SELECT action_type, source_screen_id, target_screen_id FROM transitions WHERE source_screen_id = target_screen_id AND scan_id = ?",
            (scan_id,)
        ).fetchone()
        assert self_loop is not None
        assert self_loop[0] == "tap"
        assert self_loop[1] == s2["screen_id"]


# ==============================================================================
# 4. Complete M1 + M2 + M3 Autonomous Pipeline
# ==============================================================================

def test_complete_m1_m2_m3_pipeline(temp_db, tmp_path, monkeypatch):
    """Run AutonomousRunner with mock backend and assert full pipeline execution."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path / "screenshots"))
    monkeypatch.setenv("UI_TREE_DIR", str(tmp_path / "ui_trees"))
    monkeypatch.setenv("OBSERVATION_DIR", str(tmp_path / "observations"))
    monkeypatch.setenv("ANDROID_MOCK", "1")

    scan_id = "scan_pipeline_test"
    runner = AutonomousRunner(
        max_steps=4,
        mock=True,
        enable_knowledge_engine=True,
        scan_id=scan_id,
        package_name="com.example.app",
    )

    result = runner.run()

    assert result["success"] is True
    assert result["actions_executed"] >= 1
    assert result["scan_id"] == scan_id
    pack = result["knowledge_pack"]
    assert pack is not None
    assert pack["pack_id"].startswith("pack_")
    assert len(pack["screens"]) >= 1
    assert len(pack["transitions"]) >= 1

    # Verify SQLite persistence
    with session() as conn:
        cur = conn.cursor()
        assert cur.execute("SELECT COUNT(*) FROM scans WHERE scan_id = ?", (scan_id,)).fetchone()[0] == 1
        assert cur.execute("SELECT COUNT(*) FROM screens WHERE scan_id = ?", (scan_id,)).fetchone()[0] >= 1
        assert cur.execute("SELECT COUNT(*) FROM actions WHERE scan_id = ?", (scan_id,)).fetchone()[0] >= 1
        assert cur.execute("SELECT COUNT(*) FROM transitions WHERE scan_id = ?", (scan_id,)).fetchone()[0] >= 1
        assert cur.execute("SELECT COUNT(*) FROM knowledge_packs WHERE scan_id = ?", (scan_id,)).fetchone()[0] >= 1

    # Verify generated pack file
    pack_file = tmp_path / "output" / f"{pack['pack_id']}.json"
    assert pack_file.is_file()
    on_disk = json.loads(pack_file.read_text(encoding="utf-8"))
    assert on_disk["pack_id"] == pack["pack_id"]


# ==============================================================================
# 5. Knowledge Pack Structural Schema Conformance
# ==============================================================================

def test_knowledge_pack_structural_conformance(temp_db, tmp_path, monkeypatch):
    """Validate generated Knowledge Pack against knowledge_pack.v0_2.schema.json."""
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path / "screenshots"))
    monkeypatch.setenv("UI_TREE_DIR", str(tmp_path / "ui_trees"))
    monkeypatch.setenv("OBSERVATION_DIR", str(tmp_path / "observations"))
    monkeypatch.setenv("ANDROID_MOCK", "1")

    runner = AutonomousRunner(
        max_steps=3,
        mock=True,
        enable_knowledge_engine=True,
        scan_id="scan_schema_test",
        package_name="com.example.app",
    )
    result = runner.run()
    pack = result["knowledge_pack"]

    schema_file = Path(__file__).parent.parent / "schemas" / "knowledge_pack.v0_2.schema.json"
    schema = json.loads(schema_file.read_text(encoding="utf-8"))

    # Must pass validation without raising jsonschema.ValidationError
    jsonschema.validate(instance=pack, schema=schema)

    # Assert all mandatory sections from schema
    required_keys = [
        "schema_version",
        "pack_id",
        "scan_id",
        "app",
        "generated_at",
        "source_observation_ids",
        "screens",
        "transitions",
        "journeys",
        "design_language",
        "statistics",
        "warnings",
    ]
    for key in required_keys:
        assert key in pack, f"Missing required top-level key: {key}"

    assert pack["app"]["package_name"] == "com.example.app"
