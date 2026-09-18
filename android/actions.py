"""Validate Action JSON, execute through ADB (or mock), return Observation JSON."""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

from .android_controller import AndroidController
from .apk_manager import install_apk
from .config import Config, load_config
from .element_resolver import is_sensitive_element, resolve_target
from .exceptions import (
    AndroidControllerError,
    InvalidActionError,
    UnsupportedActionError,
)
from .mock_backend import MockAndroidController
from .models import (
    SUPPORTED_ACTION_TYPES,
    Action,
    Bounds,
    ErrorInfo,
    ExecuteResult,
    Observation,
    UIElement,
)
from .observation import ObservationBuilder, persist_observation
from .ui_tree import parse_ui_hierarchy

logger = logging.getLogger(__name__)


def parse_action(raw: Union[Dict[str, Any], Action, str, Path]) -> Action:
    if isinstance(raw, Action):
        return raw
    if isinstance(raw, (str, Path)):
        path = Path(raw)
        payload = json.loads(path.read_text(encoding="utf-8"))
    elif isinstance(raw, dict):
        payload = raw
    else:
        raise InvalidActionError("Action JSON must be an object, file path, or Action")

    action_id = payload.get("action_id")
    action_type = payload.get("action_type") or payload.get("type")
    if not action_id:
        raise InvalidActionError("action_id is required")
    if not action_type:
        raise InvalidActionError("action_type is required", action_id=str(action_id))
    if action_type not in SUPPORTED_ACTION_TYPES:
        raise UnsupportedActionError(
            f"Unsupported action type: {action_type}",
            action_id=str(action_id),
        )

    bounds = None
    if payload.get("bounds") is not None:
        try:
            bounds = Bounds.from_dict(payload["bounds"])
        except ValueError as exc:
            from .exceptions import InvalidBoundsError

            raise InvalidBoundsError(str(exc), action_id=str(action_id)) from exc

    if action_type == "type" and payload.get("text") is None:
        raise InvalidActionError("type actions require a 'text' field", action_id=str(action_id))

    return Action(
        action_id=str(action_id),
        action_type=str(action_type),
        element_id=payload.get("element_id"),
        bounds=bounds,
        text=payload.get("text"),
        direction=payload.get("direction") or payload.get("scroll_direction"),
        package_name=payload.get("package_name") or payload.get("package"),
        duration_ms=int(payload.get("duration_ms", 400)),
        x=payload.get("x"),
        y=payload.get("y"),
        x2=payload.get("x2"),
        y2=payload.get("y2"),
    )


class ActionExecutor:
    """Member 1 public integration surface: Action JSON in, Observation JSON out."""

    def __init__(
        self,
        config: Optional[Config] = None,
        controller: Optional[AndroidController] = None,
        builder: Optional[ObservationBuilder] = None,
        mock: Optional[bool] = None,
    ) -> None:
        self.config = config or load_config()
        use_mock = self.config.mock if mock is None else mock
        if controller is not None:
            self.controller = controller
        elif use_mock:
            self.controller = MockAndroidController(self.config)
        else:
            self.controller = AndroidController(self.config)
        self.builder = builder or ObservationBuilder(self.config)
        self.elements: List[UIElement] = []
        self.last_observation: Optional[Observation] = None
        self.package_name = self.config.package_name

    def install(self, apk_path: str):
        res = install_apk(apk_path, config=self.config, emulator=self.controller.emulator)
        if res.success and res.package_name:
            self.package_name = res.package_name
        return res

    def observe(self, *, caused_by_action_id: Optional[str] = None) -> Observation:
        self.config.ensure_directories()
        obs_id = self.builder.next_observation_id()
        screenshot_abs = self.config.screenshot_dir / f"{obs_id}.png"
        ui_abs = self.config.ui_tree_dir / f"{obs_id}.xml"
        self.controller.capture_screenshot(screenshot_abs)
        self.controller.dump_ui_hierarchy(ui_abs)
        elements = parse_ui_hierarchy(ui_abs)
        self.elements = elements
        package, activity = self.controller.emulator.current_focus()
        if self.package_name:
            package = package or self.package_name
        observation = self.builder.build(
            elements=elements,
            screenshot_relpath=f"screenshots/{obs_id}.png",
            ui_tree_relpath=f"ui_trees/{obs_id}.xml",
            package_name=package,
            activity=activity,
            observation_id=obs_id,
            caused_by_action_id=caused_by_action_id,
        )
        persist_observation(observation, self.config)
        self.last_observation = observation
        return observation

    def reset_application(
        self,
        package_name: Optional[str] = None,
        clear_data: bool = False,
    ) -> ExecuteResult:
        package = package_name or self.package_name or self.config.package_name
        if not package:
            err = ErrorInfo(code="PACKAGE_NOT_FOUND", message="package_name is required for reset")
            return ExecuteResult(success=False, error=err)
        try:
            self.controller.force_stop_app(package)
            if clear_data:
                self.controller.clear_app_data(package)
            self.controller.launch_app(package)
            self.package_name = package
            self._settle()
            observation = self.observe()
            return ExecuteResult(success=True, observation=observation)
        except AndroidControllerError as exc:
            logger.error("reset_application failed: %s", exc.message)
            return ExecuteResult(
                success=False,
                error=ErrorInfo(
                    code=exc.code,
                    message=exc.message,
                    details=exc.details,
                ),
            )

    def launch(self, package_name: Optional[str] = None) -> ExecuteResult:
        package = package_name or self.package_name or self.config.package_name
        if not package:
            return ExecuteResult(
                success=False,
                error=ErrorInfo(code="PACKAGE_NOT_FOUND", message="package_name is required"),
            )
        try:
            self.controller.launch_app(package)
            self.package_name = package
            self._settle()
            return ExecuteResult(success=True, observation=self.observe())
        except AndroidControllerError as exc:
            logger.error("launch failed: %s", exc.message)
            return ExecuteResult(
                success=False,
                error=ErrorInfo(code=exc.code, message=exc.message, details=exc.details),
            )

    def execute(self, raw_action: Union[Dict[str, Any], Action, str, Path]) -> ExecuteResult:
        action: Optional[Action] = None
        try:
            action = parse_action(raw_action)
            self._perform(action)
            self._settle()
            observation = self.observe(caused_by_action_id=action.action_id)
            return ExecuteResult(success=True, observation=observation, action=action)
        except AndroidControllerError as exc:
            logger.error(
                "Action failed (%s): %s",
                exc.code,
                exc.message,
            )
            return ExecuteResult(
                success=False,
                action=action,
                error=ErrorInfo(
                    code=exc.code,
                    message=exc.message,
                    action_id=exc.action_id or (action.action_id if action else None),
                    details=exc.details,
                ),
            )
        except Exception as exc:
            logger.exception("Unexpected action failure")
            return ExecuteResult(
                success=False,
                action=action,
                error=ErrorInfo(
                    code="SUBPROCESS_ERROR",
                    message=str(exc),
                    action_id=action.action_id if action else None,
                ),
            )

    def _perform(self, action: Action) -> None:
        kind = action.action_type
        if kind == "tap":
            target = resolve_target(action, self.elements)
            self.controller.tap(target.x, target.y)
        elif kind == "type":
            target = resolve_target(action, self.elements)
            self.controller.tap(target.x, target.y)
            sensitive = is_sensitive_element(target.element)
            if not sensitive and action.text:
                # Heuristic: password-like payload still redacted in logs by controller flag
                sensitive = "password" in (target.element.resource_id or "").lower() if target.element else False
            self.controller.type_text(action.text or "", sensitive=sensitive)
        elif kind == "scroll":
            self.controller.scroll(action.direction or "down", duration_ms=action.duration_ms)
        elif kind == "swipe":
            if None in (action.x, action.y, action.x2, action.y2):
                target = resolve_target(action, self.elements)
                self.controller.scroll("down", duration_ms=action.duration_ms)
                return
            self.controller.swipe(action.x, action.y, action.x2, action.y2, action.duration_ms)  # type: ignore[arg-type]
        elif kind == "back":
            self.controller.press_back()
        elif kind == "home":
            self.controller.press_home()
        elif kind == "launch":
            package = action.package_name or self.package_name
            if not package:
                raise InvalidActionError("launch requires package_name", action_id=action.action_id)
            self.controller.launch_app(package)
            self.package_name = package
        elif kind == "restart":
            package = action.package_name or self.package_name
            if not package:
                raise InvalidActionError("restart requires package_name", action_id=action.action_id)
            self.controller.restart_app(package)
            self.package_name = package
        else:
            raise UnsupportedActionError(f"Unsupported action type: {kind}", action_id=action.action_id)

    def _settle(self) -> None:
        def fingerprint():
            try:
                tmp = self.config.ui_tree_dir / "_settle.xml"
                path = self.controller.dump_ui_hierarchy(tmp)
                return path.read_text(encoding="utf-8")
            except Exception:
                return None

        self.controller.wait_for_ui_settle(fingerprint_fn=fingerprint)
