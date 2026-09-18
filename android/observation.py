"""Build Observation JSON from screenshots + parsed UI trees."""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional, Sequence
from zoneinfo import ZoneInfo

from .config import Config, load_config
from .models import Observation, UIElement
from .ui_tree import make_screen_id, parse_ui_hierarchy

logger = logging.getLogger(__name__)


def _now_iso() -> str:
    try:
        tz = ZoneInfo("Asia/Kolkata")
        return datetime.now(tz).replace(microsecond=0).isoformat()
    except Exception:
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class ObservationBuilder:
    def __init__(self, config: Optional[Config] = None, start_index: int = 1) -> None:
        self.config = config or load_config()
        self._index = start_index
        self._screen_keys: dict[str, str] = {}
        self._next_screen = 1

    def next_observation_id(self) -> str:
        obs_id = f"obs_{self._index:06d}"
        self._index += 1
        return obs_id

    def peek_id(self) -> str:
        return f"obs_{self._index:06d}"

    def build(
        self,
        *,
        elements: Sequence[UIElement],
        screenshot_relpath: str,
        ui_tree_relpath: str,
        package_name: Optional[str] = None,
        activity: Optional[str] = None,
        observation_id: Optional[str] = None,
        timestamp: Optional[str] = None,
        caused_by_action_id: Optional[str] = None,
    ) -> Observation:
        obs_id = observation_id or self.next_observation_id()
        fingerprint = make_screen_id(elements)
        screen_id = self._screen_keys.get(fingerprint)
        if screen_id is None:
            screen_id = f"screen_{self._next_screen:06d}"
            self._screen_keys[fingerprint] = screen_id
            self._next_screen += 1
        return Observation(
            observation_id=obs_id,
            screen_id=screen_id,
            timestamp=timestamp or _now_iso(),
            package_name=package_name,
            activity=activity,
            screenshot_path=_to_relative(screenshot_relpath),
            ui_tree_path=_to_relative(ui_tree_relpath),
            elements=list(elements),
            caused_by_action_id=caused_by_action_id,
        )

    def from_xml_file(
        self,
        xml_path: Path,
        *,
        screenshot_relpath: str,
        ui_tree_relpath: str,
        package_name: Optional[str] = None,
        activity: Optional[str] = None,
    ) -> Observation:
        elements = parse_ui_hierarchy(xml_path)
        return self.build(
            elements=elements,
            screenshot_relpath=screenshot_relpath,
            ui_tree_relpath=ui_tree_relpath,
            package_name=package_name,
            activity=activity,
        )


def persist_observation(observation: Observation, config: Optional[Config] = None) -> Path:
    """Write Observation JSON under data/observations/{observation_id}.json."""
    config = config or load_config()
    config.ensure_directories()
    dest = config.observation_dir / f"{observation.observation_id}.json"
    dest.write_text(json.dumps(observation.to_dict(), indent=2) + "\n", encoding="utf-8")
    return dest


def _to_relative(path: str) -> str:
    normalized = path.replace("\\", "/")
    if ":" in normalized[:3]:
        logger.warning("Refusing absolute screenshot/ui path in Observation JSON: %s", normalized)
        # Keep only the last two components: screenshots/obs_x.png
        parts = normalized.replace("\\", "/").split("/")
        if len(parts) >= 2:
            return "/".join(parts[-2:])
    if normalized.startswith("data/"):
        return normalized[len("data/") :]
    return normalized.lstrip("./")
