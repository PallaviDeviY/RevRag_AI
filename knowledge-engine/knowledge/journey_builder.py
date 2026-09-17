"""Journey discovery over the app map.

A "journey" here is a *reachable path the explorer actually recorded*, not a
user-validated flow. We never claim semantic meaning we cannot prove: names
fall back to ``Screen 1 to Screen 4`` when no evidence supports a better one.

Cycle protection: every search is bounded by ``max_length`` (edge count) and
the total number of journeys is capped, so a cyclic graph cannot hang the API.
"""

from __future__ import annotations

from typing import Any, Iterable, Mapping, Sequence

import networkx as nx

from .config import DEFAULT_MAX_JOURNEYS, DEFAULT_MAX_JOURNEY_LENGTH

#: Words that, seen on the source screen or the action's element, give a
#: journey a readable name. Purely cosmetic - no inference is claimed.
_NAME_HINTS = (
    "login",
    "sign in",
    "sign up",
    "register",
    "forgot password",
    "checkout",
    "cart",
    "search",
    "settings",
    "profile",
    "payment",
    "logout",
)


def _screen_number(screen_id: str) -> str:
    """``screen_000004`` -> ``4`` for readable fallback names."""
    tail = screen_id.rsplit("_", 1)[-1]
    return str(int(tail)) if tail.isdigit() else screen_id


def _journey_name(
    path: Sequence[str],
    graph: nx.MultiDiGraph,
    element_text_by_id: Mapping[str, str],
    edge_keys: Sequence[str],
) -> str:
    """Pick a readable name, preferring evidence from element text."""
    for key in edge_keys:
        for _, _, k, data in graph.edges(keys=True, data=True):
            if k != key:
                continue
            text = (element_text_by_id.get(data.get("element_id") or "") or "").lower()
            for hint in _NAME_HINTS:
                if hint in text:
                    return f"{hint.title()} Journey"
    start_label = graph.nodes[path[0]].get("label")
    end_label = graph.nodes[path[-1]].get("label")
    if start_label and end_label and start_label != end_label:
        return f"{start_label} to {end_label}"
    return f"Screen {_screen_number(path[0])} to Screen {_screen_number(path[-1])}"


def _edges_for_path(graph: nx.MultiDiGraph, path: Sequence[str]) -> list[dict[str, Any]]:
    """Pick one representative edge per hop (lowest transition id) deterministically."""
    chosen: list[dict[str, Any]] = []
    for source, target in zip(path, path[1:]):
        candidates = graph.get_edge_data(source, target) or {}
        if not candidates:
            return []
        key = sorted(candidates)[0]
        data = dict(candidates[key])
        data["transition_id"] = key
        chosen.append(data)
    return chosen


def _roots(graph: nx.MultiDiGraph) -> list[str]:
    """Choose one or more start screens per weakly connected component.

    Normally a root is a screen with no incoming transition. A component that
    is entirely cyclic has no such screen, so we fall back to its lowest screen
    id - otherwise that component would produce zero journeys.
    """
    roots: list[str] = []
    for component in nx.weakly_connected_components(graph):
        component_roots = sorted(n for n in component if graph.in_degree(n) == 0)
        roots.extend(component_roots or [min(component)])
    return sorted(set(roots))


def discover_journeys(
    graph: nx.MultiDiGraph,
    *,
    element_text_by_id: Mapping[str, str] | None = None,
    max_length: int = DEFAULT_MAX_JOURNEY_LENGTH,
    max_journeys: int = DEFAULT_MAX_JOURNEYS,
) -> list[dict[str, Any]]:
    """Return shortest paths from every entry point to every reachable screen.

    ``max_length`` bounds the number of edges in a path. Because we use
    shortest paths only, a cycle can never be traversed twice.
    """
    element_text_by_id = element_text_by_id or {}
    if graph.number_of_nodes() == 0:
        return []

    entry_points = _roots(graph)

    seen_paths: set[tuple[str, ...]] = set()
    journeys: list[dict[str, Any]] = []

    for start in entry_points:
        try:
            paths = nx.single_source_shortest_path(graph, start, cutoff=max_length)
        except nx.NetworkXError:  # pragma: no cover - defensive
            continue
        for end in sorted(paths):
            path = paths[end]
            if len(path) < 2:
                continue
            key = tuple(path)
            if key in seen_paths:
                continue
            seen_paths.add(key)

            edges = _edges_for_path(graph, path)
            if len(edges) != len(path) - 1:
                continue
            transition_ids = [e["transition_id"] for e in edges]
            action_ids = [e["action_id"] for e in edges if e.get("action_id")]
            journeys.append(
                {
                    "name": _journey_name(path, graph, element_text_by_id, transition_ids),
                    "start_screen_id": path[0],
                    "end_screen_id": path[-1],
                    "screen_ids": list(path),
                    "action_ids": action_ids,
                    "transition_ids": transition_ids,
                    "length": len(path) - 1,
                    "kind": "shortest_path",
                    "metadata": {
                        "derivation": "networkx single_source_shortest_path",
                        "max_length": max_length,
                        "user_confirmed": False,
                    },
                }
            )
            if len(journeys) >= max_journeys:
                return _deduplicate_names(journeys)

    journeys.sort(key=lambda j: (j["start_screen_id"], j["length"], j["end_screen_id"]))
    return _deduplicate_names(journeys)


def _deduplicate_names(journeys: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Ensure journey names are unique, appending ``(2)``, ``(3)``... as needed."""
    counts: dict[str, int] = {}
    for journey in journeys:
        name = journey["name"]
        counts[name] = counts.get(name, 0) + 1
        if counts[name] > 1:
            journey["name"] = f"{name} ({counts[name]})"
    return journeys


def shortest_journey(
    graph: nx.MultiDiGraph, source: str, target: str, *, max_length: int = DEFAULT_MAX_JOURNEY_LENGTH
) -> list[str] | None:
    """Shortest screen path between two screens, or ``None`` if unreachable."""
    if source not in graph or target not in graph:
        return None
    try:
        path = nx.shortest_path(graph, source, target)
    except nx.NetworkXNoPath:
        return None
    if len(path) - 1 > max_length:
        return None
    return list(path)


def element_text_index(screens: Iterable[Mapping[str, Any]]) -> dict[str, str]:
    """Map ``element_id -> best available label`` for journey naming."""
    index: dict[str, str] = {}
    for screen in screens:
        for element in screen.get("elements") or []:
            element_id = element.get("element_id")
            if not element_id:
                continue
            index[element_id] = element.get("text") or element.get("content_description") or ""
    return index
