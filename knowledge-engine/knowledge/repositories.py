"""Repository layer: every SQL statement lives here.

Functions take an open ``sqlite3.Connection`` so the caller controls the
transaction boundary. They work with plain dicts, never Pydantic models, which
keeps this layer independent of the API framework.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from .exceptions import ConflictError, NotFoundError
from .fingerprint import canonical_element

SCREEN_ID_TEMPLATE = "screen_{:06d}"
TRANSITION_ID_TEMPLATE = "transition_{:06d}"
JOURNEY_ID_TEMPLATE = "journey_{:06d}"
PACK_ID_TEMPLATE = "pack_{:06d}"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json(value: Any) -> str | None:
    if value is None:
        return None
    return json.dumps(value, sort_keys=True, default=str)


def _loads(value: str | None, default: Any) -> Any:
    if not value:
        return default
    try:
        return json.loads(value)
    except json.JSONDecodeError:  # pragma: no cover - corrupt row
        return default


# --------------------------------------------------------------------------
# scans
# --------------------------------------------------------------------------

def ensure_scan(conn: sqlite3.Connection, scan_id: str, package_name: str | None = None) -> None:
    """Create the scan row if missing, and backfill the package name once."""
    conn.execute(
        "INSERT OR IGNORE INTO scans (scan_id, package_name, created_at, screen_counter)"
        " VALUES (?, ?, ?, 0)",
        (scan_id, package_name, _now()),
    )
    if package_name:
        conn.execute(
            "UPDATE scans SET package_name = ? WHERE scan_id = ? AND"
            " (package_name IS NULL OR package_name = '')",
            (package_name, scan_id),
        )


def list_scans(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM scans ORDER BY created_at, scan_id").fetchall()
    return [dict(row) for row in rows]


def next_screen_id(conn: sqlite3.Connection, scan_id: str) -> str:
    """Atomically allocate the next ``screen_NNNNNN`` for this scan.

    The counter lives in the ``scans`` table and is incremented inside the
    caller's write transaction, so it cannot hand out duplicates the way an
    in-process counter would.
    """
    conn.execute(
        "UPDATE scans SET screen_counter = screen_counter + 1 WHERE scan_id = ?", (scan_id,)
    )
    row = conn.execute(
        "SELECT screen_counter FROM scans WHERE scan_id = ?", (scan_id,)
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Unknown scan_id '{scan_id}'")
    return SCREEN_ID_TEMPLATE.format(int(row["screen_counter"]))


def _next_sequence(conn: sqlite3.Connection, table: str, column: str, scan_id: str, template: str) -> str:
    row = conn.execute(f"SELECT COUNT(*) AS c FROM {table} WHERE scan_id = ?", (scan_id,)).fetchone()
    index = int(row["c"]) + 1
    while True:
        candidate = template.format(index)
        exists = conn.execute(
            f"SELECT 1 FROM {table} WHERE scan_id = ? AND {column} = ?", (scan_id, candidate)
        ).fetchone()
        if exists is None:
            return candidate
        index += 1


# --------------------------------------------------------------------------
# observations
# --------------------------------------------------------------------------

def insert_observation(
    conn: sqlite3.Connection,
    *,
    scan_id: str,
    observation: Mapping[str, Any],
    resolved_screen_id: str | None,
) -> None:
    """Persist raw observation metadata plus the screen we resolved it to."""
    observation_id = observation["observation_id"]
    existing = conn.execute(
        "SELECT 1 FROM observations WHERE scan_id = ? AND observation_id = ?",
        (scan_id, observation_id),
    ).fetchone()
    if existing:
        raise ConflictError(
            f"observation_id '{observation_id}' already ingested for scan '{scan_id}'"
        )
    timestamp = observation.get("timestamp")
    conn.execute(
        """
        INSERT INTO observations (
            observation_id, scan_id, screen_id, reported_screen_id, timestamp,
            package_name, activity, screenshot_path, ui_tree_path,
            element_count, raw_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            observation_id,
            scan_id,
            resolved_screen_id,
            observation.get("screen_id"),
            str(timestamp) if timestamp is not None else None,
            observation.get("package_name"),
            observation.get("activity"),
            observation.get("screenshot_path"),
            observation.get("ui_tree_path"),
            len(observation.get("elements") or []),
            _json(observation),
            _now(),
        ),
    )


def list_observation_ids(conn: sqlite3.Connection, scan_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT observation_id FROM observations WHERE scan_id = ? ORDER BY observation_id",
        (scan_id,),
    ).fetchall()
    return [row["observation_id"] for row in rows]


def get_observation(conn: sqlite3.Connection, scan_id: str, observation_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM observations WHERE scan_id = ? AND observation_id = ?",
        (scan_id, observation_id),
    ).fetchone()
    return dict(row) if row else None


# --------------------------------------------------------------------------
# screens + elements
# --------------------------------------------------------------------------

def find_screen_by_fingerprint(
    conn: sqlite3.Connection, scan_id: str, fingerprint: str
) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM screens WHERE scan_id = ? AND fingerprint = ?", (scan_id, fingerprint)
    ).fetchone()
    return dict(row) if row else None


def get_screen(conn: sqlite3.Connection, scan_id: str, screen_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM screens WHERE scan_id = ? AND screen_id = ?", (scan_id, screen_id)
    ).fetchone()
    return dict(row) if row else None


def insert_screen(
    conn: sqlite3.Connection,
    *,
    scan_id: str,
    screen_id: str,
    fingerprint: str,
    structural_fingerprint: str,
    package_name: str | None,
    activity: str | None,
    screenshot_path: str | None,
    ui_tree_path: str | None,
    first_seen_observation_id: str | None,
    element_count: int,
    metadata: Mapping[str, Any] | None = None,
) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO screens (
            scan_id, screen_id, package_name, activity, screenshot_path, ui_tree_path,
            fingerprint, structural_fingerprint, first_seen_observation_id,
            observation_count, element_count, created_at, updated_at, metadata_json
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?, ?, ?)
        """,
        (
            scan_id,
            screen_id,
            package_name,
            activity,
            screenshot_path,
            ui_tree_path,
            fingerprint,
            structural_fingerprint,
            first_seen_observation_id,
            element_count,
            now,
            now,
            _json(dict(metadata) if metadata else None),
        ),
    )


def increment_observation_count(conn: sqlite3.Connection, scan_id: str, screen_id: str) -> int:
    conn.execute(
        "UPDATE screens SET observation_count = observation_count + 1, updated_at = ?"
        " WHERE scan_id = ? AND screen_id = ?",
        (_now(), scan_id, screen_id),
    )
    row = conn.execute(
        "SELECT observation_count FROM screens WHERE scan_id = ? AND screen_id = ?",
        (scan_id, screen_id),
    ).fetchone()
    if row is None:
        raise NotFoundError(f"Unknown screen '{screen_id}' in scan '{scan_id}'")
    return int(row["observation_count"])


def element_signature(element: Mapping[str, Any]) -> str:
    """Stable dedup key for an element inside one screen (ignores element_id)."""
    return json.dumps(canonical_element(element, include_text=True), sort_keys=True)


def upsert_elements(
    conn: sqlite3.Connection, *, scan_id: str, screen_id: str, elements: Sequence[Mapping[str, Any]]
) -> int:
    """Insert elements, ignoring ones already stored for this screen.

    Returns the number of rows actually inserted.
    """
    inserted = 0
    for element in elements:
        bounds = element.get("bounds") or {}
        if not isinstance(bounds, Mapping):
            bounds = {}
        cursor = conn.execute(
            """
            INSERT OR IGNORE INTO elements (
                scan_id, screen_id, element_id, element_signature, type, text,
                content_description, resource_id, clickable, enabled, scrollable,
                bounds_left, bounds_top, bounds_right, bounds_bottom, raw_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                scan_id,
                screen_id,
                element.get("element_id"),
                element_signature(element),
                element.get("type"),
                element.get("text"),
                element.get("content_description"),
                element.get("resource_id"),
                int(bool(element.get("clickable"))),
                int(bool(element.get("enabled", True))),
                int(bool(element.get("scrollable"))),
                bounds.get("left"),
                bounds.get("top"),
                bounds.get("right"),
                bounds.get("bottom"),
                _json(dict(element)),
            ),
        )
        inserted += cursor.rowcount if cursor.rowcount > 0 else 0
    conn.execute(
        "UPDATE screens SET element_count = ("
        "  SELECT COUNT(*) FROM elements WHERE scan_id = ? AND screen_id = ?"
        ") WHERE scan_id = ? AND screen_id = ?",
        (scan_id, screen_id, scan_id, screen_id),
    )
    return inserted


def list_elements(conn: sqlite3.Connection, scan_id: str, screen_id: str) -> list[dict[str, Any]]:
    """Return a screen's elements in deterministic order."""
    rows = conn.execute(
        "SELECT * FROM elements WHERE scan_id = ? AND screen_id = ? ORDER BY element_signature",
        (scan_id, screen_id),
    ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        bounds = None
        if row["bounds_left"] is not None:
            bounds = {
                "left": row["bounds_left"],
                "top": row["bounds_top"],
                "right": row["bounds_right"],
                "bottom": row["bounds_bottom"],
            }
        result.append(
            {
                "element_id": row["element_id"],
                "type": row["type"],
                "text": row["text"],
                "content_description": row["content_description"],
                "resource_id": row["resource_id"],
                "clickable": bool(row["clickable"]),
                "enabled": bool(row["enabled"]),
                "scrollable": bool(row["scrollable"]),
                "bounds": bounds,
            }
        )
    return result


def list_screens(
    conn: sqlite3.Connection, scan_id: str, package_name: str | None = None
) -> list[dict[str, Any]]:
    if package_name:
        rows = conn.execute(
            "SELECT * FROM screens WHERE scan_id = ? AND package_name = ? ORDER BY screen_id",
            (scan_id, package_name),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM screens WHERE scan_id = ? ORDER BY screen_id", (scan_id,)
        ).fetchall()
    return [dict(row) for row in rows]


def screen_with_elements(
    conn: sqlite3.Connection, scan_id: str, screen_id: str
) -> dict[str, Any] | None:
    screen = get_screen(conn, scan_id, screen_id)
    if screen is None:
        return None
    screen["elements"] = list_elements(conn, scan_id, screen_id)
    screen["metadata"] = _loads(screen.get("metadata_json"), None)
    return screen


# --------------------------------------------------------------------------
# actions
# --------------------------------------------------------------------------

def upsert_action(conn: sqlite3.Connection, *, scan_id: str, action: Mapping[str, Any]) -> None:
    bounds = action.get("bounds") or {}
    if not isinstance(bounds, Mapping):
        bounds = {}
    success = action.get("success")
    conn.execute(
        """
        INSERT INTO actions (
            action_id, scan_id, action_type, element_id, source_screen_id, target_screen_id,
            bounds_left, bounds_top, bounds_right, bounds_bottom,
            timestamp, result, success, raw_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(scan_id, action_id) DO UPDATE SET
            action_type = excluded.action_type,
            element_id = COALESCE(excluded.element_id, actions.element_id),
            source_screen_id = COALESCE(excluded.source_screen_id, actions.source_screen_id),
            target_screen_id = COALESCE(excluded.target_screen_id, actions.target_screen_id),
            result = COALESCE(excluded.result, actions.result),
            success = COALESCE(excluded.success, actions.success),
            raw_json = excluded.raw_json
        """,
        (
            action["action_id"],
            scan_id,
            action["action_type"],
            action.get("element_id"),
            action.get("source_screen_id"),
            action.get("target_screen_id"),
            bounds.get("left"),
            bounds.get("top"),
            bounds.get("right"),
            bounds.get("bottom"),
            str(action["timestamp"]) if action.get("timestamp") is not None else None,
            action.get("result"),
            None if success is None else int(bool(success)),
            _json(dict(action)),
            _now(),
        ),
    )


def get_action(conn: sqlite3.Connection, scan_id: str, action_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT * FROM actions WHERE scan_id = ? AND action_id = ?", (scan_id, action_id)
    ).fetchone()
    return dict(row) if row else None


def list_actions(conn: sqlite3.Connection, scan_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM actions WHERE scan_id = ? ORDER BY action_id", (scan_id,)
    ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------
# transitions
# --------------------------------------------------------------------------

def insert_transition(
    conn: sqlite3.Connection,
    *,
    scan_id: str,
    source_screen_id: str,
    target_screen_id: str,
    action_id: str | None,
    action_type: str | None,
    element_id: str | None,
    success: bool | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> str:
    """Create an edge. Returns the transition id (existing one if duplicate)."""
    existing = conn.execute(
        "SELECT transition_id FROM transitions WHERE scan_id = ? AND source_screen_id = ?"
        " AND target_screen_id = ? AND IFNULL(action_id, '') = IFNULL(?, '')",
        (scan_id, source_screen_id, target_screen_id, action_id),
    ).fetchone()
    if existing:
        return existing["transition_id"]

    transition_id = _next_sequence(
        conn, "transitions", "transition_id", scan_id, TRANSITION_ID_TEMPLATE
    )
    conn.execute(
        """
        INSERT INTO transitions (
            transition_id, scan_id, source_screen_id, target_screen_id, action_id,
            action_type, element_id, success, metadata_json, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            transition_id,
            scan_id,
            source_screen_id,
            target_screen_id,
            action_id,
            action_type,
            element_id,
            None if success is None else int(bool(success)),
            _json(dict(metadata) if metadata else None),
            _now(),
        ),
    )
    return transition_id


def list_transitions(conn: sqlite3.Connection, scan_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM transitions WHERE scan_id = ? ORDER BY transition_id", (scan_id,)
    ).fetchall()
    return [dict(row) for row in rows]


# --------------------------------------------------------------------------
# journeys
# --------------------------------------------------------------------------

def replace_journeys(
    conn: sqlite3.Connection, *, scan_id: str, journeys: Iterable[Mapping[str, Any]]
) -> list[dict[str, Any]]:
    """Journeys are derived data, so we recompute and replace them wholesale."""
    conn.execute("DELETE FROM journeys WHERE scan_id = ?", (scan_id,))
    stored: list[dict[str, Any]] = []
    for index, journey in enumerate(journeys, start=1):
        journey_id = JOURNEY_ID_TEMPLATE.format(index)
        conn.execute(
            """
            INSERT INTO journeys (
                journey_id, scan_id, name, start_screen_id, end_screen_id,
                screen_ids_json, action_ids_json, transition_ids_json,
                length, kind, metadata_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                journey_id,
                scan_id,
                journey["name"],
                journey["start_screen_id"],
                journey["end_screen_id"],
                _json(journey.get("screen_ids", [])),
                _json(journey.get("action_ids", [])),
                _json(journey.get("transition_ids", [])),
                int(journey.get("length", 0)),
                journey.get("kind", "shortest_path"),
                _json(journey.get("metadata")),
                _now(),
            ),
        )
        stored.append({**dict(journey), "journey_id": journey_id})
    return stored


def list_journeys(conn: sqlite3.Connection, scan_id: str) -> list[dict[str, Any]]:
    rows = conn.execute(
        "SELECT * FROM journeys WHERE scan_id = ? ORDER BY journey_id", (scan_id,)
    ).fetchall()
    journeys: list[dict[str, Any]] = []
    for row in rows:
        journeys.append(
            {
                "journey_id": row["journey_id"],
                "name": row["name"],
                "start_screen_id": row["start_screen_id"],
                "end_screen_id": row["end_screen_id"],
                "screen_ids": _loads(row["screen_ids_json"], []),
                "action_ids": _loads(row["action_ids_json"], []),
                "transition_ids": _loads(row["transition_ids_json"], []),
                "length": row["length"],
                "kind": row["kind"],
                "metadata": _loads(row["metadata_json"], None),
            }
        )
    return journeys


# --------------------------------------------------------------------------
# design language
# --------------------------------------------------------------------------

def save_design_language(
    conn: sqlite3.Connection, *, scan_id: str, payload: Mapping[str, Any]
) -> None:
    conn.execute("DELETE FROM design_language WHERE scan_id = ? AND screen_id IS NULL", (scan_id,))
    conn.execute(
        "INSERT INTO design_language (scan_id, screen_id, payload_json, created_at)"
        " VALUES (?, NULL, ?, ?)",
        (scan_id, _json(dict(payload)), _now()),
    )


def get_design_language(conn: sqlite3.Connection, scan_id: str) -> dict[str, Any] | None:
    row = conn.execute(
        "SELECT payload_json FROM design_language WHERE scan_id = ? AND screen_id IS NULL"
        " ORDER BY pk DESC LIMIT 1",
        (scan_id,),
    ).fetchone()
    return _loads(row["payload_json"], None) if row else None


# --------------------------------------------------------------------------
# knowledge packs
# --------------------------------------------------------------------------

def next_pack_id(conn: sqlite3.Connection) -> str:
    row = conn.execute("SELECT COUNT(*) AS c FROM knowledge_packs").fetchone()
    index = int(row["c"]) + 1
    while conn.execute(
        "SELECT 1 FROM knowledge_packs WHERE pack_id = ?", (PACK_ID_TEMPLATE.format(index),)
    ).fetchone():
        index += 1
    return PACK_ID_TEMPLATE.format(index)


def save_pack(
    conn: sqlite3.Connection,
    *,
    pack_id: str,
    scan_id: str,
    package_name: str | None,
    schema_version: str,
    payload: Mapping[str, Any],
    file_path: str | None,
) -> None:
    conn.execute(
        "INSERT OR REPLACE INTO knowledge_packs"
        " (pack_id, scan_id, package_name, schema_version, payload_json, file_path, created_at)"
        " VALUES (?, ?, ?, ?, ?, ?, ?)",
        (pack_id, scan_id, package_name, schema_version, _json(dict(payload)), file_path, _now()),
    )


def latest_pack(conn: sqlite3.Connection, scan_id: str | None = None) -> dict[str, Any] | None:
    if scan_id:
        row = conn.execute(
            "SELECT * FROM knowledge_packs WHERE scan_id = ? ORDER BY created_at DESC, pack_id DESC"
            " LIMIT 1",
            (scan_id,),
        ).fetchone()
    else:
        row = conn.execute(
            "SELECT * FROM knowledge_packs ORDER BY created_at DESC, pack_id DESC LIMIT 1"
        ).fetchone()
    if row is None:
        return None
    return _loads(row["payload_json"], None)
