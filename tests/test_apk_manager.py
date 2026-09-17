from pathlib import Path

import pytest

from android.apk_manager import extract_package_name, validate_apk
from android.exceptions import ApkNotFoundError, InvalidApkError


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
