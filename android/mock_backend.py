"""In-memory Android backend so the controller is testable without an emulator."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import List, Optional

from .android_controller import AndroidController
from .config import Config
from .emulator_manager import CommandRunner, EmulatorManager
from .exceptions import LaunchFailedError, ScrollFailedError, TextInputFailedError
from .models import CommandResult, DeviceInfo

logger = logging.getLogger(__name__)

# 1x1 PNG (valid). Used as a stand-in screenshot in mock mode.
MINIMAL_PNG = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01"
    b"\x08\x06\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01"
    b"\x00\x00\x05\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)

LAUNCH_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" password="false" selected="false" bounds="[0,0][1080,1920]">
    <node index="0" text="" resource-id="" class="android.widget.LinearLayout" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" password="false" selected="false" bounds="[0,80][1080,1920]">
      <node index="0" text="Demo App" resource-id="com.example.app:id/title" class="android.widget.TextView" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" password="false" selected="false" bounds="[100,80][980,160]"/>
      <node index="1" text="Login" resource-id="com.example.app:id/login" class="android.widget.Button" package="com.example.app" content-desc="Login" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" password="false" selected="false" bounds="[100,400][500,480]"/>
    </node>
  </node>
</hierarchy>
"""

FORM_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" password="false" selected="false" bounds="[0,0][1080,1920]">
    <node index="0" text="" resource-id="" class="android.widget.LinearLayout" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="true" password="false" selected="false" bounds="[0,80][1080,1920]">
      <node index="0" text="" resource-id="com.example.app:id/email" class="android.widget.EditText" package="com.example.app" content-desc="Email" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" password="false" selected="false" bounds="[100,200][980,280]"/>
      <node index="1" text="" resource-id="com.example.app:id/password" class="android.widget.EditText" package="com.example.app" content-desc="Password" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" password="true" selected="false" bounds="[100,300][980,380]"/>
      <node index="2" text="Submit" resource-id="com.example.app:id/submit" class="android.widget.Button" package="com.example.app" content-desc="Submit" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" password="false" selected="false" bounds="[100,400][500,480]"/>
    </node>
  </node>
</hierarchy>
"""

TYPED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" password="false" selected="false" bounds="[0,0][1080,1920]">
    <node index="0" text="" resource-id="" class="android.widget.LinearLayout" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="true" password="false" selected="false" bounds="[0,80][1080,1920]">
      <node index="0" text="test@example.com" resource-id="com.example.app:id/email" class="android.widget.EditText" package="com.example.app" content-desc="Email" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="true" scrollable="false" password="false" selected="false" bounds="[100,200][980,280]"/>
      <node index="1" text="" resource-id="com.example.app:id/password" class="android.widget.EditText" package="com.example.app" content-desc="Password" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" password="true" selected="false" bounds="[100,300][980,380]"/>
      <node index="2" text="Submit" resource-id="com.example.app:id/submit" class="android.widget.Button" package="com.example.app" content-desc="Submit" checkable="false" checked="false" clickable="true" enabled="true" focusable="true" focused="false" scrollable="false" password="false" selected="false" bounds="[100,400][500,480]"/>
    </node>
  </node>
</hierarchy>
"""

SCROLLED_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="" resource-id="" class="android.widget.FrameLayout" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" password="false" selected="false" bounds="[0,0][1080,1920]">
    <node index="0" text="" resource-id="" class="android.widget.ScrollView" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="true" password="false" selected="false" bounds="[0,80][1080,1920]">
      <node index="0" text="Footer" resource-id="com.example.app:id/footer" class="android.widget.TextView" package="com.example.app" content-desc="" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" password="false" selected="false" bounds="[100,1600][980,1680]"/>
    </node>
  </node>
</hierarchy>
"""

HOME_XML = """<?xml version="1.0" encoding="UTF-8"?>
<hierarchy rotation="0">
  <node index="0" text="Launcher" resource-id="" class="com.android.launcher3.Launcher" package="com.android.launcher3" content-desc="Home" checkable="false" checked="false" clickable="false" enabled="true" focusable="false" focused="false" scrollable="false" password="false" selected="false" bounds="[0,0][1080,1920]"/>
</hierarchy>
"""


class MockRunner(CommandRunner):
    def run(self, args, *, timeout=None, check=False, binary=False):
        return CommandResult(args=list(args), returncode=0, stdout="ok", stderr="", stdout_bytes=b"ok")


class MockEmulatorManager(EmulatorManager):
    def __init__(self, config: Config) -> None:
        super().__init__(config, runner=MockRunner())
        self._serial = "emulator-mock"
        self.installed: List[str] = []
        self.running_package: Optional[str] = None
        self.cleared: List[str] = []

    def is_adb_available(self) -> bool:
        return True

    def require_adb(self) -> None:
        return None

    def get_devices(self) -> List[DeviceInfo]:
        return [DeviceInfo(serial="emulator-mock", state="device", is_emulator=True, product="sdk_gphone")]

    def resolve_serial(self, required: bool = True) -> Optional[str]:
        self._serial = "emulator-mock"
        return self._serial

    def wait_for_device(self, timeout: Optional[float] = None) -> DeviceInfo:
        return self.get_devices()[0]

    def launch_app(self, package_name: str) -> None:
        if not package_name:
            raise LaunchFailedError("package_name is required")
        self.running_package = package_name

    def force_stop_app(self, package_name: str) -> None:
        if self.running_package == package_name:
            self.running_package = None

    def clear_app_data(self, package_name: str) -> None:
        self.cleared.append(package_name)

    def current_focus(self) -> tuple[Optional[str], Optional[str]]:
        if self.running_package:
            return self.running_package, f"{self.running_package}.MainActivity"
        return "com.android.launcher3", "com.android.launcher3.Launcher"

    def adb(self, extra, *, timeout=None, check=True, binary=False, with_serial=True):
        return CommandResult(args=list(extra), returncode=0, stdout="Success", stderr="", stdout_bytes=b"Success")


class MockAndroidController(AndroidController):
    def __init__(self, config: Config) -> None:
        emulator = MockEmulatorManager(config)
        super().__init__(config, emulator=emulator)
        self.state = "launch"
        self.xml = LAUNCH_XML
        self.last_tap: Optional[tuple[int, int]] = None
        self.typed: List[str] = []
        self.package_name = config.package_name or "com.example.app"

    def tap(self, x: int, y: int) -> None:
        self.last_tap = (int(x), int(y))
        if self.state == "launch":
            self.state = "form"
            self.xml = FORM_XML
        logger.debug("mock tap %s %s -> %s", x, y, self.state)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400) -> None:
        self.scroll_down(duration_ms=duration_ms)

    def scroll_down(self, duration_ms: int = 400) -> None:
        self.state = "scrolled"
        self.xml = SCROLLED_XML

    def scroll_up(self, duration_ms: int = 400) -> None:
        self.state = "form"
        self.xml = FORM_XML

    def scroll(self, direction: str = "down", duration_ms: int = 400) -> None:
        direction = (direction or "down").lower()
        if direction in {"down", "forward"}:
            self.scroll_down(duration_ms=duration_ms)
        elif direction in {"up", "backward"}:
            self.scroll_up(duration_ms=duration_ms)
        else:
            raise ScrollFailedError(f"Unsupported scroll direction: {direction}")

    def type_text(self, text: str, *, sensitive: bool = False) -> None:
        if text is None:
            raise TextInputFailedError("No text provided for type action")
        if sensitive:
            logger.info("Typing text into password field [REDACTED]")
        self.typed.append("[REDACTED]" if sensitive else text)
        self.state = "typed"
        self.xml = TYPED_XML.replace("test@example.com", text if not sensitive else "")

    def press_back(self) -> None:
        self.state = "launch"
        self.xml = LAUNCH_XML

    def press_home(self) -> None:
        self.state = "home"
        self.xml = HOME_XML
        self.emulator.running_package = None  # type: ignore[attr-defined]

    def launch_app(self, package_name: str) -> None:
        self.emulator.launch_app(package_name)
        self.package_name = package_name
        self.state = "launch"
        self.xml = LAUNCH_XML.replace("com.example.app", package_name)

    def restart_app(self, package_name: str) -> None:
        self.launch_app(package_name)

    def capture_screenshot(self, output_path: str | Path) -> Path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(MINIMAL_PNG)
        return dest

    def dump_ui_hierarchy(self, output_path: str | Path) -> Path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_text(self.xml, encoding="utf-8")
        return dest

    def wait_for_ui_settle(self, timeout=None, poll_interval=None, fingerprint_fn=None) -> bool:
        return True

    def _window_size(self) -> tuple[int, int]:
        return 1080, 1920
