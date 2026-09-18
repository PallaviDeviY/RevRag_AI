"""Low-level ADB input, navigation, screenshots, and UI dump helpers."""

from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import Optional

from .config import Config, load_config
from .emulator_manager import CommandRunner, EmulatorManager
from .exceptions import (
    ScreenshotFailedError,
    ScrollFailedError,
    SubprocessFailedError,
    TextInputFailedError,
    UiDumpFailedError,
)
from .models import CommandResult

logger = logging.getLogger(__name__)

_SAFE_TEXT_CHARS = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._@+-:,/=#*")


class AndroidController:
    """Hands of the system: tap, swipe, type, keys, launch, screenshot, dump."""

    def __init__(
        self,
        config: Optional[Config] = None,
        emulator: Optional[EmulatorManager] = None,
        runner: Optional[CommandRunner] = None,
    ) -> None:
        self.config = config or load_config()
        self.emulator = emulator or EmulatorManager(self.config, runner=runner)

    def tap(self, x: int, y: int) -> None:
        self._input(["tap", str(int(x)), str(int(y))])

    def swipe(self, x1: int, y1: int, x2: int, y2: int, duration_ms: int = 400) -> None:
        self._input(
            [
                "swipe",
                str(int(x1)),
                str(int(y1)),
                str(int(x2)),
                str(int(y2)),
                str(int(duration_ms)),
            ]
        )

    def scroll_down(self, duration_ms: int = 400) -> None:
        self._scroll(direction="down", duration_ms=duration_ms)

    def scroll_up(self, duration_ms: int = 400) -> None:
        self._scroll(direction="up", duration_ms=duration_ms)

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
        else:
            logger.info("Typing %d character(s)", len(text))
        try:
            for chunk in _encode_adb_text_chunks(text):
                self._input(["text", chunk])
        except SubprocessFailedError as exc:
            raise TextInputFailedError("ADB text input failed", details=exc.details) from exc

    def press_back(self) -> None:
        self._input(["keyevent", "4"])

    def press_home(self) -> None:
        self._input(["keyevent", "3"])

    def launch_app(self, package_name: str) -> None:
        self.emulator.launch_app(package_name)

    def restart_app(self, package_name: str) -> None:
        self.emulator.restart_app(package_name)

    def force_stop_app(self, package_name: str) -> None:
        self.emulator.force_stop_app(package_name)

    def clear_app_data(self, package_name: str) -> None:
        self.emulator.clear_app_data(package_name)

    def capture_screenshot(self, output_path: str | Path) -> Path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        try:
            result = self.emulator.adb(["exec-out", "screencap", "-p"], binary=True, timeout=20.0)
        except SubprocessFailedError as exc:
            raise ScreenshotFailedError("screencap failed", details=exc.details) from exc
        data = result.stdout_bytes
        if not data or len(data) < 32:
            raise ScreenshotFailedError(
                "Screenshot capture returned empty output",
                details={"stderr": result.stderr},
            )
        dest.write_bytes(data)
        return dest

    def dump_ui_hierarchy(self, output_path: str | Path) -> Path:
        dest = Path(output_path)
        dest.parent.mkdir(parents=True, exist_ok=True)
        remote = "/sdcard/revrag_window_dump.xml"
        dump = self.emulator.adb(
            ["shell", "uiautomator", "dump", remote],
            check=False,
            timeout=20.0,
        )
        combined = (dump.stdout or "") + (dump.stderr or "")
        if dump.returncode != 0 and "UI hierchary dumped" not in combined and "dumped to" not in combined.lower():
            raise UiDumpFailedError(
                "uiautomator dump failed",
                details={"stdout": dump.stdout, "stderr": dump.stderr},
            )
        pull = self.emulator.adb(["pull", remote, str(dest)], check=False, timeout=20.0)
        if not dest.is_file() or dest.stat().st_size == 0:
            raise UiDumpFailedError(
                "Failed to pull UI hierarchy XML from the device",
                details={"stdout": pull.stdout, "stderr": pull.stderr},
            )
        return dest

    def wait_for_ui_settle(
        self,
        timeout: Optional[float] = None,
        poll_interval: Optional[float] = None,
        fingerprint_fn=None,
    ) -> bool:
        """Wait until consecutive UI fingerprints match, or until timeout.

        Returns True if a stable state was observed, False if we timed out
        (callers may still proceed with the last known state).
        """
        timeout = self.config.ui_settle_timeout if timeout is None else timeout
        poll_interval = (
            self.config.ui_settle_poll_interval if poll_interval is None else poll_interval
        )
        time.sleep(min(0.35, timeout))
        if timeout <= 0:
            return True
        if fingerprint_fn is None:
            return True
        deadline = time.monotonic() + timeout
        last = None
        stable_hits = 0
        while time.monotonic() < deadline:
            current = fingerprint_fn()
            if current is not None and current == last:
                stable_hits += 1
                if stable_hits >= 2:
                    return True
            else:
                stable_hits = 0
                last = current
            time.sleep(poll_interval)
        logger.warning("UI did not fully settle within %.2fs; continuing", timeout)
        return False

    def _scroll(self, direction: str, duration_ms: int) -> None:
        width, height = self._window_size()
        cx = width // 2
        top = int(height * 0.28)
        bottom = int(height * 0.72)
        try:
            if direction == "down":
                self.swipe(cx, bottom, cx, top, duration_ms=duration_ms)
            else:
                self.swipe(cx, top, cx, bottom, duration_ms=duration_ms)
        except SubprocessFailedError as exc:
            raise ScrollFailedError("Scroll swipe failed", details=exc.details) from exc

    def _window_size(self) -> tuple[int, int]:
        result = self.emulator.adb(["shell", "wm", "size"], check=False)
        match = re.search(r"(\d+)\s*x\s*(\d+)", result.stdout or "")
        if match:
            return int(match.group(1)), int(match.group(2))
        return 1080, 1920

    def _input(self, args: list[str]) -> CommandResult:
        return self.emulator.adb(["shell", "input", *args], check=True)


def _encode_adb_text_chunks(text: str) -> list[str]:
    """Encode text for ``adb shell input text`` without shell interpolation.

    Spaces become ``%s``. Other characters outside a conservative whitelist
    are sent as short chunks so metacharacters never reach a shell string.
    """
    chunks: list[str] = []
    buf: list[str] = []

    def flush() -> None:
        if buf:
            chunks.append("".join(buf))
            buf.clear()

    for ch in text:
        if ch == " ":
            buf.append("%s")
        elif ch == "%":
            buf.append("%")
        elif ch in _SAFE_TEXT_CHARS:
            buf.append(ch)
        elif ch in "\r\n":
            flush()
            chunks.append("\\n")
        else:
            flush()
            # Backslash-escape a single character as its own input invocation.
            chunks.append("\\" + ch)
        if len(buf) >= 40:
            flush()
    flush()
    return chunks or [""]
