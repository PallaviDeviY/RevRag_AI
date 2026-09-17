from android.models import Bounds, UIElement
from android.observation import ObservationBuilder, persist_observation


def _el() -> UIElement:
    return UIElement(
        element_id="element_000001",
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


def test_observation_fields(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("DATA_DIR", str(tmp_path))
    monkeypatch.setenv("OBSERVATION_DIR", str(tmp_path / "observations"))
    from android.config import load_config

    config = load_config()
    builder = ObservationBuilder(config)
    obs = builder.build(
        elements=[_el()],
        screenshot_relpath="screenshots/obs_000001.png",
        ui_tree_relpath="ui_trees/obs_000001.xml",
        package_name="com.example.app",
        activity="com.example.app.MainActivity",
        timestamp="2026-09-17T21:30:00+05:30",
    )
    payload = obs.to_dict()
    assert payload["observation_id"] == "obs_000001"
    assert payload["screen_id"] == "screen_000001"
    assert payload["timestamp"] == "2026-09-17T21:30:00+05:30"
    assert payload["screenshot_path"] == "screenshots/obs_000001.png"
    assert payload["ui_tree_path"] == "ui_trees/obs_000001.xml"
    assert payload["elements"][0]["text"] == "Login"
    assert "C:" not in payload["screenshot_path"]
    dest = persist_observation(obs, config)
    assert dest.name == "obs_000001.json"


def test_same_ui_reuses_screen_id() -> None:
    builder = ObservationBuilder()
    first = builder.build(
        elements=[_el()],
        screenshot_relpath="screenshots/obs_000001.png",
        ui_tree_relpath="ui_trees/obs_000001.xml",
    )
    second = builder.build(
        elements=[_el()],
        screenshot_relpath="screenshots/obs_000002.png",
        ui_tree_relpath="ui_trees/obs_000002.xml",
    )
    assert first.screen_id == second.screen_id
    assert first.observation_id != second.observation_id


def test_strips_absolute_windows_path() -> None:
    builder = ObservationBuilder()
    obs = builder.build(
        elements=[_el()],
        screenshot_relpath=r"C:\Users\Pallavi\Desktop\data\screenshots\obs_000001.png",
        ui_tree_relpath=r"C:\Users\Pallavi\Desktop\data\ui_trees\obs_000001.xml",
    )
    assert obs.screenshot_path == "screenshots/obs_000001.png"
    assert obs.ui_tree_path == "ui_trees/obs_000001.xml"
