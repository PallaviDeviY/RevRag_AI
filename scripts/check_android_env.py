#!/usr/bin/env python3
"""Print whether ADB, emulator, and project data directories are ready."""

from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from android.config import load_config  # noqa: E402
from android.emulator_manager import EmulatorManager  # noqa: E402


def main() -> int:
    config = load_config()
    config.ensure_directories()
    emulator = EmulatorManager(config)
    payload = {
        "python": sys.version.split()[0],
        "adb_path": config.adb_path,
        "adb_available": emulator.is_adb_available(),
        "mock": config.mock,
        "data_dir": "data",
        "devices": [],
    }
    if payload["adb_available"]:
        payload["devices"] = [d.to_dict() for d in emulator.get_devices()]
        payload["selected_serial"] = emulator.resolve_serial(required=False)
    print(json.dumps(payload, indent=2))
    return 0 if payload["adb_available"] or config.mock else 1


if __name__ == "__main__":
    raise SystemExit(main())
