"""APK validation, installation, and package-name extraction."""

from __future__ import annotations

import logging
import re
import zipfile
from pathlib import Path
from typing import Mapping, Optional, Sequence, Union

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
        packages_before = _pm_package_map(emulator) if not package_name else {}
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


def _extract_tokens(text: str) -> set[str]:
    s = re.sub(r"([a-z])([A-Z])", r"\1 \2", text)
    tokens = {t.lower() for t in re.findall(r"[A-Za-z0-9]+", s) if len(t) >= 2}
    tokens -= {"debug", "release", "unsigned", "signed", "test", "aligned", "apk", "universal"}
    return tokens


def _score_package(hint: str, pkg: str, device_path: str = "") -> int:
    if not hint:
        return 0
    hint_lower = hint.lower()
    pkg_lower = pkg.lower()
    clean_hint = re.sub(
        r"[-_.](debug|release|unsigned|signed|test|aligned|universal).*", "", hint_lower
    )
    score = 0
    if clean_hint and clean_hint == pkg_lower:
        score = 90
    elif clean_hint and clean_hint in pkg_lower:
        score = 70
    elif hint_lower in pkg_lower:
        score = 60
    elif pkg_lower in hint_lower:
        score = 50

    hint_tokens = _extract_tokens(hint)
    pkg_tokens = _extract_tokens(pkg)
    path_tokens = _extract_tokens(device_path) if device_path else set()
    token_score = 0
    for ht in hint_tokens:
        for pt in pkg_tokens:
            if ht == pt:
                token_score += 30
            elif ht.startswith(pt) or pt.startswith(ht):
                token_score += 20
            elif ht in pt or pt in ht:
                token_score += 10
        for pat in path_tokens:
            if ht == pat:
                token_score += 15
            elif ht.startswith(pat) or pat.startswith(ht):
                token_score += 10

    if token_score > 0:
        score += token_score
        if device_path.startswith("/data/app"):
            score += 5

    return score


def _best_matching_package(
    hint: str,
    packages: Sequence[str],
    pkg_map: Mapping[str, str],
) -> Optional[str]:
    scored = []
    for pkg in packages:
        score = _score_package(hint, pkg, pkg_map.get(pkg, ""))
        if score > 0:
            scored.append((score, pkg))
    if scored:
        scored.sort(key=lambda x: x[0], reverse=True)
        return scored[0][1]
    return None


def _pm_package_map(emulator: EmulatorManager) -> dict[str, str]:
    result = emulator.adb(["shell", "pm", "list", "packages", "-f"], check=False)
    output = result.stdout or ""
    if not result.ok or "package:" not in output:
        result = emulator.adb(["shell", "pm", "list", "packages"], check=False)
        output = result.stdout or ""
    pkg_map: dict[str, str] = {}
    for line in output.splitlines():
        line = line.strip()
        if not line.startswith("package:"):
            continue
        rest = line[len("package:") :].strip()
        if "=" in rest:
            apk_path, _, pkg = rest.rpartition("=")
            pkg_map[pkg.strip()] = apk_path.strip()
        elif rest:
            pkg_map[rest.strip()] = ""
    return pkg_map


def _pm_packages(emulator: EmulatorManager) -> list[str]:
    return list(_pm_package_map(emulator).keys())


def _package_from_pm(
    emulator: EmulatorManager,
    hint: str,
    *,
    packages_before: Optional[Union[Mapping[str, str], Sequence[str]]] = None,
) -> Optional[str]:
    after_map = _pm_package_map(emulator)
    if not after_map:
        return None

    before_map: dict[str, str] = {}
    if packages_before is not None:
        if isinstance(packages_before, (dict, Mapping)):
            before_map = dict(packages_before)
        else:
            before_map = {pkg: "" for pkg in packages_before}

    # 1. Check for newly added packages
    added = [pkg for pkg in after_map if pkg not in before_map]
    if added:
        if hint:
            best_added = _best_matching_package(hint, added, after_map)
            if best_added:
                return best_added
        if len(added) == 1:
            return added[0]

    # 2. Check for reinstalled package where device APK path changed
    if before_map:
        changed_paths = [
            pkg
            for pkg, path in after_map.items()
            if pkg in before_map and path and before_map.get(pkg) and path != before_map[pkg]
        ]
        if changed_paths:
            if hint:
                best_changed = _best_matching_package(hint, changed_paths, after_map)
                if best_changed:
                    return best_changed
            if len(changed_paths) == 1:
                return changed_paths[0]

    # 3. Match hint against packages, prioritizing user-installed (/data/app) packages
    if hint:
        data_app_packages = [
            pkg for pkg, path in after_map.items() if path.startswith("/data/app")
        ]
        if data_app_packages:
            best = _best_matching_package(hint, data_app_packages, after_map)
            if best:
                return best

        best = _best_matching_package(hint, list(after_map.keys()), after_map)
        if best:
            return best

    # 4. Fallback to dumpsys for cases with arbitrary names and no path changes (e.g. unit tests)
    if before_map:
        dumpsys_pkg = _latest_updated_package_from_dumpsys(
            emulator, list(after_map.keys()), hint=hint
        )
        if dumpsys_pkg:
            return dumpsys_pkg

    return None


def _latest_updated_package_from_dumpsys(
    emulator: EmulatorManager,
    known_packages: Sequence[str],
    hint: Optional[str] = None,
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
    candidates: list[tuple[str, str]] = []

    def consider() -> None:
        if not current_package or current_package not in known or not current_update:
            return
        candidates.append((current_update, current_package))

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

    if not candidates:
        return None

    # If hint is provided, prioritize candidates that match hint tokens
    if hint:
        hint_candidates = [
            (update, pkg) for update, pkg in candidates if _score_package(hint, pkg) > 0
        ]
        if hint_candidates:
            hint_candidates.sort(key=lambda x: x[0], reverse=True)
            return hint_candidates[0][1]

    candidates.sort(key=lambda x: x[0], reverse=True)
    return candidates[0][1]
