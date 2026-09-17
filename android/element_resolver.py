"""Resolve Action JSON targets: element_id first, then bounds."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional, Sequence

from .exceptions import ElementNotFoundError, InvalidBoundsError
from .models import Action, Bounds, UIElement


@dataclass
class ResolvedTarget:
    element: Optional[UIElement]
    bounds: Bounds
    x: int
    y: int


def resolve_target(
    action: Action,
    elements: Sequence[UIElement],
    *,
    action_id: Optional[str] = None,
) -> ResolvedTarget:
    aid = action_id or action.action_id
    if action.element_id:
        for element in elements:
            if element.element_id == action.element_id:
                bounds = element.bounds
                if bounds is None or not bounds.is_valid():
                    if action.bounds and action.bounds.is_valid():
                        bounds = action.bounds
                    else:
                        raise InvalidBoundsError(
                            f"Element '{action.element_id}' has no usable bounds",
                            action_id=aid,
                        )
                x, y = bounds.center()
                return ResolvedTarget(element=element, bounds=bounds, x=x, y=y)
        if action.bounds and action.bounds.is_valid():
            x, y = action.bounds.center()
            return ResolvedTarget(element=None, bounds=action.bounds, x=x, y=y)
        raise ElementNotFoundError(
            f"Target element could not be resolved: {action.element_id}",
            action_id=aid,
        )

    if action.bounds is not None:
        if not action.bounds.is_valid():
            raise InvalidBoundsError("Invalid bounds supplied on action", action_id=aid)
        x, y = action.bounds.center()
        return ResolvedTarget(element=None, bounds=action.bounds, x=x, y=y)

    if action.x is not None and action.y is not None:
        bounds = Bounds(action.x, action.y, action.x + 1, action.y + 1)
        return ResolvedTarget(element=None, bounds=bounds, x=int(action.x), y=int(action.y))

    raise ElementNotFoundError(
        "Target element could not be resolved",
        action_id=aid,
    )


def is_sensitive_element(element: Optional[UIElement]) -> bool:
    if element is None:
        return False
    if element.password:
        return True
    blob = " ".join(
        [
            element.resource_id or "",
            element.content_description or "",
            element.type or "",
            element.text or "",
        ]
    ).lower()
    return "password" in blob or "passwd" in blob or "pin" == (element.text or "").lower()
