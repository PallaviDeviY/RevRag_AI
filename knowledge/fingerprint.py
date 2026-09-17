"""Deterministic screen fingerprinting.

Strategy (v1, documented in docs/knowledge-engine.md)
-----------------------------------------------------
A fingerprint is the SHA-256 of a canonical JSON document built from
*structural* evidence only. Volatile identifiers (observation_id, screen_id,
element_id, timestamps, file paths) are deliberately excluded so that the same
UI observed twice produces the same hash.

Two fingerprints are produced:

``exact``
    package + activity + every element's (type, text, content_desc,
    resource_id, clickable, enabled, scrollable, normalized bounds).
    Text changes -> different screen.

``structural``
    package + activity + every element's (type, resource_id, clickable,
    enabled, scrollable, coarse bounds bucket). Text is ignored, so a product
    list showing different products still collapses to one screen.

Deduplication in v1 uses ``exact``. ``structural`` is stored alongside and used
by the similarity helper and the stability checker.

This module works on plain dictionaries on purpose: it must stay importable
without FastAPI/Pydantic so it can be unit-tested in isolation.
"""

from __future__ import annotations

import hashlib
import json
import re
from typing import Any, Iterable, Mapping

__all__ = [
    "normalize_text",
    "normalize_bounds",
    "canonical_element",
    "canonical_screen_document",
    "compute_fingerprint",
    "compute_structural_fingerprint",
    "similarity_score",
]

_WHITESPACE = re.compile(r"\s+")

#: Bounds are bucketed to this many pixels for the structural fingerprint, so
#: that a 2px layout jitter between scans does not create a "new" screen.
STRUCTURAL_BUCKET = 16

FINGERPRINT_VERSION = "fp-v1"


def normalize_text(value: Any) -> str:
    """Lowercase, strip, and collapse internal whitespace.

    ``None`` becomes an empty string so that a missing field and an empty field
    are treated identically.
    """
    if value is None:
        return ""
    return _WHITESPACE.sub(" ", str(value).strip()).lower()


def _as_mapping(obj: Any) -> Mapping[str, Any]:
    """Accept dicts, Pydantic models, or dataclass-ish objects."""
    if isinstance(obj, Mapping):
        return obj
    dump = getattr(obj, "model_dump", None)
    if callable(dump):
        return dump()
    return dict(vars(obj))


def normalize_bounds(bounds: Any, bucket: int = 1) -> list[int] | None:
    """Return ``[left, top, right, bottom]`` rounded down to ``bucket`` pixels.

    Returns ``None`` when bounds are absent or unusable, so the caller can
    still fingerprint elements that carry no geometry.
    """
    if bounds is None:
        return None
    data = _as_mapping(bounds)
    try:
        values = [int(data["left"]), int(data["top"]), int(data["right"]), int(data["bottom"])]
    except (KeyError, TypeError, ValueError):
        return None
    if bucket <= 1:
        return values
    return [(v // bucket) * bucket for v in values]


def canonical_element(element: Any, *, include_text: bool, bucket: int = 1) -> dict[str, Any]:
    """Project one element down to the fields that define screen identity.

    ``element_id`` is never included: the controller may renumber elements
    between scans and that must not change the screen's identity.
    """
    data = _as_mapping(element)
    canonical: dict[str, Any] = {
        "type": normalize_text(data.get("type")),
        "resource_id": normalize_text(data.get("resource_id")),
        "clickable": bool(data.get("clickable") or False),
        "enabled": bool(data.get("enabled") if data.get("enabled") is not None else True),
        "scrollable": bool(data.get("scrollable") or False),
        "bounds": normalize_bounds(data.get("bounds"), bucket=bucket),
    }
    if include_text:
        canonical["text"] = normalize_text(data.get("text"))
        canonical["content_description"] = normalize_text(data.get("content_description"))
    return canonical


def canonical_screen_document(
    *,
    package_name: str | None,
    activity: str | None,
    elements: Iterable[Any],
    include_text: bool,
    bucket: int = 1,
) -> dict[str, Any]:
    """Build the canonical, order-independent document that gets hashed.

    Elements are sorted by their canonical JSON form so that a reordered UI
    tree does not change the fingerprint.
    """
    canonical_elements = [
        canonical_element(el, include_text=include_text, bucket=bucket) for el in elements
    ]
    canonical_elements.sort(key=lambda el: json.dumps(el, sort_keys=True, ensure_ascii=False))
    return {
        "version": FINGERPRINT_VERSION,
        "mode": "exact" if include_text else "structural",
        "package_name": normalize_text(package_name),
        "activity": normalize_text(activity),
        "element_count": len(canonical_elements),
        "elements": canonical_elements,
    }


def _hash(document: Mapping[str, Any]) -> str:
    payload = json.dumps(document, sort_keys=True, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def compute_fingerprint(
    *, package_name: str | None, activity: str | None, elements: Iterable[Any]
) -> str:
    """Exact fingerprint. This is the deduplication key."""
    doc = canonical_screen_document(
        package_name=package_name, activity=activity, elements=elements, include_text=True
    )
    return _hash(doc)


def compute_structural_fingerprint(
    *, package_name: str | None, activity: str | None, elements: Iterable[Any]
) -> str:
    """Text-insensitive fingerprint, used for similarity and stability."""
    doc = canonical_screen_document(
        package_name=package_name,
        activity=activity,
        elements=elements,
        include_text=False,
        bucket=STRUCTURAL_BUCKET,
    )
    return _hash(doc)


def similarity_score(elements_a: Iterable[Any], elements_b: Iterable[Any]) -> float:
    """Jaccard similarity over structural element signatures (0.0 - 1.0).

    This is an engineering heuristic used for reporting "changed" screens. It
    is *not* used to merge screens in v1, because silently merging two screens
    that happen to look alike is worse than reporting two screens.
    """
    def signatures(elements: Iterable[Any]) -> set[str]:
        return {
            json.dumps(
                canonical_element(el, include_text=False, bucket=STRUCTURAL_BUCKET),
                sort_keys=True,
            )
            for el in elements
        }

    set_a, set_b = signatures(elements_a), signatures(elements_b)
    if not set_a and not set_b:
        return 1.0
    union = set_a | set_b
    if not union:
        return 1.0
    return round(len(set_a & set_b) / len(union), 6)
