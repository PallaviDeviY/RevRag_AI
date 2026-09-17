"""Shared pytest fixtures.

Every test gets a throwaway SQLite file under tmp_path. The production
database (``KNOWLEDGE_DB_PATH``) is never touched.
"""

from __future__ import annotations

import copy
import os
from pathlib import Path

import pytest

OBSERVATION = {
    "observation_id": "obs_000001",
    "screen_id": "screen_000001",
    "timestamp": "2026-09-17T21:30:00+05:30",
    "package_name": "com.example.app",
    "activity": "com.example.app.MainActivity",
    "screenshot_path": "screenshots/obs_000001.png",
    "ui_tree_path": "ui_trees/obs_000001.xml",
    "elements": [
        {
            "element_id": "element_000001",
            "type": "android.widget.Button",
            "text": "Login",
            "content_description": "Login",
            "resource_id": "com.example:id/login",
            "clickable": True,
            "enabled": True,
            "scrollable": False,
            "bounds": {"left": 100, "top": 400, "right": 500, "bottom": 480},
        }
    ],
}

ACTION = {
    "action_id": "action_000001",
    "action_type": "tap",
    "element_id": "element_000001",
    "bounds": {"left": 100, "top": 400, "right": 500, "bottom": 480},
}


@pytest.fixture
def observation() -> dict:
    return copy.deepcopy(OBSERVATION)


@pytest.fixture
def action() -> dict:
    return copy.deepcopy(ACTION)


@pytest.fixture
def second_observation() -> dict:
    """A different screen: different activity and different element."""
    obs = copy.deepcopy(OBSERVATION)
    obs["observation_id"] = "obs_000002"
    obs["screen_id"] = "screen_000002"
    obs["activity"] = "com.example.app.HomeActivity"
    obs["screenshot_path"] = "screenshots/obs_000002.png"
    obs["elements"] = [
        {
            "element_id": "element_000004",
            "type": "android.widget.TextView",
            "text": "Welcome",
            "content_description": None,
            "resource_id": "com.example:id/welcome",
            "clickable": False,
            "enabled": True,
            "scrollable": False,
            "bounds": {"left": 0, "top": 100, "right": 480, "bottom": 180},
        }
    ]
    return obs


@pytest.fixture
def temp_db(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Point the engine at an isolated database + output dir for this test."""
    db_path = tmp_path / "knowledge.db"
    monkeypatch.setenv("KNOWLEDGE_DB_PATH", str(db_path))
    monkeypatch.setenv("KNOWLEDGE_PACK_OUTPUT_DIR", str(tmp_path / "output"))
    monkeypatch.setenv("KNOWLEDGE_LOG_LEVEL", "WARNING")

    from knowledge.database import init_db

    init_db(db_path)
    return db_path


@pytest.fixture
def client(temp_db: Path):
    """FastAPI test client bound to the temp database."""
    from fastapi.testclient import TestClient

    from knowledge.api import app

    with TestClient(app) as test_client:
        yield test_client
