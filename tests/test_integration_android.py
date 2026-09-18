import pytest

from android.actions import ActionExecutor
from android.config import load_config
from android.emulator_manager import EmulatorManager


@pytest.mark.android
def test_real_emulator_observe_if_present() -> None:
    config = load_config()
    emulator = EmulatorManager(config)
    if not emulator.is_adb_available():
        pytest.skip("ADB is not available")
    devices = emulator.get_online_devices()
    if not devices:
        pytest.skip("No Android emulator/device is connected")
    executor = ActionExecutor(config=config, mock=False)
    observation = executor.observe()
    assert observation.observation_id.startswith("obs_")
    assert observation.screenshot_path.startswith("screenshots/")
    assert observation.ui_tree_path.startswith("ui_trees/")
