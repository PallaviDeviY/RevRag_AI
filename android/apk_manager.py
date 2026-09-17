"""APK validation, installation, and package-name extraction."""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path
from typing import Optional, Sequence

from .config import Config, load_config
from .emulator_manager import CommandRunner, EmulatorManager
from .exceptions import (
    ApkNotFoundError,
    InstallationFailedError,
    InvalidApkError,
)
from .models import ErrorInfo, InstallResult

logger = logging.getLogger(__name__)

_PACKAGE_RE = re.compile(r"package:\s*name='([^']+)'")
_BADGING_RE = re.compile(r"package:\s*name='([^']+)'")
_MANIFEST_PACKAGE_RE = re.compile(rb'package="([A-Za-z0-9._]+)"')
_DUMPSYS_PACKAGE_RE = re.compile(r"Package \[([^\]]+)\]")
_DUMPSYS_UPDATE_RE = re.compile(r"lastUpdateTime=([^\s]+(?:\s+[^\s]+)?)")


def validate_apk(apk_path: str) -> Path:
    if not apk_path or not str(apk_path).strip():
        raise InvalidApkError("APK path is empty")
    path = Path(apk_path).expanduser()
    if not path.exists() or not path.is_file():
        raise ApkNotFoundError(f"APK file not found: {apk_path}")
    if path.suffix.lower() != ".apk":
        raise InvalidApkError(f"File does not have a .apk extension: {path.name}")
    if path.stat().st_size == 0:
        raise InvalidApkError(f"APK file is empty: {path}")
    return path.resolve()


def extract_package_name(apk_path: str, runner: Optional[CommandRunner] = None) -> Optional[str]:
    path = Path(apk_path)
    runner = runner or CommandRunner(10.0)
    for tool in ("aapt", "aapt2"):
        try:
            result = runner.run([tool, "dump", "badging", str(path)], timeout=15.0, check=False)
        except Exception:
            continue
        if result.ok:
            match = _BADGING_RE.search(result.stdout)
            if match:
                return match.group(1)
    try:
        with zipfile.ZipFile(path) as zf:
            data = zf.read("AndroidManifest.xml")
        match = _MANIFEST_PACKAGE_RE.search(data)
        if match:
            return match.group(1).decode("ascii")
    except Exception:
        logger.debug("Could not extract package name from %s", path, exc_info=True)
    return None


def install_apk(
    apk_path: str,
    *,
    config: Optional[Config] = None,
    emulator: Optional[EmulatorManager] = None,
    reinstall: bool = True,
) -> InstallResult:
    config = config or load_config()
    emulator = emulator or EmulatorManager(config)
    try:
        path = validate_apk(apk_path)
        emulator.require_adb()
        emulator.resolve_serial(required=True)
        package_name = extract_package_name(str(path), runner=emulator.runner)
        packages_before = _pm_packages(emulator) if not package_name else []
        args = ["install"]
        if reinstall:
            args.append("-r")
        args.append(str(path))
        result = emulator.adb(args, timeout=max(60.0, config.default_timeout), check=False)
        combined = (result.stdout or "") + (result.stderr or "")
        if result.returncode != 0 or "Failure" in combined or "failed" in combined.lower():
            if "Success" not in combined:
                raise InstallationFailedError(
                    f"APK installation failed for {path.name}",
                    details={"stdout": result.stdout, "stderr": result.stderr},
                )
        if not package_name:
            package_name = _package_from_pm(emulator, path.stem, packages_before=packages_before)
        return InstallResult(
            success=True,
            apk_path=str(path),
            package_name=package_name,
            message="APK installed",
        )
    except (ApkNotFoundError, InvalidApkError, InstallationFailedError) as exc:
        logger.error("install_apk failed: %s", exc.message)
        return InstallResult(
            success=False,
            apk_path=str(apk_path),
            message=exc.message,
            error=ErrorInfo(code=exc.code, message=exc.message, details=exc.details),
        )
    except Exception as exc:  # structured, do not crash callers
        from .exceptions import AndroidControllerError

        if isinstance(exc, AndroidControllerError):
            logger.error("install_apk failed: %s", exc.message)
            return InstallResult(
                success=False,
                apk_path=str(apk_path),
                message=exc.message,
                error=ErrorInfo(code=exc.code, message=exc.message, details=exc.details),
            )
        logger.exception("Unexpected install failure")
        return InstallResult(
            success=False,
            apk_path=str(apk_path),
            message=str(exc),
            error=ErrorInfo(code="INSTALLATION_FAILED", message=str(exc)),
        )


def _package_from_pm(
    emulator: EmulatorManager,
    hint: str,
    *,
    packages_before: Optional[Sequence[str]] = None,
) -> Optional[str]:
    packages = _pm_packages(emulator)
    before = set(packages_before or [])
    added = [pkg for pkg in packages if pkg not in before]
    hint_lower = hint.lower() if hint else ""
    if hint_lower:
        for pkg in added:
            if hint_lower in pkg.lower():
                return pkg
    if len(added) == 1:
        return added[0]
    if hint_lower:
        for pkg in packages:
            if hint_lower in pkg.lower():
                return pkg
    if before:
        return _latest_updated_package_from_dumpsys(emulator, packages)
    return None


def _pm_packages(emulator: EmulatorManager) -> list[str]:
    result = emulator.adb(["shell", "pm", "list", "packages"], check=False)
    packages = []
    for line in (result.stdout or "").splitlines():
        line = line.strip()
        if line.startswith("package:"):
            packages.append(line.split(":", 1)[1].strip())
    return packages


def _latest_updated_package_from_dumpsys(
    emulator: EmulatorManager,
    known_packages: Sequence[str],
) -> Optional[str]:
    result = emulator.adb(
        ["shell", "dumpsys", "package", "packages"],
        check=False,
        timeout=30.0,
    )
    if not result.ok:
        return None

    known = set(known_packages)
    current_package: Optional[str] = None
    current_update: Optional[str] = None
    latest_package: Optional[str] = None
    latest_update: Optional[str] = None

    def consider() -> None:
        nonlocal latest_package, latest_update
        if not current_package or current_package not in known or not current_update:
            return
        if latest_update is None or current_update > latest_update:
            latest_package = current_package
            latest_update = current_update

    for line in (result.stdout or "").splitlines():
        package_match = _DUMPSYS_PACKAGE_RE.search(line)
        if package_match:
            consider()
            current_package = package_match.group(1)
            current_update = None
            continue
        update_match = _DUMPSYS_UPDATE_RE.search(line)
        if update_match and current_package:
            current_update = update_match.group(1)
    consider()
    return latest_package
