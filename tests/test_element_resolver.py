from android.element_resolver import resolve_target
from android.exceptions import ElementNotFoundError, InvalidBoundsError
from android.models import Action, Bounds, UIElement


def _button() -> UIElement:
    return UIElement(
        element_id="element_000004",
        type="android.widget.Button",
        text="Login",
        content_description="Login",
        resource_id="com.example.app:id/login",
        clickable=True,
        enabled=True,
        scrollable=False,
        focusable=True,
        focused=False,
        checked=False,
        selected=False,
        bounds=Bounds(100, 400, 500, 480),
        package="com.example.app",
    )


def test_resolve_by_element_id() -> None:
    target = resolve_target(
        Action(action_id="action_000001", action_type="tap", element_id="element_000004"),
        [_button()],
    )
    assert (target.x, target.y) == (300, 440)


def test_missing_element() -> None:
    try:
        resolve_target(
            Action(action_id="action_000001", action_type="tap", element_id="element_999999"),
            [_button()],
        )
    except ElementNotFoundError as exc:
        assert exc.code == "ELEMENT_NOT_FOUND"
        assert exc.action_id == "action_000001"
    else:
        raise AssertionError("expected ELEMENT_NOT_FOUND")


def test_bounds_fallback() -> None:
    target = resolve_target(
        Action(
            action_id="a",
            action_type="tap",
            element_id="element_missing",
            bounds=Bounds(10, 20, 30, 40),
        ),
        [_button()],
    )
    assert (target.x, target.y) == (20, 30)


def test_invalid_bounds() -> None:
    try:
        resolve_target(
            Action(action_id="a", action_type="tap", bounds=Bounds(10, 10, 10, 10)),
            [],
        )
    except InvalidBoundsError as exc:
        assert exc.code == "INVALID_BOUNDS"
    else:
        raise AssertionError("expected INVALID_BOUNDS")
