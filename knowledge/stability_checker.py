"""Repeat-scan stability comparison.

The score is an ENGINEERING METRIC, not a scientific guarantee. It answers one
narrow question: "if we explore this app again, do we rediscover the same set
of screen fingerprints?" It says nothing about whether the app itself is
correct, nor about screens the explorer never reached in either run.

Matching is a three-pass process:
  1. exact fingerprint match          -> matched
  2. structural fingerprint match     -> changed (text differs, layout same)
  3. best similarity above threshold  -> changed (layout drifted)
Anything left over is added (only in current) or removed (only in previous).
"""

from __future__ import annotations

import sqlite3
from typing import Any, Mapping, Sequence

from . import repositories as repo
from .fingerprint import similarity_score

#: Below this Jaccard score we call two screens different screens, not a change.
SIMILARITY_THRESHOLD = 0.6


def _load(conn: sqlite3.Connection, scan_id: str) -> list[dict[str, Any]]:
    screens = []
    for row in repo.list_screens(conn, scan_id):
        screen = dict(row)
        screen["elements"] = repo.list_elements(conn, scan_id, screen["screen_id"])
        screens.append(screen)
    return screens


def compare_screen_sets(
    previous: Sequence[Mapping[str, Any]],
    current: Sequence[Mapping[str, Any]],
    *,
    previous_scan_id: str = "",
    current_scan_id: str = "",
) -> dict[str, Any]:
    """Compare two already-loaded screen lists. Pure function, easy to test."""
    warnings: list[str] = []
    prev_remaining = {s["screen_id"]: s for s in previous}
    curr_remaining = {s["screen_id"]: s for s in current}

    matched: list[str] = []
    changed: list[dict[str, Any]] = []

    # Pass 1: exact fingerprint.
    prev_by_fp = {s["fingerprint"]: s for s in previous}
    for screen in sorted(current, key=lambda s: s["screen_id"]):
        twin = prev_by_fp.get(screen["fingerprint"])
        if twin and twin["screen_id"] in prev_remaining and screen["screen_id"] in curr_remaining:
            matched.append(screen["screen_id"])
            prev_remaining.pop(twin["screen_id"], None)
            curr_remaining.pop(screen["screen_id"], None)
    fingerprint_matches = len(matched)

    # Pass 2: structural fingerprint (same layout, different text).
    prev_by_structural = {
        s["structural_fingerprint"]: s for s in prev_remaining.values()
    }
    for screen_id in sorted(curr_remaining):
        screen = curr_remaining[screen_id]
        twin = prev_by_structural.get(screen["structural_fingerprint"])
        if twin and twin["screen_id"] in prev_remaining:
            changed.append(
                {
                    "previous_screen_id": twin["screen_id"],
                    "current_screen_id": screen_id,
                    "similarity": similarity_score(twin["elements"], screen["elements"]),
                    "reason": "Same structure, different visible text.",
                }
            )
            prev_remaining.pop(twin["screen_id"], None)
            curr_remaining.pop(screen_id, None)

    # Pass 3: best-effort similarity.
    for screen_id in sorted(list(curr_remaining)):
        screen = curr_remaining[screen_id]
        best_id, best_score = None, 0.0
        for prev_id in sorted(prev_remaining):
            score = similarity_score(prev_remaining[prev_id]["elements"], screen["elements"])
            if score > best_score:
                best_id, best_score = prev_id, score
        if best_id is not None and best_score >= SIMILARITY_THRESHOLD:
            changed.append(
                {
                    "previous_screen_id": best_id,
                    "current_screen_id": screen_id,
                    "similarity": best_score,
                    "reason": f"Layout drifted (similarity {best_score:.2f}).",
                }
            )
            prev_remaining.pop(best_id, None)
            curr_remaining.pop(screen_id, None)

    added = sorted(curr_remaining)
    removed = sorted(prev_remaining)

    denominator = max(len(previous), len(current))
    if denominator == 0:
        stability_score = 1.0
        warnings.append("Both scans are empty; the stability score is not meaningful.")
    else:
        # Exact matches count fully, changed screens count half.
        stability_score = round((len(matched) + 0.5 * len(changed)) / denominator, 4)

    if not previous:
        warnings.append(f"Previous scan '{previous_scan_id}' has no screens.")
    if not current:
        warnings.append(f"Current scan '{current_scan_id}' has no screens.")
    if added or removed:
        warnings.append(
            f"Screen set differs between scans: {len(added)} added, {len(removed)} removed."
        )
    warnings.append(
        "stability_score is an engineering metric for explorer repeatability, "
        "not a scientific guarantee about the app."
    )

    changed.sort(key=lambda c: c["current_screen_id"])
    return {
        "previous_scan_id": previous_scan_id,
        "current_scan_id": current_scan_id,
        "previous_screen_count": len(previous),
        "current_screen_count": len(current),
        "matched_screens": len(matched),
        "fingerprint_matches": fingerprint_matches,
        "added_screens": added,
        "removed_screens": removed,
        "changed_screens": changed,
        "stability_score": stability_score,
        "warnings": warnings,
    }


def compare_scans(
    conn: sqlite3.Connection, previous_scan_id: str, current_scan_id: str
) -> dict[str, Any]:
    """Load both scans from SQLite and compare them."""
    return compare_screen_sets(
        _load(conn, previous_scan_id),
        _load(conn, current_scan_id),
        previous_scan_id=previous_scan_id,
        current_scan_id=current_scan_id,
    )
