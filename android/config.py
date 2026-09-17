"""Environment-driven configuration. No hardcoded device serials or APK names."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def _project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def load_dotenv(path: Optional[Path] = None) -> None:
    """Minimal .env loader (does not override existing environment variables)."""
    env_path = path or (_project_root() / ".env")
    if not env_path.is_file():
        return
    for raw_line in env_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _as_float(name: str, default: float) -> float:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError:
        return default


@dataclass
class Config:
    project_root: Path
    adb_path: str
    android_serial: Optional[str]
    android_avd: Optional[str]
    emulator_path: str
    default_timeout: float
    ui_settle_timeout: float
    ui_settle_poll_interval: float
    device_wait_timeout: float
    emulator_boot_timeout: float
    data_dir: Path
    screenshot_dir: Path
    ui_tree_dir: Path
    observation_dir: Path
    apk_path: Optional[str]
    package_name: Optional[str]
    mock: bool

    @property
    def screenshot_rel_dir(self) -> str:
        return "screenshots"

    @property
    def ui_tree_rel_dir(self) -> str:
        return "ui_trees"

    @property
    def observation_rel_dir(self) -> str:
        return "observations"

    def ensure_directories(self) -> None:
        self.screenshot_dir.mkdir(parents=True, exist_ok=True)
        self.ui_tree_dir.mkdir(parents=True, exist_ok=True)
        self.observation_dir.mkdir(parents=True, exist_ok=True)
        (self.data_dir / "apk").mkdir(parents=True, exist_ok=True)
        (self.data_dir / "sample").mkdir(parents=True, exist_ok=True)


def load_config(project_root: Optional[Path] = None) -> Config:
    load_dotenv()
    root = project_root or _project_root()
    data_dir = Path(os.environ.get("DATA_DIR", "data"))
    if not data_dir.is_absolute():
        data_dir = root / data_dir

    screenshot_dir = Path(os.environ.get("SCREENSHOT_DIR", str(data_dir / "screenshots")))
    if not screenshot_dir.is_absolute():
        screenshot_dir = root / screenshot_dir

    ui_tree_dir = Path(os.environ.get("UI_TREE_DIR", str(data_dir / "ui_trees")))
    if not ui_tree_dir.is_absolute():
        ui_tree_dir = root / ui_tree_dir

    observation_dir = Path(os.environ.get("OBSERVATION_DIR", str(data_dir / "observations")))
    if not observation_dir.is_absolute():
        observation_dir = root / observation_dir

    serial = os.environ.get("ANDROID_SERIAL", "").strip() or None
    avd = os.environ.get("ANDROID_AVD", "").strip() or None
    apk_path = os.environ.get("APK_PATH", "").strip() or None
    package_name = os.environ.get("PACKAGE_NAME", "").strip() or None

    return Config(
        project_root=root,
        adb_path=os.environ.get("ADB_PATH", "adb").strip() or "adb",
        android_serial=serial,
        android_avd=avd,
        emulator_path=os.environ.get("EMULATOR_PATH", "emulator").strip() or "emulator",
        default_timeout=_as_float("DEFAULT_TIMEOUT", 10.0),
        ui_settle_timeout=_as_float("UI_SETTLE_TIMEOUT", 5.0),
        ui_settle_poll_interval=_as_float("UI_SETTLE_POLL_INTERVAL", 0.25),
        device_wait_timeout=_as_float("DEVICE_WAIT_TIMEOUT", 60.0),
        emulator_boot_timeout=_as_float("EMULATOR_BOOT_TIMEOUT", 120.0),
        data_dir=data_dir,
        screenshot_dir=screenshot_dir,
        ui_tree_dir=ui_tree_dir,
        observation_dir=observation_dir,
        apk_path=apk_path,
        package_name=package_name,
        mock=_as_bool(os.environ.get("ANDROID_MOCK"), False),
    )
