from pathlib import Path

from android.actions import ActionExecutor, parse_action
from android.exceptions import InvalidActionError, UnsupportedActionError
from android.models import Action


def test_valid_tap() -> None:
    action = parse_action(
        {
            "action_id": "action_000001",
            "action_type": "tap",
            "element_id": "element_000004",
            "bounds": {"left": 100, "top": 400, "right": 500, "bottom": 480},
        }
    )
    assert action.action_type == "tap"
    assert action.bounds is not None
    assert action.bounds.center() == (300, 440)


def test_valid_type() -> None:
    action = parse_action(
        {
            "action_id": "action_000002",
            "action_type": "type",
            "element_id": "element_000003",
            "text": "test@example.com",
        }
    )
    assert action.text == "test@example.com"


def test_valid_scroll() -> None:
    action = parse_action({"action_id": "action_000003", "action_type": "scroll", "direction": "down"})
    assert action.direction == "down"


def test_unsupported_action() -> None:
    try:
        parse_action({"action_id": "action_x", "action_type": "explode"})
    except UnsupportedActionError as exc:
        assert exc.code == "UNSUPPORTED_ACTION"
    else:
        raise AssertionError("expected UNSUPPORTED_ACTION")


def test_type_requires_text() -> None:
    try:
        parse_action({"action_id": "action_x", "action_type": "type", "element_id": "element_000001"})
    except InvalidActionError:
        return
    raise AssertionError("expected InvalidActionError")


def test_parse_action_from_sample_file() -> None:
    path = Path("data/sample/action_tap.json")
    action = parse_action(path)
    assert isinstance(action, Action)
    assert action.element_id == "element_000004"


def test_mock_multistep_sequence(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("SCREENSHOT_DIR", str(tmp_path / "screenshots"))
    monkeypatch.setenv("UI_TREE_DIR", str(tmp_path / "ui_trees"))
    monkeypatch.setenv("OBSERVATION_DIR", str(tmp_path / "observations"))
    monkeypatch.setenv("ANDROID_MOCK", "1")

    from android.config import load_config

    executor = ActionExecutor(config=load_config(), mock=True)
    launched = executor.launch("com.example.app")
    assert launched.success
    obs = launched.observation
    assert obs is not None
    assert obs.observation_id == "obs_000001"
    assert not obs.screenshot_path.startswith("C:")
    assert obs.screenshot_path == "screenshots/obs_000001.png"
    login = next(el for el in obs.elements if el.text == "Login")
    assert login.element_id == "element_000004"

    tap = executor.execute(
        {
            "action_id": "action_000001",
            "action_type": "tap",
            "element_id": "element_000004",
            "bounds": {"left": 100, "top": 400, "right": 500, "bottom": 480},
        }
    )
    assert tap.success
    assert tap.observation.observation_id == "obs_000002"
    assert tap.observation.observation_id != obs.observation_id
    email = next(el for el in tap.observation.elements if el.resource_id and el.resource_id.endswith("/email"))
    typed = executor.execute(
        {
            "action_id": "action_000002",
            "action_type": "type",
            "element_id": email.element_id,
            "text": "test@example.com",
        }
    )
    assert typed.success
    assert typed.observation.observation_id == "obs_000003"
    filled = next(el for el in typed.observation.elements if el.resource_id and el.resource_id.endswith("/email"))
    assert filled.text == "test@example.com"

    scrolled = executor.execute({"action_id": "action_000003", "action_type": "scroll", "direction": "down"})
    assert scrolled.success
    assert scrolled.observation.observation_id == "obs_000004"
    assert any(el.text == "Footer" for el in scrolled.observation.elements)

    back = executor.execute({"action_id": "action_000004", "action_type": "back"})
    assert back.success
    assert back.observation.observation_id == "obs_000005"
    assert any(el.text == "Login" for el in back.observation.elements)

    # artifacts written under data dirs
    assert (tmp_path / "observations" / "obs_000001.json").is_file()
    assert (tmp_path / "screenshots" / "obs_000002.png").is_file()
    assert (tmp_path / "ui_trees" / "obs_000004.xml").is_file()
