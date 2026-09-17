from android.emulator_manager import CommandRunner, EmulatorManager
from android.models import CommandResult


class FakeRunner(CommandRunner):
    def __init__(self, mapping):
        super().__init__(default_timeout=5)
        self.mapping = mapping
        self.calls = []

    def run(self, args, *, timeout=None, check=False, binary=False):
        self.calls.append(list(args))
        key = " ".join(str(a) for a in args)
        for needle, result in self.mapping.items():
            if needle in key:
                if check and result.returncode != 0:
                    from android.exceptions import SubprocessFailedError

                    raise SubprocessFailedError("fail", details={"args": list(args)})
                return result
        return CommandResult(args=list(args), returncode=0, stdout="", stderr="")


def test_get_devices_does_not_hardcode_serial(monkeypatch, tmp_path) -> None:
    runner = FakeRunner(
        {
            "version": CommandResult(["adb", "version"], 0, "Android Debug Bridge version 1.0.41", ""),
            "devices": CommandResult(
                ["adb", "devices", "-l"],
                0,
                "List of devices attached\n"
                "emulator-9999          device product:sdk_gphone\n"
                "ABC123XYZ             device product:pixel\n",
                "",
            ),
        }
    )
    monkeypatch.setenv("ADB_PATH", "adb")
    monkeypatch.setenv("ANDROID_SERIAL", "")
    from android.config import load_config

    manager = EmulatorManager(load_config(), runner=runner)
    monkeypatch.setattr(manager, "is_adb_available", lambda: True)
    devices = manager.get_devices()
    assert {d.serial for d in devices} == {"emulator-9999", "ABC123XYZ"}
    serial = manager.resolve_serial()
    assert serial == "emulator-9999"


def test_adb_unavailable(monkeypatch) -> None:
    monkeypatch.setenv("ADB_PATH", "adb_not_real_binary_revrag")
    from android.config import load_config
    from android.exceptions import AdbUnavailableError

    manager = EmulatorManager(load_config())
    assert manager.is_adb_available() is False
    try:
        manager.require_adb()
    except AdbUnavailableError as exc:
        assert exc.code == "ADB_UNAVAILABLE"
    else:
        raise AssertionError("expected ADB_UNAVAILABLE")
