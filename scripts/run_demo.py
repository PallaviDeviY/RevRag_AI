#!/usr/bin/env python3
"""Demonstrate APK → launch → observation → Action JSON → new observation.

Usage:
  python scripts/run_demo.py --apk path/to/app.apk
  python scripts/run_demo.py --mock
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from android.actions import ActionExecutor  # noqa: E402
from android.config import load_config  # noqa: E402


def main() -> int:
    parser = argparse.ArgumentParser(description="RevRag Android controller demo")
    parser.add_argument("--apk", help="Path to an APK (required unless --mock)")
    parser.add_argument("--package", help="Package name (optional; detected after install when possible)")
    parser.add_argument("--mock", action="store_true", help="Run without a real emulator")
    parser.add_argument(
        "--action",
        default=str(ROOT / "data/sample/action_tap.json"),
        help="Action JSON to execute after the initial observation",
    )
    args = parser.parse_args()

    if not args.mock and not args.apk:
        parser.error("--apk is required unless --mock is set")

    config = load_config()
    executor = ActionExecutor(config=config, mock=args.mock)
    print("== 1. Environment ==")
    emulator = executor.controller.emulator
    print(json.dumps({
        "adb_available": emulator.is_adb_available(),
        "mock": args.mock,
        "devices": [d.to_dict() for d in emulator.get_devices()] if emulator.is_adb_available() else [],
    }, indent=2))

    package = args.package or config.package_name or "com.example.app"
    if args.apk:
        print("\n== 2. Install APK ==")
        installed = executor.install(args.apk)
        print(json.dumps(installed.to_dict(), indent=2))
        if not installed.success and not args.mock:
            return 1
        package = installed.package_name or package

    print("\n== 3. Launch + initial observation ==")
    launched = executor.launch(package)
    print(json.dumps(launched.to_dict(), indent=2))
    if not launched.success:
        return 1
    obs1 = launched.observation
    assert obs1 is not None
    print(f"screenshot: data/{obs1.screenshot_path}")
    print(f"ui_tree:    data/{obs1.ui_tree_path}")
    print(f"json:       data/observations/{obs1.observation_id}.json")

    print("\n== 4. Execute sample Action JSON ==")
    result = executor.execute(args.action)
    print(json.dumps(result.to_dict(), indent=2))
    if result.success and result.observation:
        obs2 = result.observation
        print(f"screenshot: data/{obs2.screenshot_path}")
        print(f"ui_tree:    data/{obs2.ui_tree_path}")
        print(f"json:       data/observations/{obs2.observation_id}.json")
        return 0
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
