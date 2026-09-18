"""Typed models for Action JSON, Observation JSON, and related results.

ID strategy (stable; do not change without a team contract update):

* ``action_id`` — supplied by the caller (AI agent). Format is not rewritten.
* ``observation_id`` — sequential per controller session: ``obs_000001``.
* ``screen_id`` — ``screen_000001`` assigned the first time a UI fingerprint is
  seen in a session; the same fingerprint reuses the same id.
* ``element_id`` — DFS order in that UI dump: ``element_000001``. Stable for the
  same hierarchy because dump order and node properties are deterministic.
  A fingerprint of path/class/resource-id/bounds/text is also computed internally.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any, Dict, List, Optional


SUPPORTED_ACTION_TYPES = (
    "tap",
    "type",
    "scroll",
    "swipe",
    "back",
    "home",
    "launch",
    "restart",
)


@dataclass
class Bounds:
    left: int
    top: int
    right: int
    bottom: int

    def is_valid(self) -> bool:
        return self.right > self.left and self.bottom > self.top

    def center(self) -> tuple[int, int]:
        if not self.is_valid():
            raise ValueError("Bounds are invalid")
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2

    def to_dict(self) -> Dict[str, int]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: Any) -> "Bounds":
        if not isinstance(raw, dict):
            raise ValueError("bounds must be an object")
        try:
            return cls(
                left=int(raw["left"]),
                top=int(raw["top"]),
                right=int(raw["right"]),
                bottom=int(raw["bottom"]),
            )
        except (KeyError, TypeError, ValueError) as exc:
            raise ValueError("bounds must include integer left/top/right/bottom") from exc


@dataclass
class UIElement:
    element_id: str
    type: str
    text: Optional[str]
    content_description: Optional[str]
    resource_id: Optional[str]
    clickable: bool
    enabled: bool
    scrollable: bool
    focusable: bool
    focused: bool
    checked: bool
    selected: bool
    bounds: Optional[Bounds]
    package: Optional[str]
    password: bool = False
    index_path: str = ""

    def to_dict(self) -> Dict[str, Any]:
        payload = {
            "element_id": self.element_id,
            "type": self.type,
            "text": self.text,
            "content_description": self.content_description,
            "resource_id": self.resource_id,
            "clickable": self.clickable,
            "enabled": self.enabled,
            "scrollable": self.scrollable,
            "focusable": self.focusable,
            "focused": self.focused,
            "checked": self.checked,
            "selected": self.selected,
            "bounds": self.bounds.to_dict() if self.bounds else None,
            "package": self.package,
        }
        return payload


@dataclass
class Observation:
    observation_id: str
    screen_id: str
    timestamp: str
    package_name: Optional[str]
    activity: Optional[str]
    screenshot_path: str
    ui_tree_path: str
    elements: List[UIElement] = field(default_factory=list)
    caused_by_action_id: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "observation_id": self.observation_id,
            "screen_id": self.screen_id,
            "timestamp": self.timestamp,
            "package_name": self.package_name,
            "activity": self.activity,
            "screenshot_path": self.screenshot_path,
            "ui_tree_path": self.ui_tree_path,
            "elements": [el.to_dict() for el in self.elements],
        }
        if self.caused_by_action_id:
            payload["caused_by_action_id"] = self.caused_by_action_id
        return payload


@dataclass
class Action:
    action_id: str
    action_type: str
    element_id: Optional[str] = None
    bounds: Optional[Bounds] = None
    text: Optional[str] = None
    direction: Optional[str] = None
    package_name: Optional[str] = None
    duration_ms: int = 400
    x: Optional[int] = None
    y: Optional[int] = None
    x2: Optional[int] = None
    y2: Optional[int] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "action_id": self.action_id,
            "action_type": self.action_type,
        }
        if self.element_id is not None:
            payload["element_id"] = self.element_id
        if self.bounds is not None:
            payload["bounds"] = self.bounds.to_dict()
        if self.text is not None:
            payload["text"] = self.text
        if self.direction is not None:
            payload["direction"] = self.direction
        if self.package_name is not None:
            payload["package_name"] = self.package_name
        if self.duration_ms != 400:
            payload["duration_ms"] = self.duration_ms
        return payload


@dataclass
class ErrorInfo:
    code: str
    message: str
    action_id: Optional[str] = None
    details: Optional[Dict[str, Any]] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"code": self.code, "message": self.message}
        if self.action_id:
            payload["action_id"] = self.action_id
        if self.details:
            payload["details"] = self.details
        return payload


@dataclass
class ExecuteResult:
    success: bool
    observation: Optional[Observation] = None
    error: Optional[ErrorInfo] = None
    action: Optional[Action] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {"success": self.success}
        if self.observation is not None:
            payload["observation"] = self.observation.to_dict()
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        if self.action is not None:
            payload["action"] = self.action.to_dict()
        return payload


@dataclass
class InstallResult:
    success: bool
    apk_path: str
    package_name: Optional[str] = None
    message: str = ""
    error: Optional[ErrorInfo] = None

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "success": self.success,
            "apk_path": self.apk_path,
            "package_name": self.package_name,
            "message": self.message,
        }
        if self.error is not None:
            payload["error"] = self.error.to_dict()
        return payload


@dataclass
class DeviceInfo:
    serial: str
    state: str
    is_emulator: bool
    product: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class CommandResult:
    args: List[str]
    returncode: int
    stdout: str
    stderr: str
    stdout_bytes: bytes = b""

    @property
    def ok(self) -> bool:
        return self.returncode == 0
