"""Screenshot analysis, including graceful degradation."""

from __future__ import annotations

from pathlib import Path

import cv2
import numpy as np

from knowledge.design_analyzer import analyze_screens, analyze_screenshot

BUTTON = {
    "element_id": "element_000001",
    "type": "android.widget.Button",
    "text": "Login",
    "clickable": True,
    "bounds": {"left": 100, "top": 400, "right": 400, "bottom": 480},
}


def _write_screenshot(path: Path) -> Path:
    image = np.full((800, 480, 3), 240, np.uint8)
    image[400:480, 100:400] = (200, 120, 60)  # BGR
    cv2.imwrite(str(path), image)
    return path


def test_missing_screenshot_does_not_crash(tmp_path):
    result = analyze_screenshot(str(tmp_path / "nope.png"))
    assert result.ok is False
    assert any("not found" in w for w in result.warnings)


def test_corrupt_screenshot_does_not_crash(tmp_path):
    bad = tmp_path / "bad.png"
    bad.write_bytes(b"not an image")
    result = analyze_screenshot(str(bad))
    assert result.ok is False
    assert result.warnings


def test_valid_screenshot(tmp_path):
    path = _write_screenshot(tmp_path / "shot.png")
    result = analyze_screenshot(str(path), [BUTTON])
    assert result.ok is True
    assert (result.width, result.height) == (480, 800)
    assert result.dominant_colors
    assert result.background_color.startswith("#")
    assert result.button_colors


def test_analysis_is_deterministic(tmp_path):
    path = _write_screenshot(tmp_path / "shot.png")
    assert analyze_screenshot(str(path), [BUTTON]).to_dict() == analyze_screenshot(
        str(path), [BUTTON]
    ).to_dict()


def test_out_of_range_bounds_warn(tmp_path):
    path = _write_screenshot(tmp_path / "shot.png")
    huge = {**BUTTON, "bounds": {"left": 5000, "top": 5000, "right": 5001, "bottom": 5001}}
    result = analyze_screenshot(str(path), [huge])
    assert any("outside the screenshot" in w for w in result.warnings)


def test_aggregate_confidence(tmp_path):
    path = _write_screenshot(tmp_path / "shot.png")
    summary = analyze_screens(
        [
            {"screen_id": "screen_000001", "screenshot_path": str(path), "elements": [BUTTON]},
            {"screen_id": "screen_000002", "screenshot_path": str(tmp_path / "gone.png"), "elements": []},
        ]
    )
    assert summary["screenshot_count"] == 2
    assert summary["analyzed_count"] == 1
    assert summary["confidence"] == 0.5
    assert summary["analysis_warnings"]


def test_no_screenshots_at_all():
    summary = analyze_screens([{"screen_id": "screen_000001", "elements": []}])
    assert summary["confidence"] == 0.0
    assert summary["dominant_colors"] == []
    assert any("no screenshot_path" in w for w in summary["analysis_warnings"])


def test_unsupported_properties_stay_empty(tmp_path):
    path = _write_screenshot(tmp_path / "shot.png")
    summary = analyze_screens(
        [{"screen_id": "screen_000001", "screenshot_path": str(path), "elements": [BUTTON]}]
    )
    # We never guess font family or corner radius from a screenshot.
    assert summary["font_sizes"] == []
    assert summary["corner_radius_estimates"] == []
