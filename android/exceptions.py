"""Structured errors for the Android controller.

Exploration callers should catch `AndroidControllerError` (or inspect
`ExecuteResult`) instead of letting a single failed ADB action crash the run.
"""

from __future__ import annotations

from typing import Any, Dict, Optional


class AndroidControllerError(Exception):
    """Base error with a stable machine-readable code."""

    code = "ANDROID_CONTROLLER_ERROR"

    def __init__(
        self,
        message: str,
        *,
        code: Optional[str] = None,
        action_id: Optional[str] = None,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.code = code or self.code
        self.action_id = action_id
        self.details = details or {}

    def to_dict(self) -> Dict[str, Any]:
        payload: Dict[str, Any] = {
            "success": False,
            "error": {
                "code": self.code,
                "message": self.message,
            },
        }
        if self.action_id:
            payload["error"]["action_id"] = self.action_id
        if self.details:
            payload["error"]["details"] = self.details
        return payload


class ApkNotFoundError(AndroidControllerError):
    code = "APK_NOT_FOUND"


class InvalidApkError(AndroidControllerError):
    code = "INVALID_APK"


class AdbUnavailableError(AndroidControllerError):
    code = "ADB_UNAVAILABLE"


class EmulatorUnavailableError(AndroidControllerError):
    code = "EMULATOR_UNAVAILABLE"


class InstallationFailedError(AndroidControllerError):
    code = "INSTALLATION_FAILED"


class LaunchFailedError(AndroidControllerError):
    code = "LAUNCH_FAILED"


class AppCrashError(AndroidControllerError):
    code = "APP_CRASH"


class UiDumpFailedError(AndroidControllerError):
    code = "UI_DUMP_FAILED"


class ScreenshotFailedError(AndroidControllerError):
    code = "SCREENSHOT_FAILED"


class ElementNotFoundError(AndroidControllerError):
    code = "ELEMENT_NOT_FOUND"


class InvalidBoundsError(AndroidControllerError):
    code = "INVALID_BOUNDS"


class ActionTimeoutError(AndroidControllerError):
    code = "ACTION_TIMEOUT"


class UnsupportedActionError(AndroidControllerError):
    code = "UNSUPPORTED_ACTION"


class TextInputFailedError(AndroidControllerError):
    code = "TEXT_INPUT_FAILED"


class ScrollFailedError(AndroidControllerError):
    code = "SCROLL_FAILED"


class SubprocessFailedError(AndroidControllerError):
    code = "SUBPROCESS_ERROR"


class InvalidActionError(AndroidControllerError):
    code = "INVALID_ACTION"


class DeviceTimeoutError(AndroidControllerError):
    code = "DEVICE_TIMEOUT"


class PackageNotFoundError(AndroidControllerError):
    code = "PACKAGE_NOT_FOUND"
