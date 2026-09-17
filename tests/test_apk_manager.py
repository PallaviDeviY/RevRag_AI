from pathlib import Path

import pytest

from android.apk_manager import extract_package_name, install_apk, validate_apk
from android.config import load_config
from android.emulator_manager import CommandRunner, EmulatorManager
from android.exceptions import ApkNotFoundError, InvalidApkError, SubprocessFailedError
from android.models import CommandResult


class MissingAaptRunner(CommandRunner):
    def run(self, args, *, timeout=None, check=False, binary=False):
        raise SubprocessFailedError("missing tool", details={"args": list(args)})


class FakeInstallEmulator(EmulatorManager):
    def __init__(self, pm_outputs, dumpsys_output: str = "") -> None:
        super().__init__(load_config(), runner=MissingAaptRunner())
        self.pm_outputs = list(pm_outputs)
        self.dumpsys_output = dumpsys_output
        self.calls = []

    def require_adb(self) -> None:
        return None

    def resolve_serial(self, required: bool = True):
        self._serial = "emulator-test"
        return self._serial

    def adb(self, extra, *, timeout=None, check=True, binary=False, with_serial=True):
        self.calls.append(list(extra))
        if list(extra[:4]) == ["shell", "pm", "list", "packages"]:
            stdout = self.pm_outputs.pop(0) if self.pm_outputs else ""
            return CommandResult(args=list(extra), returncode=0, stdout=stdout, stderr="")
        if list(extra[:4]) == ["shell", "dumpsys", "package", "packages"]:
            return CommandResult(args=list(extra), returncode=0, stdout=self.dumpsys_output, stderr="")
        if extra and extra[0] == "install":
            return CommandResult(args=list(extra), returncode=0, stdout="Success", stderr="")
        return CommandResult(args=list(extra), returncode=0, stdout="", stderr="")


def test_missing_apk(tmp_path: Path) -> None:
    missing = tmp_path / "nope.apk"
    with pytest.raises(ApkNotFoundError) as exc:
        validate_apk(str(missing))
    assert exc.value.code == "APK_NOT_FOUND"


def test_invalid_extension(tmp_path: Path) -> None:
    fake = tmp_path / "app.txt"
    fake.write_text("not an apk", encoding="utf-8")
    with pytest.raises(InvalidApkError) as exc:
        validate_apk(str(fake))
    assert exc.value.code == "INVALID_APK"


def test_empty_apk(tmp_path: Path) -> None:
    empty = tmp_path / "empty.apk"
    empty.write_bytes(b"")
    with pytest.raises(InvalidApkError):
        validate_apk(str(empty))


def test_valid_path(tmp_path: Path) -> None:
    apk = tmp_path / "demo.apk"
    apk.write_bytes(b"PK\x03\x04fake")
    resolved = validate_apk(str(apk))
    assert resolved.name == "demo.apk"
    assert resolved.is_file()


def test_extract_package_name_without_aapt(tmp_path: Path) -> None:
    apk = tmp_path / "plain.apk"
    apk.write_bytes(b"PK\x03\x04notzip")
    assert extract_package_name(str(apk)) is None


def test_install_apk_discovers_new_package_from_pm_diff(tmp_path: Path) -> None:
    apk = tmp_path / "ApiDemos-debug.apk"
    apk.write_bytes(b"PK\x03\x04notzip")
    emulator = FakeInstallEmulator(
        pm_outputs=[
            "package:com.android.settings\n",
            "package:com.android.settings\npackage:io.appium.android.apis\n",
        ]
    )

    result = install_apk(str(apk), emulator=emulator)

    assert result.success is True
    assert result.package_name == "io.appium.android.apis"
    assert ["install", "-r", str(apk.resolve())] in emulator.calls


def test_install_apk_discovers_reinstalled_package_from_dumpsys(tmp_path: Path) -> None:
    apk = tmp_path / "arbitrary-name.apk"
    apk.write_bytes(b"PK\x03\x04notzip")
    pm_output = "package:com.android.settings\npackage:io.appium.android.apis\n"
    dumpsys_output = """
    Package [com.android.settings] (abc):
      lastUpdateTime=2026-09-18 09:00:00
    Package [io.appium.android.apis] (def):
      lastUpdateTime=2026-09-18 10:00:00
    """
    emulator = FakeInstallEmulator(
        pm_outputs=[pm_output, pm_output],
        dumpsys_output=dumpsys_output,
    )

    result = install_apk(str(apk), emulator=emulator)

    assert result.success is True
    assert result.package_name == "io.appium.android.apis"


def test_install_apk_preserves_unknown_package_when_pm_has_no_package_lines(tmp_path: Path) -> None:
    apk = tmp_path / "plain.apk"
    apk.write_bytes(b"PK\x03\x04notzip")
    emulator = FakeInstallEmulator(pm_outputs=["Success", "Success"])

    result = install_apk(str(apk), emulator=emulator)

    assert result.success is True
    assert result.package_name is None
