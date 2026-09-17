"""Knowledge Pack generation - the artifact Suma (Member 4) consumes.

Compatibility
-------------
The approved shared schema (``schemas/knowledge_pack.schema.json``) is an
explicit placeholder with only ``pack_id`` and ``source_observation_ids``.
Both are preserved exactly. Every other field is a PROVISIONAL Member 3
extension, described in ``schemas/knowledge_pack.v0_2.schema.json``, and must
be approved by the team before anyone treats it as stable.

Determinism
-----------
Every list is sorted by a stable key and ``generated_at`` is the only field
that changes between two runs over identical data. ``build_pack`` therefore
produces byte-identical JSON when ``generated_at`` is pinned - which is what
``test_knowledge_pack.py`` asserts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping, Sequence

from . import repositories as repo
from .config import SCHEMA_VERSION, get_settings
from .design_analyzer import analyze_screens
from .graph_builder import build_graph, skipped_transitions
from .journey_builder import discover_journeys, element_text_index

logger = logging.getLogger(__name__)


def _screen_payload(screen: Mapping[str, Any], include_elements: bool) -> dict[str, Any]:
    payload = {
        "screen_id": screen["screen_id"],
        "package_name": screen.get("package_name"),
        "activity": screen.get("activity"),
        "screenshot_path": screen.get("screenshot_path"),
        "ui_tree_path": screen.get("ui_tree_path"),
        "fingerprint": screen.get("fingerprint"),
        "structural_fingerprint": screen.get("structural_fingerprint"),
        "first_seen_observation_id": screen.get("first_seen_observation_id"),
        "observation_count": int(screen.get("observation_count") or 0),
        "element_count": int(screen.get("element_count") or 0),
    }
    if include_elements:
        payload["elements"] = screen.get("elements") or []
    return payload


def _action_payload(action: Mapping[str, Any]) -> dict[str, Any]:
    bounds = None
    if action.get("bounds_left") is not None:
        bounds = {
            "left": action["bounds_left"],
            "top": action["bounds_top"],
            "right": action["bounds_right"],
            "bottom": action["bounds_bottom"],
        }
    return {
        "action_id": action["action_id"],
        "action_type": action["action_type"],
        "element_id": action.get("element_id"),
        "source_screen_id": action.get("source_screen_id"),
        "target_screen_id": action.get("target_screen_id"),
        "bounds": bounds,
        "result": action.get("result"),
        "success": None if action.get("success") is None else bool(action["success"]),
    }


def _transition_payload(transition: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "transition_id": transition["transition_id"],
        "source_screen_id": transition["source_screen_id"],
        "target_screen_id": transition["target_screen_id"],
        "action_id": transition.get("action_id"),
        "action_type": transition.get("action_type"),
        "element_id": transition.get("element_id"),
        "success": None if transition.get("success") is None else bool(transition["success"]),
    }


def build_pack(
    conn: sqlite3.Connection,
    *,
    scan_id: str,
    pack_id: str,
    package_name: str | None = None,
    include_elements: bool = True,
    generated_at: str | None = None,
    media_root: str | Path = ".",
    run_design_analysis: bool = True,
) -> dict[str, Any]:
    """Assemble the pack from persisted state. Read-only; does not write."""
    warnings: list[str] = []

    screen_rows = repo.list_screens(conn, scan_id, package_name)
    screens = []
    for row in screen_rows:
        screen = dict(row)
        screen["elements"] = repo.list_elements(conn, scan_id, screen["screen_id"])
        screens.append(screen)

    transitions = repo.list_transitions(conn, scan_id)
    actions = repo.list_actions(conn, scan_id)
    observation_ids = repo.list_observation_ids(conn, scan_id)

    graph = build_graph(screens, transitions)
    warnings.extend(skipped_transitions(screens, transitions))

    settings = get_settings()
    journeys = discover_journeys(
        graph,
        element_text_by_id=element_text_index(screens),
        max_length=settings.max_journey_length,
        max_journeys=settings.max_journeys,
    )
    journeys = [
        {**journey, "journey_id": f"journey_{i:06d}"} for i, journey in enumerate(journeys, start=1)
    ]

    if run_design_analysis:
        design_language = analyze_screens(screens, media_root=media_root)
    else:
        design_language = {
            "screenshot_count": 0,
            "analyzed_count": 0,
            "confidence": 0.0,
            "analysis_warnings": ["Design analysis was disabled for this run."],
        }
    warnings.extend(design_language.get("analysis_warnings", []))

    # Elements are emitted once, flattened, keyed by their screen.
    flat_elements: list[dict[str, Any]] = []
    for screen in screens:
        for element in screen["elements"]:
            flat_elements.append({**element, "screen_id": screen["screen_id"]})
    flat_elements.sort(
        key=lambda e: (e["screen_id"], e.get("element_id") or "", e.get("type") or "")
    )

    activities = sorted({s["activity"] for s in screens if s.get("activity")})
    packages = sorted({s["package_name"] for s in screens if s.get("package_name")})
    if len(packages) > 1:
        warnings.append(f"Multiple packages present in this scan: {packages}")
    if not screens:
        warnings.append("No screens have been ingested for this scan.")

    pack: dict[str, Any] = {
        # --- approved shared contract ---
        "pack_id": pack_id,
        "source_observation_ids": sorted(observation_ids),
        # --- provisional Member 3 extension ---
        "schema_version": SCHEMA_VERSION,
        "generated_at": generated_at or datetime.now(timezone.utc).isoformat(),
        "scan_id": scan_id,
        "app": {
            "package_name": package_name or (packages[0] if packages else None),
            "packages": packages,
            "activity_count": len(activities),
            "activities": activities,
        },
        "screens": [_screen_payload(s, include_elements) for s in screens],
        "elements": flat_elements,
        "actions": [_action_payload(a) for a in actions],
        "transitions": [_transition_payload(t) for t in transitions],
        "journeys": journeys,
        "design_language": design_language,
        "statistics": {
            "screen_count": len(screens),
            "element_count": len(flat_elements),
            "action_count": len(actions),
            "transition_count": len(transitions),
            "journey_count": len(journeys),
            "observation_count": len(observation_ids),
            "isolated_screen_count": len(
                [n for n in graph.nodes if graph.degree(n) == 0]
            ),
        },
        "warnings": sorted(set(warnings)),
    }
    validate_pack(pack)
    return pack


def validate_pack(pack: Mapping[str, Any]) -> None:
    """Fail loudly if the two approved contract fields were broken."""
    if not isinstance(pack.get("pack_id"), str) or not pack["pack_id"]:
        raise ValueError("Knowledge Pack must carry a non-empty string pack_id")
    ids = pack.get("source_observation_ids")
    if not isinstance(ids, list) or any(not isinstance(i, str) for i in ids):
        raise ValueError("source_observation_ids must be an array of strings")
    screen_ids = [s["screen_id"] for s in pack.get("screens", [])]
    if len(screen_ids) != len(set(screen_ids)):
        raise ValueError("Knowledge Pack contains duplicate screens")


def write_pack(pack: Mapping[str, Any], output_dir: str | Path | None = None) -> Path:
    """Write the pack as pretty JSON and return the file path."""
    settings = get_settings()
    directory = Path(output_dir) if output_dir else settings.pack_output_dir
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / f"{pack['pack_id']}.json"
    path.write_text(json.dumps(pack, indent=2, sort_keys=False, ensure_ascii=False), "utf-8")
    logger.info("Knowledge Pack written to %s", path)
    return path


def generate_and_store(
    conn: sqlite3.Connection,
    *,
    scan_id: str,
    package_name: str | None = None,
    save_to_disk: bool = True,
    include_elements: bool = True,
    media_root: str | Path = ".",
) -> dict[str, Any]:
    """Build, persist derived journeys, save, and return the pack.

    Must be called inside a write transaction.
    """
    pack_id = repo.next_pack_id(conn)
    pack = build_pack(
        conn,
        scan_id=scan_id,
        pack_id=pack_id,
        package_name=package_name,
        include_elements=include_elements,
        media_root=media_root,
    )
    repo.replace_journeys(conn, scan_id=scan_id, journeys=pack["journeys"])
    repo.save_design_language(conn, scan_id=scan_id, payload=pack["design_language"])
    file_path = str(write_pack(pack)) if save_to_disk else None
    repo.save_pack(
        conn,
        pack_id=pack_id,
        scan_id=scan_id,
        package_name=pack["app"]["package_name"],
        schema_version=pack["schema_version"],
        payload=pack,
        file_path=file_path,
    )
    return pack


def sequence_key(value: Sequence[Any]) -> tuple:  # pragma: no cover - helper
    return tuple(value)
