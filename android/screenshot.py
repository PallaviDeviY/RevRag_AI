"""Screenshot capture and optional OpenCV similarity helpers."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Optional

from .android_controller import AndroidController
from .config import Config, load_config
from .exceptions import ScreenshotFailedError

logger = logging.getLogger(__name__)


def relative_screenshot_path(observation_id: str) -> str:
    return f"screenshots/{observation_id}.png"


def capture_screenshot(
    output_path: str | Path,
    *,
    controller: Optional[AndroidController] = None,
    config: Optional[Config] = None,
) -> Path:
    controller = controller or AndroidController(config or load_config())
    return controller.capture_screenshot(output_path)


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(65536), b""):
            digest.update(chunk)
    return digest.hexdigest()


def screenshot_similarity(path_a: Path, path_b: Path) -> Optional[float]:
    """Return a 0-1 similarity score using OpenCV if available, else None."""
    try:
        import cv2  # type: ignore
        import numpy as np  # type: ignore
    except Exception:
        return None
    img_a = cv2.imread(str(path_a), cv2.IMREAD_GRAYSCALE)
    img_b = cv2.imread(str(path_b), cv2.IMREAD_GRAYSCALE)
    if img_a is None or img_b is None:
        raise ScreenshotFailedError("OpenCV could not read one of the screenshots")
    if img_a.shape != img_b.shape:
        img_b = cv2.resize(img_b, (img_a.shape[1], img_a.shape[0]))
    diff = cv2.absdiff(img_a, img_b)
    score = 1.0 - (float(np.mean(diff)) / 255.0)
    return max(0.0, min(1.0, score))
