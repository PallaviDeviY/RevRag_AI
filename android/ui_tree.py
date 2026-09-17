"""Capture and parse Android UI hierarchy XML (UIAutomator dump)."""

from __future__ import annotations

import hashlib
import logging
import re
import xml.etree.ElementTree as ET
from pathlib import Path
from typing import Iterable, List, Optional, Tuple

from .exceptions import UiDumpFailedError
from .models import Bounds, UIElement

logger = logging.getLogger(__name__)

_BOUNDS_RE = re.compile(r"\[(\-?\d+),(\-?\d+)\]\[(\-?\d+),(\-?\d+)\]")


def parse_bounds(raw: Optional[str]) -> Optional[Bounds]:
    if not raw:
        return None
    match = _BOUNDS_RE.search(raw)
    if not match:
        return None
    left, top, right, bottom = (int(g) for g in match.groups())
    bounds = Bounds(left=left, top=top, right=right, bottom=bottom)
    return bounds if bounds.is_valid() or (right >= left and bottom >= top) else None


def _as_bool(value: Optional[str], default: bool = False) -> bool:
    if value is None:
        return default
    return value.strip().lower() == "true"


def _empty_to_none(value: Optional[str]) -> Optional[str]:
    if value is None:
        return None
    stripped = value.strip()
    return stripped if stripped else None


def make_element_id(
    index_path: str,
    class_name: str,
    resource_id: str,
    bounds: Optional[Bounds],
    text: str,
    content_desc: str,
) -> str:
    """Deterministic element id. See ``android.models`` module docstring."""
    bounds_part = ""
    if bounds is not None:
        bounds_part = f"{bounds.left},{bounds.top},{bounds.right},{bounds.bottom}"
    raw = "|".join(
        [
            index_path,
            class_name,
            resource_id,
            bounds_part,
            text[:80],
            content_desc[:80],
        ]
    )
    digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()[:12]
    return f"element_{digest}"


def make_screen_id(elements: Iterable[UIElement]) -> str:
    parts = []
    for el in elements:
        b = ""
        if el.bounds:
            b = f"{el.bounds.left},{el.bounds.top},{el.bounds.right},{el.bounds.bottom}"
        parts.append(
            f"{el.type}|{el.resource_id or ''}|{el.text or ''}|{el.content_description or ''}|{b}"
        )
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()[:12]
    return f"screen_{digest}"


def parse_ui_hierarchy(xml_source: str | Path) -> List[UIElement]:
    if isinstance(xml_source, Path) or (
        isinstance(xml_source, str) and Path(xml_source).is_file() and "<" not in xml_source[:32]
    ):
        path = Path(xml_source)
        try:
            text = path.read_text(encoding="utf-8")
        except OSError as exc:
            raise UiDumpFailedError(f"Cannot read UI XML: {path}") from exc
    else:
        text = str(xml_source)
    try:
        root = ET.fromstring(text)
    except ET.ParseError as exc:
        raise UiDumpFailedError(f"Invalid UI hierarchy XML: {exc}") from exc

    elements: List[UIElement] = []

    def walk(node: ET.Element, path: str) -> None:
        attrib = node.attrib
        class_name = attrib.get("class") or node.tag or ""
        if node.tag == "node" or attrib.get("class"):
            resource_id = attrib.get("resource-id", "") or ""
            text_value = attrib.get("text", "") or ""
            content_desc = attrib.get("content-desc", "") or ""
            bounds = parse_bounds(attrib.get("bounds"))
            element = UIElement(
                element_id="",  # assigned after DFS so IDs are element_000001…
                type=class_name or "unknown",
                text=_empty_to_none(text_value),
                content_description=_empty_to_none(content_desc),
                resource_id=_empty_to_none(resource_id),
                clickable=_as_bool(attrib.get("clickable")),
                enabled=_as_bool(attrib.get("enabled"), default=True),
                scrollable=_as_bool(attrib.get("scrollable")),
                focusable=_as_bool(attrib.get("focusable")),
                focused=_as_bool(attrib.get("focused")),
                checked=_as_bool(attrib.get("checked")),
                selected=_as_bool(attrib.get("selected")),
                bounds=bounds,
                package=_empty_to_none(attrib.get("package")),
                password=_as_bool(attrib.get("password")),
                index_path=path,
            )
            elements.append(element)
        children = list(node)
        for i, child in enumerate(children):
            child_index = child.attrib.get("index", str(i))
            child_path = f"{path}/{child_index}" if path else str(child_index)
            walk(child, child_path)

    walk(root, "0")
    for i, element in enumerate(elements, start=1):
        element.element_id = f"element_{i:06d}"
    return elements


def hierarchy_fingerprint(xml_text: str) -> str:
    return hashlib.sha256(xml_text.encode("utf-8")).hexdigest()


def dump_and_parse(xml_path: Path) -> Tuple[List[UIElement], str]:
    elements = parse_ui_hierarchy(xml_path)
    screen_id = make_screen_id(elements)
    return elements, screen_id
