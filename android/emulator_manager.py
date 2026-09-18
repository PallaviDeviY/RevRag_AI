"""ADB availability, device selection, emulator lifecycle, and app process control."""

from __future__ import annotations

import logging
import shutil
import time
from typing import List, Optional, Sequence

from .config import Config, load_config
from .exceptions import (
    AdbUnavailableError,
    DeviceTimeoutError,
    EmulatorUnavailableError,
    LaunchFailedError,
    SubprocessFailedError,
)
from .models import CommandResult, DeviceInfo

logger = logging.getLogger(__name__)


def _decode(data: bytes) -> str:
    return data.decode("utf-8", errors="replace")


class CommandRunner:
    """Safe subprocess runner: argument lists only, timeouts, captured I/O."""

    def __init__(self, default_timeout: float = 10.0) -> None:
        self.default_timeout = default_timeout

    def run(
        self,
        args: Sequence[str],
        *,
        timeout: Optional[float] = None,
        check: bool = False,
        binary: bool = False,
    ) -> CommandResult:
        import subprocess

        timeout = self.default_timeout if timeout is None else timeout
        arg_list = [str(a) for a in args]
        logger.debug("Running command: %s", arg_list)
        try:
            completed = subprocess.run(
                arg_list,
                capture_output=True,
                timeout=timeout,
                check=False,
                shell=False,
            )
        except FileNotFoundError as exc:
            raise SubprocessFailedError(
                f"Executable not found: {arg_list[0]}",
                details={"args": arg_list},
            ) from exc
        except subprocess.TimeoutExpired as exc:
            stdout = _decode(exc.stdout or b"")
            stderr = _decode(exc.stderr or b"")
            raise SubprocessFailedError(
                f"Command timed out after {timeout}s: {arg_list[0]}",
                details={"args": arg_list, "stdout": stdout, "stderr": stderr},
            ) from exc

        result = CommandResult(
            args=arg_list,
            returncode=completed.returncode,
            stdout="" if binary else _decode(completed.stdout),
            stderr=_decode(completed.stderr),
            stdout_bytes=completed.stdout or b"",
        )
        if check and not result.ok:
            raise SubprocessFailedError(
                f"Command failed ({result.returncode}): {arg_list[0]}",
                details={
                    "args": arg_list,
                    "returncode": result.returncode,
                    "stdout": result.stdout,
                    "stderr": result.stderr,
                },
            )
        return result


class EmulatorManager:
    def __init__(
        self,
        config: Optional[Config] = None,
        runner: Optional[CommandRunner] = None,
    ) -> None:
        self.config = config or load_config()
        self.runner = runner or CommandRunner(self.config.default_timeout)
        self._serial = self.config.android_serial

    @property
    def serial(self) -> Optional[str]:
        return self._serial

    def is_adb_available(self) -> bool:
        if shutil.which(self.config.adb_path) is None and not _looks_like_abs_exe(
            self.config.adb_path
        ):
            return False
        try:
            result = self.runner.run([self.config.adb_path, "version"], timeout=8.0)
            return result.ok
        except SubprocessFailedError:
            return False

    def require_adb(self) -> None:
        if not self.is_adb_available():
            raise AdbUnavailableError(
                f"ADB is not available at '{self.config.adb_path}'. "
                "Install Android platform-tools and set ADB_PATH if needed."
            )

    def adb(self, extra: Sequence[str], *, timeout: Optional[float] = None, check: bool = True,
            binary: bool = False, with_serial: bool = True) -> CommandResult:
        self.require_adb()
        args: List[str] = [self.config.adb_path]
        serial = self.resolve_serial(required=False) if with_serial else None
        if serial:
            args.extend(["-s", serial])
        args.extend(str(x) for x in extra)
        return self.runner.run(args, timeout=timeout, check=check, binary=binary)

    def get_devices(self) -> List[DeviceInfo]:
        self.require_adb()
        result = self.runner.run([self.config.adb_path, "devices", "-l"], timeout=10.0, check=True)
        devices: List[DeviceInfo] = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or line.startswith("List of devices"):
                continue
            parts = line.split()
            if len(parts) < 2:
                continue
            serial, state = parts[0], parts[1]
            product = None
            for token in parts[2:]:
                if token.startswith("product:"):
                    product = token.split(":", 1)[1]
            is_emulator = serial.startswith("emulator-") or (product or "").startswith("sdk")
            devices.append(
                DeviceInfo(serial=serial, state=state, is_emulator=is_emulator, product=product)
            )
        return devices

    def get_online_devices(self) -> List[DeviceInfo]:
        return [d for d in self.get_devices() if d.state == "device"]

    def detect_emulator(self) -> Optional[DeviceInfo]:
        online = self.get_online_devices()
        for device in online:
            if device.is_emulator:
                return device
        return None

    def resolve_serial(self, required: bool = True) -> Optional[str]:
        if self._serial:
            return self._serial
        if self.config.android_serial:
            self._serial = self.config.android_serial
            return self._serial
        devices = self.get_online_devices()
        emulator = next((d for d in devices if d.is_emulator), None)
        chosen = emulator or (devices[0] if devices else None)
        if chosen:
            self._serial = chosen.serial
            logger.info("Selected Android device serial=%s state=%s", chosen.serial, chosen.state)
            return self._serial
        if required:
            raise EmulatorUnavailableError(
                "No connected Android emulator/device found. "
                "Start an emulator or set ANDROID_SERIAL."
            )
        return None

    def wait_for_device(self, timeout: Optional[float] = None) -> DeviceInfo:
        timeout = self.config.device_wait_timeout if timeout is None else timeout
        deadline = time.monotonic() + timeout
        last_error = "No devices reported"
        while time.monotonic() < deadline:
            try:
                devices = self.get_devices()
            except (AdbUnavailableError, SubprocessFailedError) as exc:
                last_error = str(exc)
                time.sleep(1.0)
                continue
            preferred = self.config.android_serial
            for device in devices:
                if device.state != "device":
                    continue
                if preferred and device.serial != preferred:
                    continue
                self._serial = device.serial
                return device
            last_error = f"Connected devices: {[d.to_dict() for d in devices]}"
            time.sleep(1.0)
        raise DeviceTimeoutError(
            f"Timed out waiting {timeout}s for an Android device to become ready. {last_error}"
        )

    def launch_emulator(self, avd: Optional[str] = None) -> None:
        avd_name = avd or self.config.android_avd
        if not avd_name:
            raise EmulatorUnavailableError(
                "Cannot launch emulator: ANDROID_AVD / --avd is not configured."
            )
        if shutil.which(self.config.emulator_path) is None and not _looks_like_abs_exe(
            self.config.emulator_path
        ):
            raise EmulatorUnavailableError(
                f"Emulator binary not found at '{self.config.emulator_path}'."
            )
        self.runner.run(
            [self.config.emulator_path, "-avd", avd_name, "-no-snapshot-save"],
            timeout=self.config.emulator_boot_timeout,
            check=False,
        )

    def restart_emulator(self, timeout: Optional[float] = None) -> DeviceInfo:
        self.require_adb()
        serial = self.resolve_serial(required=False)
        if serial:
            self.runner.run(
                [self.config.adb_path, "-s", serial, "reboot"],
                timeout=self.config.default_timeout,
                check=False,
            )
        return self.wait_for_device(timeout=timeout)

    def force_stop_app(self, package_name: str) -> None:
        result = self.adb(["shell", "am", "force-stop", package_name], check=False)
        if not result.ok:
            logger.warning("force-stop failed for %s: %s", package_name, result.stderr)

    def clear_app_data(self, package_name: str) -> None:
        result = self.adb(["shell", "pm", "clear", package_name], check=False)
        if not result.ok:
            raise SubprocessFailedError(
                f"Failed to clear data for {package_name}",
                details={"stderr": result.stderr, "stdout": result.stdout},
            )

    def launch_app(self, package_name: str) -> None:
        result = self.adb(
            [
                "shell",
                "monkey",
                "-p",
                package_name,
                "-c",
                "android.intent.category.LAUNCHER",
                "1",
            ],
            timeout=max(25.0, self.config.default_timeout),
            check=False,
        )
        if not result.ok or "No activities found" in (result.stdout + result.stderr):
            raise LaunchFailedError(
                f"Failed to launch package '{package_name}'",
                details={"stdout": result.stdout, "stderr": result.stderr},
            )

    def restart_app(self, package_name: str) -> None:
        self.force_stop_app(package_name)
        time.sleep(0.4)
        self.launch_app(package_name)

    def current_focus(self) -> tuple[Optional[str], Optional[str]]:
        """Return (package, activity) from dumpsys window, if available."""
        result = self.adb(["shell", "dumpsys", "window", "windows"], check=False, timeout=15.0)
        text = result.stdout or ""
        for marker in ("mCurrentFocus=", "mFocusedApp="):
            if marker not in text:
                continue
            for line in text.splitlines():
                if marker not in line:
                    continue
                package, activity = _parse_focus_line(line)
                if package:
                    return package, activity
        return None, None


def _parse_focus_line(line: str) -> tuple[Optional[str], Optional[str]]:
    # Example: mCurrentFocus=Window{... u0 com.example/.MainActivity}
    if "/" not in line:
        return None, None
    try:
        token = line.split()[-1].rstrip("}")
        package, _, activity = token.partition("/")
        if activity.startswith("."):
            activity = package + activity
        package = package.strip()
        activity = activity.strip() or None
        if package and "." in package:
            return package, activity
    except Exception:
        return None, None
    return None, None


def _looks_like_abs_exe(path: str) -> bool:
    from pathlib import Path

    candidate = Path(path)
    return candidate.is_file()
