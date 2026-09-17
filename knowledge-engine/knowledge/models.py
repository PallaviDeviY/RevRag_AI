"""Database schema (DDL) and row dataclasses.

We use a hand-written SQLite repository layer rather than SQLAlchemy:
the data model is small, the queries are simple, and it keeps the module's
dependency list minimal (rule 8 in the brief). Swapping in SQLAlchemy later
only requires changing ``models.py`` + ``repositories.py``.

Every table carries ``scan_id`` so multiple scans of the same app can live in
one database. ``screen_id`` is only unique *within a scan*, which matches the
shared screen schema note ("within a controller session"); the primary key is
the composite ``(scan_id, screen_id)``.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS scans (
    scan_id        TEXT PRIMARY KEY,
    package_name   TEXT,
    created_at     TEXT NOT NULL,
    screen_counter INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS screens (
    scan_id                 TEXT NOT NULL,
    screen_id               TEXT NOT NULL,
    package_name            TEXT,
    activity                TEXT,
    screenshot_path         TEXT,
    ui_tree_path            TEXT,
    fingerprint             TEXT NOT NULL,
    structural_fingerprint  TEXT NOT NULL,
    first_seen_observation_id TEXT,
    observation_count       INTEGER NOT NULL DEFAULT 0,
    element_count           INTEGER NOT NULL DEFAULT 0,
    created_at              TEXT NOT NULL,
    updated_at              TEXT NOT NULL,
    metadata_json           TEXT,
    PRIMARY KEY (scan_id, screen_id),
    FOREIGN KEY (scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE
);

-- Deduplication key: one screen per exact fingerprint per scan.
CREATE UNIQUE INDEX IF NOT EXISTS ux_screens_scan_fingerprint
    ON screens(scan_id, fingerprint);
CREATE INDEX IF NOT EXISTS ix_screens_fingerprint ON screens(fingerprint);
CREATE INDEX IF NOT EXISTS ix_screens_structural ON screens(structural_fingerprint);
CREATE INDEX IF NOT EXISTS ix_screens_package ON screens(package_name);

CREATE TABLE IF NOT EXISTS observations (
    observation_id   TEXT NOT NULL,
    scan_id          TEXT NOT NULL,
    screen_id        TEXT,
    reported_screen_id TEXT,
    timestamp        TEXT,
    package_name     TEXT,
    activity         TEXT,
    screenshot_path  TEXT,
    ui_tree_path     TEXT,
    element_count    INTEGER NOT NULL DEFAULT 0,
    raw_json         TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (scan_id, observation_id),
    FOREIGN KEY (scan_id) REFERENCES scans(scan_id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_observations_screen ON observations(scan_id, screen_id);
CREATE INDEX IF NOT EXISTS ix_observations_id ON observations(observation_id);

CREATE TABLE IF NOT EXISTS elements (
    pk                  INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id             TEXT NOT NULL,
    screen_id           TEXT NOT NULL,
    element_id          TEXT,
    element_signature   TEXT NOT NULL,
    type                TEXT,
    text                TEXT,
    content_description TEXT,
    resource_id         TEXT,
    clickable           INTEGER NOT NULL DEFAULT 0,
    enabled             INTEGER NOT NULL DEFAULT 1,
    scrollable          INTEGER NOT NULL DEFAULT 0,
    bounds_left         INTEGER,
    bounds_top          INTEGER,
    bounds_right        INTEGER,
    bounds_bottom       INTEGER,
    raw_json            TEXT,
    FOREIGN KEY (scan_id, screen_id) REFERENCES screens(scan_id, screen_id) ON DELETE CASCADE
);

-- No duplicate elements within a screen.
CREATE UNIQUE INDEX IF NOT EXISTS ux_elements_screen_signature
    ON elements(scan_id, screen_id, element_signature);
CREATE INDEX IF NOT EXISTS ix_elements_screen ON elements(scan_id, screen_id);
CREATE INDEX IF NOT EXISTS ix_elements_element_id ON elements(element_id);

CREATE TABLE IF NOT EXISTS actions (
    action_id        TEXT NOT NULL,
    scan_id          TEXT NOT NULL,
    action_type      TEXT NOT NULL,
    element_id       TEXT,
    source_screen_id TEXT,
    target_screen_id TEXT,
    bounds_left      INTEGER,
    bounds_top       INTEGER,
    bounds_right     INTEGER,
    bounds_bottom    INTEGER,
    timestamp        TEXT,
    result           TEXT,
    success          INTEGER,
    raw_json         TEXT NOT NULL,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (scan_id, action_id)
);

CREATE INDEX IF NOT EXISTS ix_actions_id ON actions(action_id);
CREATE INDEX IF NOT EXISTS ix_actions_source ON actions(scan_id, source_screen_id);
CREATE INDEX IF NOT EXISTS ix_actions_target ON actions(scan_id, target_screen_id);

CREATE TABLE IF NOT EXISTS transitions (
    transition_id    TEXT NOT NULL,
    scan_id          TEXT NOT NULL,
    source_screen_id TEXT NOT NULL,
    target_screen_id TEXT NOT NULL,
    action_id        TEXT,
    action_type      TEXT,
    element_id       TEXT,
    success          INTEGER,
    metadata_json    TEXT,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (scan_id, transition_id)
);

CREATE INDEX IF NOT EXISTS ix_transitions_source ON transitions(scan_id, source_screen_id);
CREATE INDEX IF NOT EXISTS ix_transitions_target ON transitions(scan_id, target_screen_id);
CREATE INDEX IF NOT EXISTS ix_transitions_action ON transitions(action_id);
CREATE UNIQUE INDEX IF NOT EXISTS ux_transitions_edge
    ON transitions(scan_id, source_screen_id, target_screen_id, IFNULL(action_id, ''));

CREATE TABLE IF NOT EXISTS journeys (
    journey_id       TEXT NOT NULL,
    scan_id          TEXT NOT NULL,
    name             TEXT NOT NULL,
    start_screen_id  TEXT NOT NULL,
    end_screen_id    TEXT NOT NULL,
    screen_ids_json  TEXT NOT NULL,
    action_ids_json  TEXT NOT NULL,
    transition_ids_json TEXT NOT NULL,
    length           INTEGER NOT NULL,
    kind             TEXT NOT NULL,
    metadata_json    TEXT,
    created_at       TEXT NOT NULL,
    PRIMARY KEY (scan_id, journey_id)
);

CREATE TABLE IF NOT EXISTS design_language (
    pk            INTEGER PRIMARY KEY AUTOINCREMENT,
    scan_id       TEXT NOT NULL,
    screen_id     TEXT,
    payload_json  TEXT NOT NULL,
    created_at    TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_design_scan ON design_language(scan_id);

CREATE TABLE IF NOT EXISTS knowledge_packs (
    pack_id      TEXT PRIMARY KEY,
    scan_id      TEXT NOT NULL,
    package_name TEXT,
    schema_version TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    file_path    TEXT,
    created_at   TEXT NOT NULL
);

CREATE INDEX IF NOT EXISTS ix_packs_scan ON knowledge_packs(scan_id, created_at);
"""


@dataclass
class ScreenRow:
    """In-memory view of a ``screens`` row plus its elements."""

    scan_id: str
    screen_id: str
    fingerprint: str
    structural_fingerprint: str
    package_name: str | None = None
    activity: str | None = None
    screenshot_path: str | None = None
    ui_tree_path: str | None = None
    first_seen_observation_id: str | None = None
    observation_count: int = 0
    element_count: int = 0
    elements: list[dict[str, Any]] = field(default_factory=list)
    metadata: dict[str, Any] | None = None

    def to_api_dict(self) -> dict[str, Any]:
        """Shape used by ``ScreenOut``."""
        return {
            "screen_id": self.screen_id,
            "package_name": self.package_name,
            "activity": self.activity,
            "screenshot_path": self.screenshot_path,
            "ui_tree_path": self.ui_tree_path,
            "fingerprint": self.fingerprint,
            "structural_fingerprint": self.structural_fingerprint,
            "element_count": self.element_count,
            "elements": self.elements,
            "first_seen_observation_id": self.first_seen_observation_id,
            "observation_count": self.observation_count,
            "scan_id": self.scan_id,
        }


@dataclass
class TransitionRow:
    scan_id: str
    transition_id: str
    source_screen_id: str
    target_screen_id: str
    action_id: str | None = None
    action_type: str | None = None
    element_id: str | None = None
    success: bool | None = None
    metadata: dict[str, Any] | None = None
