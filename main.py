"""CLI for the Android Controller & Observation module."""

from __future__ import annotations

import argparse
import json
import logging
import sys

from android.actions import ActionExecutor
from android.config import load_config


def _print(payload) -> None:
    print(json.dumps(payload, indent=2))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="RevRag AI — Android Controller & Observation (Member 1)"
    )
    parser.add_argument("--mock", action="store_true", help="Use the in-memory mock backend")
    sub = parser.add_subparsers(dest="command", required=True)

    sub.add_parser("check", help="Check ADB and connected devices")

    install = sub.add_parser("install", help="Install an APK")
    install.add_argument("--apk", required=True)

    launch = sub.add_parser("launch", help="Launch an application and observe")
    launch.add_argument("--package", required=True)

    sub.add_parser("screenshot", help="Capture a screenshot only")
    sub.add_parser("observe", help="Capture screenshot + UI tree + Observation JSON")

    execute = sub.add_parser("execute", help="Execute Action JSON and print Observation JSON")
    execute.add_argument("--action", required=True, help="Path to Action JSON")

    reset = sub.add_parser("reset", help="Force-stop, optionally clear, relaunch, observe")
    reset.add_argument("--package", required=True)
    reset.add_argument("--clear-data", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(name)s: %(message)s")
    args = build_parser().parse_args(argv)
    config = load_config()
    if args.mock:
        config.mock = True
    executor = ActionExecutor(config=config, mock=config.mock)
    emulator = executor.controller.emulator

    if args.command == "check":
        info = {
            "adb_available": emulator.is_adb_available(),
            "mock": config.mock,
            "devices": [d.to_dict() for d in (emulator.get_devices() if emulator.is_adb_available() else [])],
        }
        try:
            info["selected_serial"] = emulator.resolve_serial(required=False)
        except Exception as exc:
            info["selected_serial"] = None
            info["serial_error"] = str(exc)
        _print(info)
        return 0 if info["adb_available"] or config.mock else 2

    if args.command == "install":
        _print(executor.install(args.apk).to_dict())
        return 0

    if args.command == "launch":
        _print(executor.launch(args.package).to_dict())
        return 0

    if args.command == "screenshot":
        config.ensure_directories()
        dest = config.screenshot_dir / "manual.png"
        executor.controller.capture_screenshot(dest)
        _print({"success": True, "screenshot_path": "screenshots/manual.png"})
        return 0

    if args.command == "observe":
        _print(executor.observe().to_dict())
        return 0

    if args.command == "execute":
        _print(executor.execute(args.action).to_dict())
        return 0

    if args.command == "reset":
        _print(executor.reset_application(args.package, clear_data=args.clear_data).to_dict())
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
