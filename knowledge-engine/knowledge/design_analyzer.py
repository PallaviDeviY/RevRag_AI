"""Screenshot-based design analysis (OpenCV + NumPy).

Scope and honesty
-----------------
What we can measure reasonably well from a PNG:
  * dominant colours (k-means over downsampled pixels)
  * the background colour (most common colour in the border region)
  * image dimensions and basic quality checks

What we approximate, and label as such:
  * button colours - sampled from the *UI-tree bounds of clickable elements*,
    not from shape detection. Requires element bounds.
  * text colours - sampled from high-contrast pixels inside text elements.
  * spacing - pixel gaps between sibling element bounds, from the UI tree.

What we do NOT attempt, because a screenshot cannot support it:
  * font family, exact font size in sp, exact corner radius.
  ``font_sizes`` and ``corner_radius_estimates`` stay empty unless the UI tree
  ever starts carrying that data.

A missing or unreadable screenshot never raises: it produces a warning and a
lower confidence score.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Mapping, Sequence

import cv2
import numpy as np

logger = logging.getLogger(__name__)

#: Pixels are downsampled to at most this many before k-means, for speed.
MAX_SAMPLE_PIXELS = 20000
DEFAULT_COLOR_COUNT = 5


@dataclass
class DesignAnalysisResult:
    """Per-screenshot analysis outcome."""

    path: str
    ok: bool = False
    width: int | None = None
    height: int | None = None
    dominant_colors: list[str] = field(default_factory=list)
    background_color: str | None = None
    text_colors: list[str] = field(default_factory=list)
    button_colors: list[str] = field(default_factory=list)
    mean_brightness: float | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "path": self.path,
            "ok": self.ok,
            "width": self.width,
            "height": self.height,
            "dominant_colors": self.dominant_colors,
            "background_color": self.background_color,
            "text_colors": self.text_colors,
            "button_colors": self.button_colors,
            "mean_brightness": self.mean_brightness,
            "warnings": self.warnings,
        }


def _to_hex(bgr: Sequence[float]) -> str:
    b, g, r = (int(max(0, min(255, round(float(c))))) for c in bgr[:3])
    return f"#{r:02x}{g:02x}{b:02x}"


def _dominant_colors(image: np.ndarray, count: int = DEFAULT_COLOR_COUNT) -> list[str]:
    """K-means over a random pixel sample. Returns hex colours, most common first."""
    pixels = image.reshape(-1, 3).astype(np.float32)
    if pixels.shape[0] > MAX_SAMPLE_PIXELS:
        rng = np.random.default_rng(seed=42)  # fixed seed -> deterministic output
        pixels = pixels[rng.choice(pixels.shape[0], MAX_SAMPLE_PIXELS, replace=False)]
    k = int(min(count, max(1, len(np.unique(pixels, axis=0)))))
    criteria = (cv2.TERM_CRITERIA_EPS + cv2.TERM_CRITERIA_MAX_ITER, 20, 1.0)
    _, labels, centers = cv2.kmeans(
        pixels, k, None, criteria, 3, cv2.KMEANS_PP_CENTERS
    )
    counts = np.bincount(labels.flatten(), minlength=k)
    order = np.argsort(-counts)
    return [_to_hex(centers[i]) for i in order]


def _background_color(image: np.ndarray) -> str:
    """Most common colour in a thin border frame around the image."""
    h, w = image.shape[:2]
    band = max(1, min(h, w) // 40)
    border = np.concatenate(
        [
            image[:band].reshape(-1, 3),
            image[-band:].reshape(-1, 3),
            image[:, :band].reshape(-1, 3),
            image[:, -band:].reshape(-1, 3),
        ]
    )
    quantised = (border // 8 * 8).astype(np.uint8)
    colors, counts = np.unique(quantised, axis=0, return_counts=True)
    return _to_hex(colors[int(np.argmax(counts))])


def _crop(image: np.ndarray, bounds: Mapping[str, Any]) -> np.ndarray | None:
    h, w = image.shape[:2]
    try:
        left = max(0, int(bounds["left"]))
        top = max(0, int(bounds["top"]))
        right = min(w, int(bounds["right"]))
        bottom = min(h, int(bounds["bottom"]))
    except (KeyError, TypeError, ValueError):
        return None
    if right - left < 2 or bottom - top < 2:
        return None
    return image[top:bottom, left:right]


def _region_colors(
    image: np.ndarray, elements: Sequence[Mapping[str, Any]], predicate
) -> tuple[list[str], list[str]]:
    """Sample the modal colour inside each matching element's bounds."""
    colors: list[str] = []
    warnings: list[str] = []
    for element in elements:
        if not predicate(element):
            continue
        bounds = element.get("bounds")
        if not isinstance(bounds, Mapping):
            continue
        patch = _crop(image, bounds)
        if patch is None:
            warnings.append(
                f"Element {element.get('element_id')} bounds fall outside the screenshot; skipped."
            )
            continue
        flat = (patch.reshape(-1, 3) // 8 * 8).astype(np.uint8)
        values, counts = np.unique(flat, axis=0, return_counts=True)
        colors.append(_to_hex(values[int(np.argmax(counts))]))
    # Deterministic: most frequent first, then hex order.
    ranked = sorted(set(colors), key=lambda c: (-colors.count(c), c))
    return ranked, warnings


def analyze_screenshot(
    path: str, elements: Sequence[Mapping[str, Any]] | None = None
) -> DesignAnalysisResult:
    """Analyse one screenshot. Never raises on a missing or corrupt file.

    ``elements`` (from the UI tree) are optional; without them button and text
    colours cannot be attributed and stay empty.
    """
    result = DesignAnalysisResult(path=path)
    elements = list(elements or [])

    file_path = Path(path)
    if not file_path.exists():
        result.warnings.append(f"Screenshot not found: {path}")
        return result

    image = cv2.imread(str(file_path), cv2.IMREAD_COLOR)
    if image is None or image.size == 0:
        result.warnings.append(f"Screenshot could not be decoded: {path}")
        return result

    try:
        result.ok = True
        result.height, result.width = int(image.shape[0]), int(image.shape[1])
        result.mean_brightness = round(float(np.mean(cv2.cvtColor(image, cv2.COLOR_BGR2GRAY))), 2)
        result.dominant_colors = _dominant_colors(image)
        result.background_color = _background_color(image)

        buttons, button_warnings = _region_colors(
            image, elements, lambda el: bool(el.get("clickable"))
        )
        result.button_colors = buttons
        result.warnings.extend(button_warnings)

        texts, text_warnings = _region_colors(
            image, elements, lambda el: bool((el.get("text") or "").strip())
        )
        result.text_colors = texts
        result.warnings.extend(text_warnings)

        if result.width < 200 or result.height < 200:
            result.warnings.append("Screenshot is unusually small; colour analysis is low quality.")
    except cv2.error as exc:  # pragma: no cover - OpenCV internal failure
        result.ok = False
        result.warnings.append(f"OpenCV failed on {path}: {exc}")
    return result


def _spacing_estimates(elements: Sequence[Mapping[str, Any]]) -> dict[str, Any]:
    """Vertical gaps between vertically-stacked element bounds, in pixels."""
    boxes = [
        el["bounds"]
        for el in elements
        if isinstance(el.get("bounds"), Mapping)
        and all(k in el["bounds"] for k in ("left", "top", "right", "bottom"))
    ]
    if len(boxes) < 2:
        return {"vertical_gaps_px": [], "median_vertical_gap_px": None, "sample_size": len(boxes)}
    boxes = sorted(boxes, key=lambda b: (b["top"], b["left"]))
    gaps = [
        int(nxt["top"]) - int(cur["bottom"])
        for cur, nxt in zip(boxes, boxes[1:])
        if int(nxt["top"]) - int(cur["bottom"]) >= 0
    ]
    return {
        "vertical_gaps_px": sorted(gaps),
        "median_vertical_gap_px": float(np.median(gaps)) if gaps else None,
        "sample_size": len(boxes),
    }


def analyze_screens(
    screens: Sequence[Mapping[str, Any]], media_root: str | Path = "."
) -> dict[str, Any]:
    """Aggregate design evidence across every screen in a scan.

    Returns a dict matching the ``DesignLanguage`` schema. ``confidence`` is the
    fraction of screens whose screenshot we could actually read - it is an
    engineering signal, not a statistical measure.
    """
    media_root = Path(media_root)
    results: list[DesignAnalysisResult] = []
    warnings: list[str] = []
    dimensions: list[dict[str, int]] = []
    dominant: list[str] = []
    backgrounds: list[str] = []
    buttons: list[str] = []
    texts: list[str] = []
    all_elements: list[Mapping[str, Any]] = []

    screenshot_count = 0
    for screen in sorted(screens, key=lambda s: s["screen_id"]):
        elements = list(screen.get("elements") or [])
        all_elements.extend(elements)
        path = screen.get("screenshot_path")
        if not path:
            warnings.append(f"Screen {screen['screen_id']} has no screenshot_path.")
            continue
        screenshot_count += 1
        resolved = Path(path)
        if not resolved.is_absolute() and not resolved.exists():
            resolved = media_root / path
        result = analyze_screenshot(str(resolved), elements)
        results.append(result)
        warnings.extend(f"[{screen['screen_id']}] {w}" for w in result.warnings)
        if not result.ok:
            continue
        dimensions.append({"width": result.width or 0, "height": result.height or 0})
        dominant.extend(result.dominant_colors)
        if result.background_color:
            backgrounds.append(result.background_color)
        buttons.extend(result.button_colors)
        texts.extend(result.text_colors)

    analyzed = sum(1 for r in results if r.ok)
    confidence = round(analyzed / screenshot_count, 4) if screenshot_count else 0.0

    def rank(values: list[str], limit: int = 8) -> list[str]:
        return sorted(set(values), key=lambda c: (-values.count(c), c))[:limit]

    if screenshot_count == 0:
        warnings.append("No screenshots available; design language is empty.")

    return {
        "dominant_colors": rank(dominant),
        "background_colors": rank(backgrounds, 4),
        "text_colors": rank(texts),
        "button_colors": rank(buttons),
        "font_sizes": [],
        "corner_radius_estimates": [],
        "spacing_estimates": _spacing_estimates(all_elements),
        "screen_dimensions": [
            {"width": w, "height": h}
            for w, h in sorted({(d["width"], d["height"]) for d in dimensions})
        ],
        "screenshot_count": screenshot_count,
        "analyzed_count": analyzed,
        "confidence": confidence,
        "analysis_warnings": warnings,
    }
