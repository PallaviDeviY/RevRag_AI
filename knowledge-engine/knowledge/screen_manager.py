"""Screen identity: fingerprint -> deduplicate -> stable screen id.

The controller may send a ``screen_id``. We treat it as *advisory metadata*
only (rule 4/5 in the brief): identity is decided by the fingerprint, and the
reported id is stored on the observation row for traceability.
"""

from __future__ import annotations

import logging
import sqlite3
from typing import Any, Mapping

from . import repositories as repo
from .fingerprint import compute_fingerprint, compute_structural_fingerprint

logger = logging.getLogger(__name__)


class ScreenManager:
    """Resolves an observation to a stable screen row inside one scan."""

    def __init__(self, scan_id: str) -> None:
        self.scan_id = scan_id

    def process_observation(
        self, conn: sqlite3.Connection, observation: Mapping[str, Any]
    ) -> tuple[dict[str, Any], bool, list[str]]:
        """Ingest one observation.

        Must be called inside a write transaction.

        Returns ``(screen_dict, created, warnings)`` where ``created`` is True
        when this observation produced a brand-new screen.
        """
        warnings: list[str] = []
        elements = [dict(el) for el in (observation.get("elements") or [])]
        package_name = observation.get("package_name")
        activity = observation.get("activity")

        if not elements:
            warnings.append(
                "Observation contains no elements; the fingerprint is based on "
                "package/activity alone and may over-merge screens."
            )

        fingerprint = compute_fingerprint(
            package_name=package_name, activity=activity, elements=elements
        )
        structural = compute_structural_fingerprint(
            package_name=package_name, activity=activity, elements=elements
        )

        repo.ensure_scan(conn, self.scan_id, package_name)
        existing = repo.find_screen_by_fingerprint(conn, self.scan_id, fingerprint)

        if existing is not None:
            screen_id = existing["screen_id"]
            created = False
            repo.increment_observation_count(conn, self.scan_id, screen_id)
            reported = observation.get("screen_id")
            if reported and reported != screen_id:
                warnings.append(
                    f"Controller reported screen_id '{reported}' but this UI fingerprint "
                    f"already maps to '{screen_id}'. Using '{screen_id}'."
                )
        else:
            screen_id = repo.next_screen_id(conn, self.scan_id)
            created = True
            repo.insert_screen(
                conn,
                scan_id=self.scan_id,
                screen_id=screen_id,
                fingerprint=fingerprint,
                structural_fingerprint=structural,
                package_name=package_name,
                activity=activity,
                screenshot_path=observation.get("screenshot_path"),
                ui_tree_path=observation.get("ui_tree_path"),
                first_seen_observation_id=observation.get("observation_id"),
                element_count=len(elements),
                metadata={"reported_screen_id": observation.get("screen_id")},
            )

        repo.upsert_elements(
            conn, scan_id=self.scan_id, screen_id=screen_id, elements=elements
        )
        repo.insert_observation(
            conn, scan_id=self.scan_id, observation=observation, resolved_screen_id=screen_id
        )

        screen = repo.screen_with_elements(conn, self.scan_id, screen_id) or {}
        logger.debug(
            "Observation %s -> screen %s (created=%s)",
            observation.get("observation_id"),
            screen_id,
            created,
        )
        return screen, created, warnings


def screen_label(screen: Mapping[str, Any]) -> str:
    """Human-readable node label for the dashboard.

    Preference order: last segment of the activity name -> first visible text
    on a non-clickable element -> the screen id itself.
    """
    activity = screen.get("activity")
    if activity:
        return str(activity).rsplit(".", 1)[-1]
    for element in screen.get("elements") or []:
        text = (element.get("text") or "").strip()
        if text:
            return text[:40]
    return str(screen.get("screen_id", "unknown"))
